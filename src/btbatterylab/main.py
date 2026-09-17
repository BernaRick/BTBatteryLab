import sys

from btbatterylab.collector.unified_collector import UnifiedCollector


def main() -> None:
    # Quando questo processo viene avviato in background da
    # BluetoothWatcher.exe (build standalone, vedi build_exe.bat)
    # invece che in una console interattiva, stdout/stderr non sono
    # piu' un terminale ma una pipe: Python passa automaticamente da
    # line-buffering a block-buffering, quindi i print() restano
    # bloccati in un buffer interno finche' non si riempie o il
    # processo termina - con poche righe al minuto, di fatto mai. Il
    # log risultava vuoto (o addirittura mai creato) per questo, non
    # per un problema nella logica di raccolta dati. Forziamo il
    # line-buffering sempre, cosi' ogni riga stampata arriva subito a
    # chi legge lo stdout, che sia una console vera o il file di log
    # di BluetoothWatcher.exe.
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

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
