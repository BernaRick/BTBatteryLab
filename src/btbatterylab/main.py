from btbatterylab.models.device import Device


def main() -> None:

    demo_device = Device(
        id="demo",
        name="OPPO Enco Air2",
        device_type="Headset",
        vendor="OPPO",
    )

    print("BTBatteryLab")
    print("----------------")

    print(f"Device: {demo_device.name}")
    print(f"Type: {demo_device.device_type}")
    print(f"Vendor: {demo_device.vendor}")


if __name__ == "__main__":
    main()