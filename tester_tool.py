import can
import time
import sys
import traceback
import os
import click # Make sure click is installed: pip install click

# --- Configuration for UDS messages ---
# UDS Request ID (physical addressing)
# Common request ID for a single ECU. Response ID is usually Request_ID + 8.
REQUEST_ID = 0x7E0

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

# --- Custom CAN Listener for printing received messages ---
class SummaryListener(can.Listener):
    """
    A simple listener that prints a one-line summary of received CAN messages.
    """
    def on_message_received(self, msg: can.Message) -> None:
        """
        Callback function for received messages.
        Prints a formatted one-line summary.
        """
        # Format: --> RX: ARB_ID [DLC] DATA_BYTES (e.g., --> RX: 7E8 [8] 01 02 03 04 05 06 07 08)
        data_str = ' '.join(f'{b:02X}' for b in msg.data)
        click.echo(f"--> RX: {msg.arbitration_id:03X} [{msg.dlc}] {data_str}")

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
    click.echo(f"<-- TX: {description}: {msg.arbitration_id:03X} [{msg.dlc}] {data_str}", err=True)
    bus_obj.send(msg)

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
def main(config_path: str | None, debug: bool):
    """
    Test Automation Tools CAN Diagnostic Session Tester.

    Sends a Diagnostic Session Control 10 03 and then continuously sends
    Tester Present (3E 00) messages to keep the session active.
    It also listens for and prints a one-line summary of all received CAN packets.
    """
    global bus, notifier # Declare global to ensure cleanup in finally block

    if debug:
        click.echo("Debug mode enabled.", err=True)
        # If you had a custom exception_hook, you would set it here:
        # sys.excepthook = partial(exception_hook, debug=debug)

    try:
        # 1. Initialize the CAN bus
        if config_path:
            click.echo(f"Attempting to connect to CAN bus using configuration from: {config_path}...", err=True)
            bus = can.interface.Bus(config=config_path)
        else:
            click.echo(f"Attempting to connect to CAN bus using default ~/.canrc...", err=True)
            bus = can.interface.Bus()

        click.echo(f"CAN bus connected successfully: {bus.channel_info}", err=True)

        # 2. Set up a notifier to listen for incoming messages
        listener = SummaryListener()
        notifier = can.Notifier(bus, [listener])
        click.echo("Listening for incoming CAN messages...", err=True)
        click.echo("Received messages will be printed above this line.", err=True)

        # 3. Send Diagnostic Session Control 10 03
        click.echo("\n--- Sending Diagnostic Session Control (10 03) ---", err=True)
        send_uds_message(bus, REQUEST_ID, [SESSION_CONTROL_SID, EXTENDED_SESSION_SUBFUNCTION],
                         "Diagnostic Session Control (Extended Session)")
        time.sleep(0.1) # Small delay for the bus to process

        # 4. Loop on Tester Present command indefinitely
        click.echo(f"\n--- Looping Tester Present (3E 00) every {TESTER_PRESENT_INTERVAL}s ---", err=True)
        click.echo("Press Ctrl+C to stop.", err=True)
        while True:
            send_uds_message(bus, REQUEST_ID, [TESTER_PRESENT_SID, TESTER_PRESENT_SUBFUNCTION],
                             "Tester Present")
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
    finally:
        # Ensure the notifier and bus are always shut down
        if notifier:
            click.echo("\nStopping CAN message notifier...", err=True)
            notifier.stop()
        if bus:
            click.echo("Shutting down CAN bus...", err=True)
            bus.shutdown()
            click.echo("CAN bus shut down.", err=True)
        sys.exit(0) # Exit cleanly after shutdown

if __name__ == "__main__":
    main()
