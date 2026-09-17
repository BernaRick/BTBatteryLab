using System.Diagnostics;
using System.Text.Json;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.GenericAttributeProfile;
using Windows.Devices.Enumeration;
using Windows.Storage.Streams;

// Standard Bluetooth SIG GATT identifiers for battery reporting.
// Any BLE device implementing the standard Battery Service exposes its
// level through this characteristic - no vendor-specific code needed.
Guid batteryServiceUuid =
    Guid.Parse("0000180f-0000-1000-8000-00805f9b34fb");

Guid batteryLevelCharacteristicUuid =
    Guid.Parse("00002a19-0000-1000-8000-00805f9b34fb");

string dataDirectory =
    Path.Combine(
        Environment.GetFolderPath(
            Environment.SpecialFolder.MyDocuments),
        "BTBatteryLabData");

Directory.CreateDirectory(dataDirectory);

string logFile =
    Path.Combine(
        dataDirectory,
        "ble-events.jsonl");

// We reset the log on every startup so it doesn't grow forever across
// sessions - the Python-side JsonlTailMonitor ignores all existing
// content anyway (it seeks to the end of the file as soon as it
// starts), so this isn't functionally necessary, just housekeeping.
//
// This needs to be attempted carefully: run.bat deliberately starts
// the Python collector BEFORE this process (otherwise the initial
// "Startup" events get lost - see README), so by the time we get here
// the file might already be open for reading by Python, and on
// Windows, File.Delete on a file held open by another process throws
// IOException instead of being silently ignored like on Linux. In
// that case we just continue in append mode: better a file with a few
// extra old lines than a crash on startup.
try
{
    if (File.Exists(logFile))
    {
        File.Delete(logFile);
    }
}
catch (IOException ex)
{
    Console.WriteLine(
        $"Could not reset the existing log (likely in use by an " +
        $"already-running Python collector): {ex.Message}");
    Console.WriteLine("Continuing by appending events to the existing file.");
}

object logLock = new();

void LogEvent(
    string eventType,
    string status,
    string deviceName,
    ulong bluetoothAddress,
    int? batteryPercent)
{
    var record = new
    {
        Timestamp = DateTime.UtcNow,
        Event = eventType,
        Status = status,
        DeviceName = deviceName,
        BluetoothAddress = bluetoothAddress.ToString("X"),
        BatteryPercent = batteryPercent
    };

    string json = JsonSerializer.Serialize(record);

    lock (logLock)
    {
        File.AppendAllText(logFile, json + Environment.NewLine);
    }
}

async Task<int?> TryReadBatteryLevelAsync(BluetoothLEDevice device)
{
    try
    {
        GattDeviceServicesResult servicesResult =
            await device.GetGattServicesForUuidAsync(
                batteryServiceUuid,
                BluetoothCacheMode.Uncached);

        if (servicesResult.Status != GattCommunicationStatus.Success ||
            servicesResult.Services.Count == 0)
        {
            return null;
        }

        using GattDeviceService batteryService =
            servicesResult.Services[0];

        GattCharacteristicsResult characteristicsResult =
            await batteryService.GetCharacteristicsForUuidAsync(
                batteryLevelCharacteristicUuid);

        if (characteristicsResult.Status != GattCommunicationStatus.Success ||
            characteristicsResult.Characteristics.Count == 0)
        {
            return null;
        }

        GattCharacteristic characteristic =
            characteristicsResult.Characteristics[0];

        GattReadResult readResult =
            await characteristic.ReadValueAsync(
                BluetoothCacheMode.Uncached);

        if (readResult.Status != GattCommunicationStatus.Success ||
            readResult.Value.Length == 0)
        {
            return null;
        }

        DataReader reader = DataReader.FromBuffer(readResult.Value);

        byte level = reader.ReadByte();

        return level;
    }
    catch (Exception ex)
    {
        Console.WriteLine($"  [battery] read error: {ex.Message}");
        return null;
    }
}

async Task HandleConnectionStatusChangedAsync(BluetoothLEDevice device)
{
    string status = device.ConnectionStatus.ToString();

    int? battery = null;

    if (device.ConnectionStatus == BluetoothConnectionStatus.Connected)
    {
        battery = await TryReadBatteryLevelAsync(device);
    }

    string timestamp = DateTime.Now.ToString("HH:mm:ss.fff");

    Console.WriteLine(
        $"[{timestamp}] {device.Name}: {status}" +
        (battery is null ? "" : $" (battery {battery}%)"));

    LogEvent(
        "ConnectionStatusChanged",
        status,
        device.Name,
        device.BluetoothAddress,
        battery);
}

Dictionary<string, BluetoothLEDevice> trackedDevices = new();

async Task OnDeviceAddedAsync(DeviceInformation info)
{
    BluetoothLEDevice? device;

    try
    {
        device = await BluetoothLEDevice.FromIdAsync(info.Id);
    }
    catch (Exception ex)
    {
        Console.WriteLine(
            $"Could not open {info.Name} ({info.Id}): {ex.Message}");

        return;
    }

    if (device is null)
    {
        return;
    }

    lock (trackedDevices)
    {
        if (trackedDevices.ContainsKey(info.Id))
        {
            device.Dispose();
            return;
        }

        trackedDevices[info.Id] = device;
    }

    string initialStatus = device.ConnectionStatus.ToString();

    device.ConnectionStatusChanged += async (_, _) =>
        await HandleConnectionStatusChangedAsync(device);

    int? initialBattery = null;

    if (device.ConnectionStatus == BluetoothConnectionStatus.Connected)
    {
        initialBattery = await TryReadBatteryLevelAsync(device);
    }

    Console.WriteLine(
        $"Found: {device.Name} [{info.Id}] - status: {initialStatus}" +
        (initialBattery is null ? "" : $" (battery {initialBattery}%)"));

    LogEvent(
        "Startup",
        device.ConnectionStatus.ToString(),
        device.Name,
        device.BluetoothAddress,
        initialBattery);
}

void OnDeviceRemoved(string id)
{
    lock (trackedDevices)
    {
        if (trackedDevices.TryGetValue(id, out BluetoothLEDevice? device))
        {
            device.Dispose();
            trackedDevices.Remove(id);
        }
    }
}

// --- Classic devices (BR/EDR) ---
//
// Headsets/earbuds like the OPPO Enco Air2 or the HD 450BT don't have
// a useful BLE interface: their battery can only be read on the
// Python side via PnP (BluetoothCollector.read_battery_levels()), not
// here. What we CAN do here is track their connection in real time
// with the classic equivalent of BluetoothLEDevice, and write the
// same kind of event to the JSONL (without BatteryPercent - that's
// not something this process can read for a classic device). On the
// Python side, seeing a "Connected" event for a device it doesn't
// know as a BLE source triggers an immediate battery poll instead of
// waiting for the timer.

Dictionary<string, BluetoothDevice> trackedClassicDevices = new();

void HandleClassicConnectionStatusChanged(BluetoothDevice device)
{
    string status = device.ConnectionStatus.ToString();

    string timestamp = DateTime.Now.ToString("HH:mm:ss.fff");

    Console.WriteLine($"[{timestamp}] {device.Name} (classic): {status}");

    LogEvent(
        "ConnectionStatusChanged",
        status,
        device.Name,
        device.BluetoothAddress,
        null);
}

async Task OnClassicDeviceAddedAsync(DeviceInformation info)
{
    BluetoothDevice? device;

    try
    {
        device = await BluetoothDevice.FromIdAsync(info.Id);
    }
    catch (Exception ex)
    {
        Console.WriteLine(
            $"Could not open (classic) {info.Name} ({info.Id}): " +
            $"{ex.Message}");

        return;
    }

    if (device is null)
    {
        return;
    }

    lock (trackedClassicDevices)
    {
        if (trackedClassicDevices.ContainsKey(info.Id))
        {
            device.Dispose();
            return;
        }

        trackedClassicDevices[info.Id] = device;
    }

    string initialStatus = device.ConnectionStatus.ToString();

    device.ConnectionStatusChanged += (_, _) =>
        HandleClassicConnectionStatusChanged(device);

    Console.WriteLine(
        $"Found (classic): {device.Name} [{info.Id}] - " +
        $"status: {initialStatus}");

    LogEvent(
        "Startup",
        initialStatus,
        device.Name,
        device.BluetoothAddress,
        null);
}

void OnClassicDeviceRemoved(string id)
{
    lock (trackedClassicDevices)
    {
        if (trackedClassicDevices.TryGetValue(
                id, out BluetoothDevice? device))
        {
            device.Dispose();
            trackedClassicDevices.Remove(id);
        }
    }
}

Console.WriteLine("BTBatteryLab - BLE Watcher (all devices)");
Console.WriteLine("------------------------------------------------");
Console.WriteLine();
Console.WriteLine($"Log file: {logFile}");
Console.WriteLine();

// --- Bundled Python collector (standalone build, see build_exe.bat) ---
//
// If this executable was published with build_exe.bat, there's a
// "btbatterylab" folder next to it with the exe PyInstaller
// generated: in that case we start it ourselves in the background,
// without a second console window, instead of requiring two separate
// terminals like with run.bat. In development (dotnet run from
// source) that folder doesn't exist: nothing changes, we keep using
// run.bat or starting the collector by hand.
string collectorExePath = Path.Combine(
    AppContext.BaseDirectory, "btbatterylab", "btbatterylab.exe");

Process? collectorProcess = null;

if (File.Exists(collectorExePath))
{
    string collectorLogFile = Path.Combine(dataDirectory, "collector.log");

    var collectorStartInfo = new ProcessStartInfo
    {
        FileName = collectorExePath,
        UseShellExecute = false,
        CreateNoWindow = true,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };

    collectorProcess = new Process { StartInfo = collectorStartInfo };

    collectorProcess.OutputDataReceived += (_, e) =>
    {
        if (e.Data is null) return;

        lock (logLock)
        {
            File.AppendAllText(
                collectorLogFile,
                $"[{DateTime.Now:HH:mm:ss}] {e.Data}{Environment.NewLine}");
        }
    };

    collectorProcess.ErrorDataReceived += (_, e) =>
    {
        if (e.Data is null) return;

        lock (logLock)
        {
            File.AppendAllText(
                collectorLogFile,
                $"[{DateTime.Now:HH:mm:ss}] [ERR] {e.Data}{Environment.NewLine}");
        }
    };

    collectorProcess.Start();
    collectorProcess.BeginOutputReadLine();
    collectorProcess.BeginErrorReadLine();

    Console.WriteLine(
        $"Python collector started in the background (log: {collectorLogFile})");

    // Same reason for the wait as in run.bat: JsonlTailMonitor only
    // follows *new* lines written from this point on, so the
    // collector needs to already be listening before the watchers
    // below write their "Startup" events.
    await Task.Delay(3000);
}
else
{
    Console.WriteLine(
        "Python collector not included in this executable (development " +
        "mode): start it separately with run.bat or " +
        "'python -m btbatterylab.main'.");
}

Console.WriteLine();

string selector = BluetoothLEDevice.GetDeviceSelector();

DeviceWatcher watcher = DeviceInformation.CreateWatcher(selector);

watcher.Added += async (_, info) => await OnDeviceAddedAsync(info);
watcher.Removed += (_, update) => OnDeviceRemoved(update.Id);

Console.WriteLine("Starting search for paired BLE devices...");
Console.WriteLine();

watcher.Start();

string classicSelector = BluetoothDevice.GetDeviceSelector();

DeviceWatcher classicWatcher = DeviceInformation.CreateWatcher(classicSelector);

classicWatcher.Added += async (_, info) => await OnClassicDeviceAddedAsync(info);
classicWatcher.Removed += (_, update) => OnClassicDeviceRemoved(update.Id);

Console.WriteLine("Starting search for paired classic devices...");
Console.WriteLine();

classicWatcher.Start();

Console.WriteLine();
Console.WriteLine("Monitoring in progress.");
Console.WriteLine("Press ENTER to stop.");
Console.WriteLine();

Console.ReadLine();

watcher.Stop();
classicWatcher.Stop();

if (collectorProcess is not null && !collectorProcess.HasExited)
{
    try
    {
        collectorProcess.Kill(entireProcessTree: true);
    }
    catch (Exception ex)
    {
        Console.WriteLine(
            $"Could not stop the Python collector: {ex.Message}");
    }
}

lock (trackedDevices)
{
    foreach (BluetoothLEDevice device in trackedDevices.Values)
    {
        device.Dispose();
    }

    trackedDevices.Clear();
}

lock (trackedClassicDevices)
{
    foreach (BluetoothDevice device in trackedClassicDevices.Values)
    {
        device.Dispose();
    }

    trackedClassicDevices.Clear();
}
