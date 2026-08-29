using BluetoothWatcher;
using Windows.Devices.Enumeration;
using Windows.Devices.Enumeration.Pnp;

Console.WriteLine("Bluetooth Device Watcher");
Console.WriteLine("------------------------");

string[] properties =
{
    "System.ItemNameDisplay",
    "System.Devices.Aep.DeviceAddress",
    "System.Devices.Aep.IsConnected",
    "System.Devices.Present",
    "System.Devices.ContainerId",
    "System.Devices.Aep.Bluetooth.Le.IsConnectable",
    "System.Devices.Aep.Bluetooth.LastSeenTime",
    "System.Devices.Aep.Bluetooth.LastConnectedTime"
};

string bluetoothSelector =
    "System.Devices.Aep.ProtocolId:=\"{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}\"";

//
// DEVICE WATCHER
//
DeviceWatcher watcher =
    DeviceInformation.CreateWatcher(
        bluetoothSelector,
        properties,
        DeviceInformationKind.AssociationEndpoint);

watcher.Added += (_, device) =>
{
    DeviceLogger.Log(
        "Added",
        device.Id,
        device.Name,
        device.Properties.ToDictionary(
            x => x.Key,
            x => x.Value ?? "null"));
};

watcher.Updated += (_, update) =>
{
    DeviceLogger.Log(
        "Updated",
        update.Id,
        null,
        update.Properties.ToDictionary(
            x => x.Key,
            x => x.Value ?? "null"));
};

watcher.Removed += (_, remove) =>
{
    DeviceLogger.Log(
        "Removed",
        remove.Id,
        null);
};

watcher.EnumerationCompleted += (_, _) =>
{
    Console.WriteLine("Initial enumeration completed.");
};

watcher.Stopped += (_, _) =>
{
    Console.WriteLine("Watcher stopped.");
};

//
// PNP WATCHER
//
var pnpProps = new[]
{
    "System.Devices.Present",
    "System.Devices.ContainerId"
};

PnpObjectWatcher pnpWatcher =
    PnpObject.CreateWatcher(
        PnpObjectType.Device,
        pnpProps);

pnpWatcher.Added += (_, obj) =>
{
    DeviceLogger.Log(
        "PnpAdded",
        obj.Id,
        null,
        obj.Properties.ToDictionary(
            x => x.Key,
            x => x.Value ?? "null"));
};

pnpWatcher.Updated += (_, update) =>
{
    DeviceLogger.Log(
        "PnpUpdated",
        update.Id,
        null,
        update.Properties.ToDictionary(
            x => x.Key,
            x => x.Value ?? "null"));
};

pnpWatcher.Removed += (_, remove) =>
{
    DeviceLogger.Log(
        "PnpRemoved",
        remove.Id,
        null);
};

watcher.Start();
pnpWatcher.Start();

Console.WriteLine();
Console.WriteLine("Monitoring...");
Console.WriteLine("Accendi e spegni il dispositivo.");
Console.WriteLine("Premi ENTER per terminare.");

Console.ReadLine();

watcher.Stop();
pnpWatcher.Stop();