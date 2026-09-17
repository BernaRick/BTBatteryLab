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

// Azzeriamo il log ad ogni avvio per non farlo crescere all'infinito
// tra una sessione e l'altra - JsonlTailMonitor lato Python comunque
// ignora tutto il contenuto precedente (si mette in fondo al file
// appena parte), quindi non e' funzionalmente necessario, solo
// housekeeping.
//
// Va tentato con cautela: run.bat avvia apposta il collector Python
// PRIMA di questo processo (altrimenti si perdono gli eventi
// "Startup" iniziali - vedi README), quindi quando arriviamo qui il
// file potrebbe gia' essere aperto in lettura da Python, e su
// Windows File.Delete su un file aperto da un altro processo lancia
// IOException invece di essere ignorato in silenzio come su Linux.
// In quel caso continuiamo semplicemente in append: meglio un file
// che si allunga di qualche riga vecchia che un crash all'avvio.
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
        $"Impossibile azzerare il log esistente (probabilmente in " +
        $"uso dal collector Python gia' avviato): {ex.Message}");
    Console.WriteLine("Continuo aggiungendo gli eventi in coda al file esistente.");
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
        Console.WriteLine($"  [battery] errore lettura: {ex.Message}");
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
        (battery is null ? "" : $" (batteria {battery}%)"));

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
            $"Impossibile aprire {info.Name} ({info.Id}): {ex.Message}");

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
        $"Trovato: {device.Name} [{info.Id}] - stato: {initialStatus}" +
        (initialBattery is null ? "" : $" (batteria {initialBattery}%)"));

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

// --- Dispositivi classici (BR/EDR) ---
//
// Cuffie/auricolari come le OPPO Enco Air2 o le HD 450BT non hanno
// un'interfaccia BLE utile: la loro batteria si legge solo lato
// Python via PnP (BluetoothCollector.read_battery_levels()), non da
// qui. Quello che possiamo fare qui e' tracciare la loro connessione
// in tempo reale con l'equivalente classico di BluetoothLEDevice, e
// scrivere lo stesso tipo di evento nel JSONL (senza BatteryPercent -
// non e' un dato che questo processo sa leggere per un device
// classico). Il lato Python, vedendo un evento "Connected" per un
// device che non conosce come sorgente BLE, fa scattare un poll
// batteria immediato invece di aspettare il timer.

Dictionary<string, BluetoothDevice> trackedClassicDevices = new();

void HandleClassicConnectionStatusChanged(BluetoothDevice device)
{
    string status = device.ConnectionStatus.ToString();

    string timestamp = DateTime.Now.ToString("HH:mm:ss.fff");

    Console.WriteLine($"[{timestamp}] {device.Name} (classico): {status}");

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
            $"Impossibile aprire (classico) {info.Name} ({info.Id}): " +
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
        $"Trovato (classico): {device.Name} [{info.Id}] - " +
        $"stato: {initialStatus}");

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

Console.WriteLine("BTBatteryLab - BLE Watcher (tutti i dispositivi)");
Console.WriteLine("------------------------------------------------");
Console.WriteLine();
Console.WriteLine($"Log file: {logFile}");
Console.WriteLine();

// --- Collector Python in bundle (build standalone, vedi build_exe.bat) ---
//
// Se questo eseguibile e' stato pubblicato con build_exe.bat, accanto a
// lui c'e' una cartella "btbatterylab" con l'exe generato da PyInstaller:
// in quel caso lo avviamo noi in background, senza una seconda finestra
// di console, invece di richiedere due terminali separati come con
// run.bat. In sviluppo (dotnet run dalla sorgente) quella cartella non
// esiste: non cambia nulla, si continua a usare run.bat o ad avviare il
// collector a mano.
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
        $"Collector Python avviato in background (log: {collectorLogFile})");

    // Stesso motivo dell'attesa in run.bat: JsonlTailMonitor segue solo
    // le righe *nuove* scritte da questo momento in poi, quindi il
    // collector deve essere gia' in ascolto prima che i watcher qui
    // sotto scrivano i loro eventi "Startup".
    await Task.Delay(3000);
}
else
{
    Console.WriteLine(
        "Collector Python non incluso in questo eseguibile (modalita' " +
        "sviluppo): avvialo separatamente con run.bat o " +
        "'python -m btbatterylab.main'.");
}

Console.WriteLine();

string selector = BluetoothLEDevice.GetDeviceSelector();

DeviceWatcher watcher = DeviceInformation.CreateWatcher(selector);

watcher.Added += async (_, info) => await OnDeviceAddedAsync(info);
watcher.Removed += (_, update) => OnDeviceRemoved(update.Id);

Console.WriteLine("Avvio ricerca dispositivi BLE accoppiati...");
Console.WriteLine();

watcher.Start();

string classicSelector = BluetoothDevice.GetDeviceSelector();

DeviceWatcher classicWatcher = DeviceInformation.CreateWatcher(classicSelector);

classicWatcher.Added += async (_, info) => await OnClassicDeviceAddedAsync(info);
classicWatcher.Removed += (_, update) => OnClassicDeviceRemoved(update.Id);

Console.WriteLine("Avvio ricerca dispositivi classici accoppiati...");
Console.WriteLine();

classicWatcher.Start();

Console.WriteLine();
Console.WriteLine("Monitoring in corso.");
Console.WriteLine("Premi ENTER per terminare.");
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
            $"Impossibile fermare il collector Python: {ex.Message}");
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
