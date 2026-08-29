using System.Text.Json;

namespace BluetoothWatcher;

public static class DeviceLogger
{
    private static readonly string LogFile =
        Path.Combine(AppContext.BaseDirectory,
            $"device-watch-{DateTime.Now:yyyyMMdd-HHmmss}.jsonl");

    public static void Log(string type,
                           string id,
                           string? name,
                           IDictionary<string, object>? properties = null)
    {
        var obj = new
        {
            Timestamp = DateTime.Now,
            Event = type,
            Id = id,
            Name = name,
            Properties = properties
        };

        string json = JsonSerializer.Serialize(obj);

        File.AppendAllText(LogFile, json + Environment.NewLine);

        Console.WriteLine(json);
    }
}