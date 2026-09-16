from btbatterylab.collector.unified_collector import UnifiedCollector


def main() -> None:
    collector = UnifiedCollector(
        jsonl_path=(
            r"C:\Users\PatrickBernardoni\OneDrive - Patrick Bernardoni"
            r"\Documents\BTBatteryLabData\ble-events.jsonl"
        ),
        # Il polling PnP e' lento (decine di secondi con 5 device
        # accoppiati): ogni 5 minuti e' un buon compromesso per ora,
        # va rivisto quando ci sara' un sistema di configurazione.
        poll_interval_seconds=300.0,
    )

    try:
        collector.start()

    except KeyboardInterrupt:
        collector.stop()


if __name__ == "__main__":
    main()
