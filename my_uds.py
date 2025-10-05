import can
import click
import time
import sys
import traceback
import os

import struct
DID_NAMES = {
    # Powertrain / Engine control
    0x1000: "ECU Identification",
    0x1001: "VIN (Vehicle Identification Number)",
    0x1003: "Calibration ID",
    0x1005: "ECU Serial Number",
    0x1010: "ECU Software Version",
    0x1100: "Engine Speed (RPM)",
    0x1101: "Vehicle Speed",
    0x1102: "Throttle Position",
    0x1103: "Intake Manifold Pressure (MAP)",
    0x1104: "Engine Load",
    0x1105: "Mass Air Flow (MAF)",
    0x1106: "Intake Air Temperature",
    0x1107: "Coolant Temperature",
    0x1108: "Barometric Pressure",
    0x1110: "Fuel Rail Pressure",
    0x1111: "Fuel Pump Command",
    0x1112: "Oil Pressure",
    0x1113: "Oil Temperature",

    # GM-specific / AFM-related
    0x1900: "AFM Active Cylinders Mask",
    0x1901: "AFM Mode Active (Yes/No)",
    0x1902: "AFM Commanded State",
    0x1903: "AFM Transition Counter",
    0x1904: "AFM Desired Cylinder Torque",
    0x1905: "AFM Actual Cylinder Torque",
    0x1906: "AFM Intake Manifold Pressure",
    0x1907: "AFM Estimated Fuel Savings",
    0x1910: "AFM Fault Status",
    0x1911: "AFM Enable Criteria Satisfied",
    0x1912: "AFM Disable Reason",

    # Transmission / Chassis
    0x2000: "Transmission Gear Position",
    0x2001: "Transmission Oil Temp",
    0x2002: "Converter Clutch Command",
    0x2003: "Vehicle Speed Sensor",
    0x2010: "Brake Pedal Position",
    0x2011: "Accelerator Pedal Position",
    0x2020: "Steering Angle",
    0x2021: "Yaw Rate",

    # Environmental / Misc
    0x3000: "Ambient Air Temperature",
    0x3001: "Battery Voltage",
    0x3002: "Alternator Load",
    0x3003: "Odometer Reading",
    0x3004: "Ignition Status",

    0xF40C: "GM Engine Load (Alt)",
    0xF41F: "GM AFM Active",
}

PID_NAMES = {
    0x04: "Calculated Engine Load",
    0x05: "Coolant Temperature",
    0x06: "Short Term Fuel Trim (Bank 1)",
    0x07: "Long Term Fuel Trim (Bank 1)",
    0x08: "Short Term Fuel Trim (Bank 2)",
    0x09: "Long Term Fuel Trim (Bank 2)",
    0x0A: "Fuel Pressure",
    0x0B: "Intake Manifold Pressure",
    0x0C: "Engine RPM",
    0x0D: "Vehicle Speed",
    0x0E: "Timing Advance",
    0x0F: "Intake Air Temperature",
    0x10: "MAF Air Flow Rate",
    0x11: "Throttle Position",
    0x1F: "Run Time Since Engine Start",
    0x21: "Distance Traveled with MIL On",
    0x2F: "Fuel Level Input",
    0x33: "Barometric Pressure",
    0x46: "Ambient Air Temperature",
    0x5C: "Engine Oil Temperature",
    0x5E: "Engine Fuel Rate",
}

ECU_NAMES = {
    # Powertrain / standard UDS IDs
    0x7E0: "ECM", # Engine Control Module)",
    0x7E1: "TCM", # (Transmission Control Module)",
    0x7E2: "ABS / EBCM (Brake Control)",
    0x7E3: "SRS / Airbag Module",
    0x7E4: "BCM (Body Control Module)",
    0x7E5: "IPC (Instrument Cluster)",
    0x7E6: "HVAC / Climate Control",
    0x7E7: "Gateway / Diagnostic Manager",

    # Some GM and SAE tools use 0x77x range instead of 0x7Ex
    0x77E: "ECM (alt address, Powertrain)",
    0x77F: "TCM (alt address, Transmission)",
    0x771: "ABS (alt address)",
    0x772: "SRS (alt address)",
    0x773: "BCM (alt address)",
    0x774: "IPC (alt address)",
    0x775: "HVAC (alt address)",
    0x776: "Gateway (alt address)",

    # Non-diagnostic broadcast frames seen on GM CAN
    # Common runtime broadcast frames (Powertrain / Chassis / Body)
    0x0C9: "SDM", #SDM (Airbag Module)
    0x0F9: "BCM / Gateway Keepalive",
    0x199: "ECM Torque / Throttle Position",
    0x19D: "ECM Accelerator Pedal / Torque Request",
    0x12A: "ECM Fuel / Airflow Data",
    0x138: "ECM Lambda / AFR Sensor Data",
    0x17D: "Transmission / Torque Converter Status",
    0x17F: "Transmission / Gear Status",
    0x1CB: "BCM / Lighting / Accessory Data",
    0x1CD: "IPC (Cluster Display Data)",
    0x1E9: "ECM Engine Data (RPM, Torque)",
    0x1EB: "ECM Cruise / Idle Control",
    0x1ED: "ECM Engine Load / Knock Info",
    0x2F9: "ABS / Wheel Speed Data",
    0x348: "Chassis Sensor Cluster",
    0x34A: "Chassis / Yaw / Accel Data",
    0x3C9: "SDM (Airbag Module)",
    0x3E9: "ECM Misc Sensor Data",
    0x3F9: "ECM Sensor Fusion Data",
    0x3FB: "ECM / Fuel Trim Info",
    0x3FD: "IPC / Cluster Keepalive",
    0x4C9: "ABS Brake Pressure Data",
    0x4D9: "ABS / Yaw Sensor Data",
    0x4E9: "Steering Angle / Column Sensor",
    0x528: "Transfer Case / 4WD Control",
    0x52A: "Suspension / Ride Height / Damping",
}

def decode_pid(pid, payload):
    try:
        A, B = payload[0], payload[1] if len(payload) > 1 else 0
        if pid == 0x0C:  # RPM
            return f"{((A * 256) + B) / 4:.0f} rpm"
        elif pid == 0x0D:  # Speed
            return f"{A} km/h"
        elif pid == 0x0B:  # MAP
            return f"{A} kPa"
        elif pid == 0x04:  # Load
            return f"{A * 100 / 255:.1f}%"
        elif pid == 0x05:  # Coolant temp
            return f"{A - 40} °C"
        elif pid == 0x0F:  # Intake air temp
            return f"{A - 40} °C"
        elif pid == 0x10:  # MAF
            return f"{((A * 256) + B) / 100:.2f} g/s"
        elif pid == 0x11:  # Throttle
            return f"{A * 100 / 255:.1f}%"
    except Exception:
        pass
    return None

def decode_did(did, payload):
    if did == 0xF41F:
        return "Active" if payload[0] else "Inactive"
    elif did == 0xF40C:
        val = (payload[0] << 8 | payload[1]) / 10.0
        return f"{val:.1f}%"
    return None

# --- Human-friendly CAN frame decoder for GMT900 Tahoe ---
def decode_frame(msg):

    if msg.arbitration_id in ARB_DECODERS:
        return ARB_DECODERS[msg.arbitration_id](msg.data)
    return "Raw " + " ".join(f"{b:02X}" for b in msg.data)

def decode_ecu(arb_id) -> str:
    # Direction: 0x08 bit toggles request vs. response
    dir = '<--' if (arb_id & 0x08) else '-->'
    # Normalize the ID for lookup (clear bit 3)
    ecu = ECU_NAMES.get(arb_id & 0xFFF7, ECU_NAMES.get(arb_id | 0x08, f"{arb_id:03X}")) # Unknown ECU
    return f"{dir} {ecu}"

def decode_7E8_7E9(data: bytes) -> str:
    """Interpret UDS or OBD-II response frames from ECM (0x7E8) or TCM (0x7E9)."""
    if not data:
        return None

    # Response to Mode 0x01 (0x41)
    if data[0] == 0x04 and data[1] == 0x41:
        pid = data[2]
        payload = data[3:]
        value = decode_pid(pid, payload)
        if value is not None:
            return f"{PID_NAMES.get(pid, f'PID 0x{pid:02X}')}: {value}"
        else:
            return f"PID 0x{pid:02X} -> {payload}"

    # Response to Mode 0x22 (manufacturer-specific)
    # UDS 0x22 Read Data By Identifier
    elif data[0] >= 3 and data[1] == 0x62:
        did_hi, did_lo = data[2], data[3]
        did = (did_hi << 8) | did_lo
        payload = data[4:]
        value = decode_did(did, payload)
        if value is not None:
            return f"{DID_NAMES.get(did, f'DID 0x{did:04X}')}: {value}"
        else:
            return f"DID 0x{did:04X} -> {payload}"

def decode_0C9(data: bytes) -> str:
    """Decode GM SDM (Airbag / Accel sensor) frame 0x0C9."""
    if len(data) < 7:
        return "Invalid SDM frame length"

    long_accel = int.from_bytes(data[0:2], 'big', signed=True) * 0.01  # m/s²
    lat_accel  = int.from_bytes(data[2:4], 'big', signed=True) * 0.01
    yaw_rate   = int.from_bytes(data[4:5], 'big', signed=True) * 1.5   # °/s
    status     = data[5]
    counter    = data[6]

    ignition_on = bool(status & 0x40)
    crash_flag  = bool(status & 0x08)

    return (f"Longitudinal={long_accel:+.2f} m/s², "
            f"Lateral={lat_accel:+.2f} m/s², "
            f"Yaw={yaw_rate:+.1f}°/s, "
            f"Ignition={'On' if ignition_on else 'Off'}, "
            f"Crash={'Yes' if crash_flag else 'No'}, "
            f"Counter={counter}")


ARB_DECODERS = {
    0x0C9: decode_0C9,
    0x7E8: decode_7E8_7E9,
    0x7E9: decode_7E8_7E9,
}


class SummaryListener(can.Listener):
    """
    A CAN listener that interprets known OBD-II/GM PIDs
    into human-friendly text.
    """
    def on_message_received(self, msg: can.Message) -> None:
        if msg.arbitration_id & 0x08 == 0:
            # Requests silent
            return
        decoded = decode_frame(msg)
        ecu_name = decode_ecu(msg.arbitration_id)
        if decoded:
            click.echo(f"    Rx {ecu_name} [{msg.dlc}] {decoded}")
        else:
            data_str = ' '.join(f'{b:02X}' for b in msg.data)
            click.echo(f"    Rx {ecu_name} [{msg.dlc}] {data_str}")

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
