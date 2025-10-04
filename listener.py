import can
import click
import time
import sys
import traceback
import os

class SummaryListener(can.Listener):
    """
    A CAN listener that interprets known OBD-II/GM PIDs
    into human-friendly text.
    """
    def on_message_received(self, msg: can.Message) -> None:
        arb_id = msg.arbitration_id
        data = msg.data
        data_str = ' '.join(f'{b:02X}' for b in data)

        # Default: raw display
        display_line = f"--> RX: {arb_id:03X} [{msg.dlc}] {data_str}"

        # Standard OBD-II response to functional/physical request
        # Usually 0x7E8 = ECU response to 0x7E0
        if arb_id in (0x7E8, 0x7E9):
            try:
                if len(data) < 3:
                    click.echo(display_line)
                    return

                # Byte 0 = PCI (length), Byte 1 = Service + 0x40, Byte 2 = PID
                sid = data[1]
                pid = data[2]

                if sid == 0x41:  # Service 01 response (Show Current Data)
                    value_str = interpret_pid(pid, data[3:])
                    display_line += f"  →  {value_str}"

                elif sid == 0x62:  # Service 22 response (GM extended data)
                    value_str = interpret_gm_did(pid, data[3:])
                    display_line += f"  →  {value_str}"

            except Exception as e:
                display_line += f"  [Decode error: {e}]"

        click.echo(display_line)

def interpret_pid(pid: int, payload: bytes) -> str:
    """Decode standard OBD-II PIDs from Service 01 (0x41 responses)."""
    try:
        if pid == 0x0B:  # Intake Manifold Absolute Pressure
            kpa = payload[0]
            return f"MAP: {kpa} kPa"

        elif pid == 0x0C:  # Engine RPM
            rpm = ((payload[0] * 256) + payload[1]) / 4
            return f"Engine RPM: {rpm:.0f} rpm"

        elif pid == 0x0D:  # Vehicle Speed
            speed = payload[0]
            return f"Vehicle Speed: {speed} km/h"

        elif pid == 0x04:  # Engine Load
            load = payload[0] * 100.0 / 255.0
            return f"Engine Load: {load:.1f}%"

        elif pid == 0x05:  # Coolant Temp
            temp = payload[0] - 40
            return f"Coolant Temp: {temp} °C"

        elif pid == 0x46:  # Ambient Air Temp
            temp = payload[0] - 40
            return f"Ambient Air Temp: {temp} °C"

        elif pid == 0x11:  # Throttle Position
            throttle = payload[0] * 100.0 / 255.0
            return f"Throttle: {throttle:.1f}%"

        else:
            return f"Unknown PID 0x{pid:02X}, data={payload.hex().upper()}"

    except Exception as e:
        return f"PID decode error ({pid:02X}): {e}"


def interpret_gm_did(pid: int, payload: bytes) -> str:
    """
    Decode GM-specific Data Identifiers (Service 0x22 / 0x62 responses)
    Common DIDs include AFM, fuel trims, etc.
    """
    try:
        # AFM state – often DID 0x1167 or similar
        if pid in (0x11, 0x67):  # Example: Active Fuel Management State
            afm_state = payload[-1]  # Last byte usually indicates state
            if afm_state == 0:
                return "AFM: V8 mode"
            elif afm_state == 1:
                return "AFM: V4 mode"
            else:
                return f"AFM state unknown (0x{afm_state:02X})"

        # Intake manifold pressure (if GM extended PID)
        elif pid == 0x10:
            kpa = payload[0]
            return f"MAP (GM): {kpa} kPa"

        else:
            return f"GM DID 0x{pid:02X} data={payload.hex().upper()}"

    except Exception as e:
        return f"DID decode error ({pid:02X}): {e}"
