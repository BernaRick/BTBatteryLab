using System.Collections.Concurrent;
using System.Text.Json;

namespace BluetoothWatcher;

public static class DeviceLogger
{
    private static readonly string LogFile =
        Path.Combine(
            AppContext.BaseDirectory,
            $"device-watch-{DateTime.Now:yyyyMMdd-HHmmss}.jsonl");

    private static readonly ConcurrentDictionary<string,
        Dictionary<string, string>> LastState = new();

    public static void Log(
        string eventType,
        string id,
        string? name,
        IDictionary<string, object>? properties = null)
    {
        var transitions = new List<object>();

        if (properties != null)
        {
            var currentState =
                LastState.GetOrAdd(id, _ => new Dictionary<string, string>());

            lock (currentState)
            {
                foreach (var property in properties)
                {
                    string key = property.Key;
                    string newValue = property.Value?.ToString() ?? "null";

                    if (currentState.TryGetValue(key, out var oldValue))
                    {
                        if (!string.Equals(
                                oldValue,
                                newValue,
                                StringComparison.Ordinal))
                        {
                            transitions.Add(new
                            {
                                Property = key,
                                OldValue = oldValue,
                                NewValue = newValue
                            });
                        }
                    }
                    else
                    {
                        transitions.Add(new
                        {
                            Property = key,
                            OldValue = "(unset)",
                            NewValue = newValue
                        });
                    }

                    currentState[key] = newValue;
                }
            }
        }

        var logEntry = new
        {
            Timestamp = DateTime.Now,
            Event = eventType,
            Id = id,
            Name = name,
            Properties = properties,
            Transitions = transitions
        };

        string json = JsonSerializer.Serialize(
            logEntry,
            new JsonSerializerOptions
            {
                WriteIndented = false
            });

        File.AppendAllText(
            LogFile,
            json + Environment.NewLine);

        Console.WriteLine();
        Console.WriteLine($"[{eventType}] {name ?? id}");

        if (transitions.Count > 0)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;

            foreach (dynamic t in transitions)
            {
                Console.WriteLine(
                    $"  {t.Property}: {t.OldValue} -> {t.NewValue}");
            }

            Console.ResetColor();
        }
    }

    public static void RemoveDevice(string id)
    {
        LastState.TryRemove(id, out _);
    }
}