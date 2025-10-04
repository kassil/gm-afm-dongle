# CAN Diagnostic Session Tester

A Python-based command-line interface (CLI) tool for establishing and maintaining a diagnostic session on a CAN bus using `python-can` and `click`. It's particularly useful for interacting with ECUs that require a constant "Tester Present" message to keep an extended diagnostic session active.

## Table of Contents

-   [Features](#features)
-   [Dependencies](#dependencies)
-   [Installation](#installation)
-   [Configuration](#configuration)
-   [Usage](#usage)
-   [Example Output](#example-output)
-   [UDS Basics](#uds-basics)

## Features

*   **Diagnostic Session Control**: Initiates an Extended Diagnostic Session (`10 03`).
*   **Tester Present Loop**: Continuously sends "Tester Present" (`3E 00`) messages at a defined interval to prevent the diagnostic session from timing out.
*   **CAN Message Monitoring**: Listens for all incoming CAN messages and prints a one-line summary of each received packet.
*   **Flexible Configuration**: Supports custom `python-can` configuration files (`.canrc`) via a command-line argument, or automatically uses the default `~/.canrc`.
*   **Debug Mode**: Provides detailed tracebacks for errors when enabled.
*   **Graceful Shutdown**: Handles `Ctrl+C` to cleanly shut down the CAN bus and notifier.

## Dependencies

This tool relies on the following:

### Python Packages

*   **`python-can`**: The primary library for CAN communication in Python.
    *   Installation: `pip install python-can`
    *   Some source suggest install `python-can` wwith the `neovi` extras: `pip install python-can[neovi]`
*   **`click`**: A library for creating beautiful command-line interfaces.
    *   Installation: `pip install click`

### Hardware-Specific Drivers

If you are using an Intrepid Control Systems device like a ValueCAN4 (which uses the `neovi` interface in `python-can`), you will also need:

*   **Intrepid Control Systems API/Drivers**: These are native drivers (e.g., `icsneo40.dll` on Windows, `libicsneo40.so` on Linux) provided by Intrepid. They are typically installed via:
    *   **Windows**: Installing Vehicle Spy or the "neoVI API Setup" from Intrepid's website.
    *   **Linux**: Installing the Intrepid Linux SDK and ensuring `libicsneo40.so` is discoverable (e.g., in `/usr/local/lib` or via `LD_LIBRARY_PATH`).
*   **`ics` Python Package**: This is the official Python binding for the Intrepid API, often bundled with their SDKs or available via `pip`. `python-can`'s `neovi` backend uses this package.

## Installation

1.  **Clone this repository** (or save the script as `diag_tester.py`).

2.  **Set up a Python environment** (recommended using `pipx` for CLI tools):

    ```bash
    # If you don't have pipx
    pip install pipx
    pipx ensurepath

    # Create a new pipx environment and install the dependencies
    # Assuming your script is named diag_tester.py and is in the current directory
    pipx install --python python3.12 .
    # Or, if you prefer to just install packages in an existing pipx venv:
    # pipx inject your_venv_name python-can click
    ```
    *Replace `python3.12` with your desired Python version.*
    *If you don't use `pipx`, a standard `venv` or system-wide `pip install` will also work.*

3.  **Install Intrepid Drivers**: Follow the instructions from Intrepid Control Systems for your operating system to install the necessary drivers and the `ics` Python package. Verify that `python-can` can find them (running the tool will usually tell you if it can't).

## Configuration

This tool uses `python-can`'s flexible configuration system.

### `~/.canrc` (Default)

By default, `python-can` looks for a configuration file at `~/.canrc` (or `CAN_RC` environment variable). A typical configuration for a ValueCAN4 might look like this:

```ini
# ~/.canrc
[default]
interface = neovi
serial = V27840  ; Replace with your device's serial number
channel = 1     ; Use CAN channel 1 (adjust if your device uses a different channel)
baudrate = 2000000 ; Set to your desired CAN bus baud rate (e.g., 500000 for 500kbps)
