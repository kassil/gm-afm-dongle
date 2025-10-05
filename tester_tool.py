#!/home/kevin/.local/share/pipx/venvs/tat-cli/bin/python
from my_uds import SummaryListener
import my_uds

import time
import sys
import traceback
import os
import click # Make sure click is installed: pip install click

# --- Configuration for UDS messages ---
# UDS Request ID (physical addressing)
# Common request ID for a single ECU. Response ID is usually Request_ID + 8.
ECU_REQ_ID = 0x7E0

# UDS Service IDs and Sub-functions
# Diagnostic Session Control (10)
# Sub-function 03: Extended Diagnostic Session
SESSION_CONTROL_SID = 0x10
EXTENDED_SESSION_SUBFUNCTION = 0x03

# Tester Present (3E)
# Sub-function 00: Keep alive
TESTER_PRESENT_SID = 0x3E
TESTER_PRESENT_SUBFUNCTION = 0x00

# Delay between Tester Present messages (in seconds)
TESTER_PRESENT_INTERVAL = 2.0

# Global variables for the bus and notifier to ensure proper cleanup
bus = None
notifier = None

# --- Main CLI Command using click ---
@click.command()
@click.option(
    "--config",
    "config_path", # Internal variable name for the option
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to an alternative .canrc configuration file. If not provided, ~/.canrc is used.",
    default=None
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode for more detailed error reporting (prints full tracebacks).",
    default=False
)
@click.option("--simulate", is_flag=True, help="Run in simulation mode (no real CAN bus).")
def main(simulate: bool, config_path: str | None, debug: bool):
    """
    Test Automation Tools CAN Diagnostic Session Tester.

    Sends a Diagnostic Session Control 10 03 and then continuously sends
    Tester Present (3E 00) messages to keep the session active.
    It also listens for and prints a one-line summary of all received CAN packets.
    """
    bus = None
    notifier = None
    if debug:
        click.echo("Debug mode enabled.", err=True)
        # If you had a custom exception_hook, you would set it here:
        # sys.excepthook = partial(exception_hook, debug=debug)

    try:
        # 1. Initialize the CAN bus
        if simulate:
            click.echo("Running in simulation mode (random CAN frames).")
            import sim_can as can
        else:
            import can

        if config_path and not simulate:
            click.echo(f"Connecting to CAN bus using configuration file {config_path}...", err=True)
            bus = can.interface.Bus(config=config_path)
            click.echo(f"CAN bus connected successfully: {bus.channel_info}", err=True)
        else:
            click.echo(f"Connecting to CAN bus...", err=True)
            bus = can.interface.Bus()
            click.echo(f"CAN bus connected successfully: {bus.channel_info}", err=True)

        # --- UDS Message Sending Helper ---
        def send_uds_message(bus_obj: can.Bus, arb_id: int, data_bytes: list, description: str = ""):
            """
            Constructs and sends a CAN message with UDS data.
            For single-frame UDS requests, the first byte is the PCI (Protocol Control Information) byte.
            0x02 indicates 2 bytes of data follow (the SID and sub-function).
            """
            uds_data = [0x02, data_bytes[0], data_bytes[1]]
            msg = can.Message(arbitration_id=arb_id,
                            data=uds_data,
                            is_extended_id=False) # Standard 11-bit CAN ID
            data_str = ' '.join(f'{b:02X}' for b in msg.data)
            click.echo(f"Tx {my_uds.decode_ecu(arb_id)} {description}: [{msg.dlc}] {data_str}")
            bus_obj.send(msg)

        # 2. Set up a notifier to listen for incoming messages
        listener = SummaryListener()
        notifier = can.Notifier(bus, [listener])
        click.echo("Listening for incoming CAN messages...", err=True)
        click.echo("Received messages will be printed above this line.", err=True)

        # 3. Send Diagnostic Session Control 10 03
        click.echo("\n--- Sending Diagnostic Session Control (10 03) ---", err=True)
        send_uds_message(bus, ECU_REQ_ID, [SESSION_CONTROL_SID, EXTENDED_SESSION_SUBFUNCTION],
                         "Diagnostic Session Control (Extended Session)")
        time.sleep(0.1) # Small delay for the bus to process

        # 4. Loop on Tester Present command indefinitely
        click.echo(f"\n--- Looping Tester Present (3E 00) every {TESTER_PRESENT_INTERVAL}s ---", err=True)
        click.echo("Press Ctrl+C to stop.", err=True)

        # Periodic data polling loop
        IDS_TO_POLL = [
            (0x7E0, 0x01, 0x0C), # "Engine RPM"),
            (0x7E0, 0x01, 0x0D), # "Vehicle Speed"),
            (0x7E0, 0x01, 0x0B), # "Intake MAP"),
            (0x7E0, 0x01, 0x04), # "Engine Load"),
            (0x7E0, 0x01, 0x05), # "Coolant Temp"),
            (0x7E0, 0x01, 0x0F), # "Intake Air Temp"),
            (0x7E0, 0x01, 0x10), # "MAF Air Flow"),
            (0x7E0, 0x01, 0x11), # "Throttle Position"),
            (0x7E0, 0x01, 0x06), # "Short Term Fuel Trim B1"),
            (0x7E0, 0x01, 0x07), # "Long Term Fuel Trim B1"),
            (0x7E0, 0x01, 0x46), # "Ambient Air Temp"),
            (0x7E0, 0x01, 0x33), # "Barometric Pressure"),
            # Optional GM DIDs (if supported)
            (0x7E0, 0x22, 0xF40C), # "GM Engine Load (Alt)"),
            (0x7E0, 0x22, 0xF41F), # "GM AFM Active"),
        ]
        while True:
            # Send tester present
            send_uds_message(bus, ECU_REQ_ID, [TESTER_PRESENT_SID, TESTER_PRESENT_SUBFUNCTION], "Tester Present")
            # Send standard OBD-II PID requests
            for arb_id, sid, pid in IDS_TO_POLL:
                if pid <= 0xFF:
                    # Standard OBD-II PID (8-bit)
                    data = [0x02, sid, pid]
                else:
                    # Extended 16-bit DID (e.g., GM-specific Mode 0x22)
                    data = [0x03, sid, (pid >> 8) & 0xFF, pid & 0xFF]
                lookup = my_uds.search_list(arb_id, pid, my_uds.DID_LIST if sid==0x22 else my_uds.PID_LIST)
                name = lookup[0]
                msg = can.Message(
                    arbitration_id=arb_id,
                    data=data,
                    is_extended_id=False
                )
                data_str = ' '.join(f'{b:02X}' for b in msg.data)
                ecu = my_uds.decode_ecu(arb_id)
                click.echo(f"Tx {ecu} {name}: [{msg.dlc}] {data_str}")
                bus.send(msg)
                time.sleep(0.05)  # Small gap between requests
            time.sleep(TESTER_PRESENT_INTERVAL)


    except FileNotFoundError as e:
        click.echo(f"Configuration Error: {e}", err=True)
        sys.exit(1)
    except can.exceptions.CanError as e:
        click.echo(f"\n--- CAN Error Detected! ---", err=True)
        click.echo(f"Error Type: {type(e).__name__}", err=True)
        click.echo(f"Error Message: {e}", err=True)
        if debug:
            click.echo("\n--- Traceback ---", err=True)
            traceback.print_exc(file=sys.stderr) # Print traceback to stderr only if debug
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n--- Script stopped by user (Ctrl+C) ---", err=True)
    except Exception as e:
        click.echo(f"\n--- General Error Detected! ---", err=True)
        click.echo(f"Error Type: {type(e).__name__}", err=True)
        click.echo(f"Error Message: {e}", err=True)
        if debug:
            click.echo("\n--- Traceback ---", err=True)
            traceback.print_exc(file=sys.stderr) # Print traceback to stderr only if debug
        sys.exit(1)
    finally: #SystemExit goes here
        # Ensure the notifier and bus are always shut down
        if notifier:
            click.echo("\nStopping CAN message notifier...", err=True)
            notifier.stop()
        if bus:
            click.echo("Shutting down CAN bus...", err=True)
            bus.shutdown()
        click.echo("Finally, goodbye", err=True)
        sys.exit(0) # Exit cleanly after shutdown

if __name__ == "__main__":
    main()
