using System.Text.Json;
using Windows.Devices.Bluetooth;
using Windows.Devices.Enumeration;

const string TargetName = "MX Master 2S";

string logFile =
    Path.Combine(
        AppContext.BaseDirectory,
        $"ble-events-{DateTime.Now:yyyyMMdd-HHmmss}.jsonl");

void LogEvent(
    string eventType,
    string status,
    string deviceName,
    ulong bluetoothAddress)
{
    var record = new
    {
        Timestamp = DateTime.UtcNow,
        Event = eventType,
        Status = status,
        DeviceName = deviceName,
        BluetoothAddress = bluetoothAddress.ToString("X")
    };

    string json = JsonSerializer.Serialize(record);

    File.AppendAllText(
        logFile,
        json + Environment.NewLine);
}

Console.WriteLine("MX Master 2S BLE Monitor");
Console.WriteLine("------------------------");
Console.WriteLine();

var devices = await DeviceInformation.FindAllAsync();

DeviceInformation? target =
    devices.FirstOrDefault(d =>
        !string.IsNullOrWhiteSpace(d.Name) &&
        d.Name.Contains(
            TargetName,
            StringComparison.OrdinalIgnoreCase));

if (target is null)
{
    Console.WriteLine("MX Master 2S non trovato.");
    return;
}

Console.WriteLine("Dispositivo trovato:");
Console.WriteLine(target.Name);
Console.WriteLine(target.Id);
Console.WriteLine();

BluetoothLEDevice? bleDevice =
    await BluetoothLEDevice.FromIdAsync(target.Id);

if (bleDevice is null)
{
    Console.WriteLine("FromIdAsync() ha restituito null.");
    return;
}

Console.WriteLine("BluetoothLEDevice aperto.");
Console.WriteLine($"Name               : {bleDevice.Name}");
Console.WriteLine($"BluetoothAddress   : 0x{bleDevice.BluetoothAddress:X}");
Console.WriteLine($"ConnectionStatus   : {bleDevice.ConnectionStatus}");
Console.WriteLine();

LogEvent(
    "Startup",
    bleDevice.ConnectionStatus.ToString(),
    bleDevice.Name,
    bleDevice.BluetoothAddress);

bleDevice.ConnectionStatusChanged += (_, _) =>
{
    string status =
        bleDevice.ConnectionStatus.ToString();

    string timestamp =
        DateTime.Now.ToString("HH:mm:ss.fff");

    Console.WriteLine(
        $"[{timestamp}] ConnectionStatus = {status}");

    LogEvent(
        "ConnectionStatusChanged",
        status,
        bleDevice.Name,
        bleDevice.BluetoothAddress);
};

Console.WriteLine("Tentativo lettura servizi GATT...");
Console.WriteLine();

try
{
    var gattResult =
        await bleDevice.GetGattServicesAsync();

    Console.WriteLine(
        $"Gatt Status: {gattResult.Status}");

    Console.WriteLine(
        $"Servizi trovati: {gattResult.Services.Count}");

    foreach (var service in gattResult.Services)
    {
        Console.WriteLine(
            $"  Service UUID: {service.Uuid}");
    }

    LogEvent(
        "GattDiscovery",
        gattResult.Status.ToString(),
        bleDevice.Name,
        bleDevice.BluetoothAddress);
}
catch (Exception ex)
{
    Console.WriteLine(
        $"Errore GATT: {ex.Message}");

    LogEvent(
        "GattError",
        ex.Message,
        bleDevice.Name,
        bleDevice.BluetoothAddress);
}

Console.WriteLine();
Console.WriteLine($"Log file: {logFile}");
Console.WriteLine();
Console.WriteLine("Monitoring...");
Console.WriteLine("Lascia il mouse fermo, riattivalo oppure spegnilo.");
Console.WriteLine("Premi ENTER per terminare.");
Console.WriteLine();

Console.ReadLine();

bleDevice.Dispose();