# Contributing to BTBatteryLab

First of all, thank you for your interest in contributing to BTBatteryLab.

The goal of this project is to provide a simple, powerful and vendor-neutral platform for Bluetooth battery monitoring and analytics on Windows.

Whether you are fixing bugs, improving documentation, testing devices, or proposing new features, your contribution is welcome.

---

# Ways to Contribute

You can contribute in several ways:

- Reporting bugs
- Suggesting features
- Improving documentation
- Testing Bluetooth devices
- Writing code
- Reviewing pull requests

---

# Reporting Bugs

When reporting a bug, please include:

- Windows version
- Device name
- Device manufacturer
- Steps to reproduce
- Expected behavior
- Actual behavior
- Log output (if available)

Example:

```text
Device: OPPO Enco Air2
Windows: Windows 11 24H2

Expected:
Battery percentage should update every few minutes.

Actual:
Battery remains unchanged.
```

---

# Suggesting Features

Feature requests are welcome.

Before opening a new feature request:

- Check existing issues
- Explain the use case
- Describe the expected outcome

Good feature requests are based on real user needs.

---

# Development Guidelines

## Code Style

Please follow:

- PEP 8
- Type hints whenever possible
- Clear naming conventions
- Small and focused functions

Example:

```python
def get_battery_percentage(device_id: str) -> int:
    pass
```

---

## Documentation

Documentation is a first-class citizen.

Whenever new functionality is added:

- Update README if needed
- Update documentation
- Add comments only when they provide useful context

---

## Testing

Before submitting a pull request:

- Verify the application runs correctly
- Verify existing functionality is not broken
- Test with real Bluetooth devices whenever possible

---

# Pull Requests

Before opening a pull request:

1. Create a dedicated branch
2. Keep changes focused
3. Write a meaningful description
4. Reference related issues

Example:

```text
Fixes #12
```

---

# Device Compatibility Reports

One of the most valuable contributions is reporting device compatibility.

Please include:

- Device name
- Manufacturer
- Device category
- Battery support status

Example:

```text
Device: OPPO Enco Air2
Category: Earbuds
Battery Detection: Supported
```

---

# Project Principles

BTBatteryLab follows a few important principles:

## Privacy First

No cloud dependency.

No telemetry.

Your data stays on your machine.

---

## Vendor Neutral

The project should work with any Bluetooth device exposing battery information.

---

## Open Source

All contributions are welcome and appreciated.

---

Thank you for helping improve BTBatteryLab ❤️
