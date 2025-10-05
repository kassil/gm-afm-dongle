# TODO Maybe rename to decode_functions
import can
import click
import os
import struct
import sys
import time
import traceback
from typing import Callable, List, Tuple, Union

CanMsgData = Union[bytes, bytearray] # can.Message.data

def decode_pressure(data: CanMsgData) -> str:
    if len(data) < 1:
        raise ValueError("Pressure PID expects ≥1 byte payload")
    return f"{data[0]} kPa"
def decode_rpm(data: CanMsgData) -> str:
    if len(data) < 2:
        raise ValueError("RPM PID expects ≥2 byte payload")
    rpm = ((data[0] << 8) | data[1]) / 4
    return f"{rpm:.0f} rpm"
def decode_speed(data: CanMsgData) -> str:
    if len(data) < 1:
        raise ValueError("Speed PID expects ≥1 byte payload")
    return f"{data[0]} km/h"
def decode_percent(data: CanMsgData) -> str:
    if len(data) < 1:
        raise ValueError("Percent PID expects ≥1 byte payload")
    return f"{data[0] * 100.0 / 255.0:.1f} %"
def decode_temp(data: CanMsgData) -> str:
    if len(data) < 1:
        raise ValueError("Temperature PID expects ≥1 byte payload")
    return f"{data[0] - 40} °C"
def decode_voltage(data: CanMsgData) -> str:
    if len(data) < 1:
        raise ValueError("Voltage expects ≥1 byte payload")
    return f"{data[0] / 10:.1f} V"
def decode_generic(data: CanMsgData) -> str:
    return " ".join(f"{b:02X}" for b in data)
def decode_yes_no(data: CanMsgData) -> str:
    if len(data) < 1:
        raise ValueError("Boolean field expects ≥1 byte payload")
    return "Yes" if data[0] else "No"

# Call this to search for a PID or DID
search_list = lambda arb_id, pid, id_list: next((v for k, v in id_list if k == (arb_id, pid)), None)

# Mode 1 Parameter ID (PID)
PID_LIST: List[Tuple[Tuple[int, int], Tuple[str, str, Callable[[CanMsgData], str]]]] = [
    ((0x7E0, 0x04), ("Calculated Engine Load", "Engine load as a percentage", decode_percent)),
    ((0x7E0, 0x05), ("ECT", "Engine coolant temperature", decode_temp)),
    ((0x7E0, 0x06), ("STFT B1", "Bank 1 short-term fuel trim", decode_percent)),
    ((0x7E0, 0x07), ("LTFT B1", "Bank 1 long-term fuel trim", decode_percent)),
    ((0x7E0, 0x08), ("STFT B2", "Bank 2 short-term fuel trim", decode_percent)),
    ((0x7E0, 0x09), ("LTFT B2", "Bank 2 long-term fuel trim", decode_percent)),
    ((0x7E0, 0x0A), ("FP", "Fuel rail pressure", decode_pressure)),
    ((0x7E0, 0x0B), ("MAP", "Intake manifold pressure in kPa", decode_pressure)),
    ((0x7E0, 0x0C), ("RPM", "Engine speed in revolutions per minute", decode_rpm)),
    ((0x7E0, 0x0D), ("VSS", "Vehicle speed in km/h", decode_speed)),
    ((0x7E0, 0x0E), ("Timing Advance", "Ignition timing advance before TDC", decode_generic)),
    ((0x7E0, 0x0F), ("Intake Air Temperature", "Temperature of air entering engine", decode_temp)),
    ((0x7E0, 0x10), ("MAF", "Mass air flow rate into engine", decode_generic)),
    ((0x7E0, 0x11), ("TPS", "Throttle position sensor", decode_percent)),
    ((0x7E0, 0x46), ("AAT", "Outside air temperature", decode_temp)),
    ((0x7E0, 0x1F), ("Run Time Since Engine Start", "Elapsed time since engine started", decode_generic)),
    ((0x7E0, 0x21), ("Distance with MIL On", "Distance traveled with MIL on", decode_generic)),
    ((0x7E0, 0x2F), ("Fuel Level Input", "Fuel level as a percentage", decode_percent)),
    ((0x7E0, 0x33), ("Barometric Pressure", "Ambient barometric pressure", decode_pressure)),
    ((0x7E0, 0x46), ("Ambient Air Temperature", "Outside air temperature", decode_temp)),
    ((0x7E0, 0x5C), ("Engine Oil Temperature", "Temperature of engine oil", decode_temp)),
    ((0x7E0, 0x5E), ("Engine Fuel Rate", "Fuel consumption rate", decode_generic)),
]
# UDS Data By Identifer (DID)
DID_LIST: List[Tuple[Tuple[int, int], Tuple[str, str, Callable[[CanMsgData], str]]]] = [
    ((0x7E0, 0x1000), ("ECU Identification", "ECU hardware and software identifiers", decode_generic)),
    ((0x7E0, 0x1001), ("VIN", "Vehicle Identification Number", decode_generic)),
    ((0x7E0, 0x1003), ("Calibration ID", "Software calibration identifier", decode_generic)),
    ((0x7E0, 0x1005), ("ECU Serial Number", "Unique ECU serial number", decode_generic)),
    ((0x7E0, 0x1010), ("ECU Software Version", "Software version of ECU", decode_generic)),
    ((0x7E0, 0x1100), ("Engine Speed", "Current engine speed (RPM)", decode_rpm)),
    ((0x7E0, 0x1101), ("Vehicle Speed", "Vehicle speed in km/h", decode_speed)),
    ((0x7E0, 0x1102), ("Throttle Position", "Throttle angle position", decode_percent)),
    ((0x7E0, 0x1103), ("Intake Manifold Pressure", "Intake manifold pressure", decode_pressure)),
    ((0x7E0, 0x1104), ("Engine Load", "Engine load as a percentage", decode_percent)),
    ((0x7E0, 0x1105), ("Mass Air Flow", "Mass air flow rate", decode_generic)),
    ((0x7E0, 0x1106), ("Intake Air Temperature", "Temperature of intake air", decode_temp)),
    ((0x7E0, 0x1107), ("Coolant Temperature", "Engine coolant temperature", decode_temp)),
    ((0x7E0, 0x1108), ("Barometric Pressure", "Atmospheric pressure", decode_pressure)),
    ((0x7E0, 0x1110), ("Fuel Rail Pressure", "Fuel rail pressure", decode_pressure)),
    ((0x7E0, 0x1111), ("Fuel Pump Command", "Fuel pump control signal", decode_percent)),
    ((0x7E0, 0x1112), ("Oil Pressure", "Measured engine oil pressure", decode_pressure)),
    ((0x7E0, 0x1113), ("Oil Temperature", "Measured oil temperature", decode_temp)),
    # AFM / GM-specific group
    ((0x7E0, 0x1900), ("AFM Active Cylinders Mask", "Active cylinder bitmask", decode_generic)),
    ((0x7E0, 0x1901), ("AFM Mode Active", "Indicates if AFM is currently active", decode_yes_no)),
    ((0x7E0, 0x1902), ("AFM Commanded State", "AFM commanded on/off state", decode_yes_no)),
    ((0x7E0, 0x1903), ("AFM Transition Counter", "Counts AFM on/off transitions", decode_generic)),
    ((0x7E0, 0x1904), ("AFM Desired Cylinder Torque", "Desired torque in AFM mode", decode_generic)),
    ((0x7E0, 0x1905), ("AFM Actual Cylinder Torque", "Measured torque in AFM mode", decode_generic)),
    ((0x7E0, 0x1906), ("AFM Intake Manifold Pressure", "MAP during AFM mode", decode_pressure)),
    ((0x7E0, 0x1907), ("AFM Estimated Fuel Savings", "Estimated fuel saved by AFM", decode_percent)),
    ((0x7E0, 0x1910), ("AFM Fault Status", "Current AFM fault state", decode_generic)),
    ((0x7E0, 0x1911), ("AFM Enable Criteria Satisfied", "If AFM enable conditions are met", decode_yes_no)),
    ((0x7E0, 0x1912), ("AFM Disable Reason", "Reason AFM disabled", decode_generic)),

    ((0x7E0, 0x2000), ("Gear Position", "Transmission gear selection", decode_generic)),
    ((0x7E0, 0x2001), ("Trans Oil Temp", "Transmission oil temperature", decode_temp)),
    ((0x7E0, 0x2002), ("Clutch Command", "Torque converter clutch command", decode_generic)),
    ((0x7E0, 0x2003), ("VSS", "Vehicle speed sensor reading", decode_speed)),
    ((0x7E0, 0x2010), ("Brake Pedal Pos", "Brake pedal position sensor", decode_percent)),
    ((0x7E0, 0x2011), ("Accel Pedal Pos", "Accelerator pedal position sensor", decode_percent)),
    ((0x7E0, 0x2020), ("Steering Angle", "Current steering wheel angle", decode_generic)),
    ((0x7E0, 0x2021), ("Yaw Rate", "Vehicle yaw rate", decode_generic)),
    # Environmental / Misc
    ((0x7E0, 0x3000), ("Ambient Temp", "Outside air temperature", decode_temp)),
    ((0x7E0, 0x3001), ("Battery Voltage", "System voltage", decode_voltage)),
    ((0x7E0, 0x3002), ("Alternator Load", "Alternator output load", decode_percent)),
    ((0x7E0, 0x3003), ("Odometer", "Total vehicle distance traveled", decode_generic)),
    ((0x7E0, 0x3004), ("Ignition Status", "Ignition key/run state", decode_generic)),
    # GM alternate / legacy
    ((0x7E0, 0xF40C), ("GM Engine Load (Alt)", "Alternate engine load calculation", decode_percent)),
    ((0x7E0, 0xF41F), ("GM AFM Active", "Active Fuel Management engaged", decode_yes_no)),
]

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

def decode_did(did: int, payload: CanMsgData):
    if did == 0xF41F:
        return "Active" if payload[0] else "Inactive"
    elif did == 0xF40C:
        val = (payload[0] << 8 | payload[1]) / 10.0
        return f"{val:.1f}%"
    return None

# --- Human-friendly CAN frame decoder for GMT900 Tahoe ---
def decode_frame(msg: can.Message):
    #TODO Mask response bit 3?
    if msg.arbitration_id in ARB_DECODERS:
        return ARB_DECODERS[msg.arbitration_id](msg)
    return "Raw " + " ".join(f"{b:02X}" for b in msg.data)

def decode_ecu(arb_id: int) -> str:
    # Direction: 0x08 bit toggles request vs. response
    dir = '<--' if (arb_id & 0x08) else '-->'
    # Normalize the ID for lookup (clear bit 3)
    req_id = arb_id & 0xFFF7
    resp_id = arb_id | 0x08
    ecu = ECU_NAMES.get(req_id, ECU_NAMES.get(resp_id, f"{arb_id:03X}")) # Unknown ECU
    return f"{dir} {ecu}"

def decode_7E8_7E9(msg: can.Message) -> str:
    """Interpret UDS or OBD-II response frames from ECM (0x7E8) or TCM (0x7E9)."""
    data = msg.data
    if not data:
        return None

    # TODO Check data[0] == len(data)

    # Response to Mode 0x01 (0x41)
    if data[0] == 0x04 and data[1] == 0x41:
        pid = data[2]
        # Assemble 16-bit integer
        payload = data[3:]
        value = (payload[0] << 8) | payload[1]  # Big-endian
        k = (msg.arbitration_id, pid)
        if k in PID_LIST:
            (name, _, decode_fn) = PID_LIST[k]
            value_str = decode_fn(value)
            return f"{name}: {value}"
        else:
            # Unknown ECU, PID combination
            data_str = ' '.join(f'{b:02X}' for b in msg.data)
            return f"PID {pid:04X} Raw {data_str}"

    # Response to Mode 0x22 (manufacturer-specific)
    # UDS 0x22 Read Data By Identifier
    elif data[0] >= 3 and data[1] == 0x62:
        # Assemble 16-bit integer
        payload = data[4:]
        value = (payload[0] << 8) | payload[1]  # Big-endian
        value = decode_did(did, payload)
        did = (data[2] << 8) | data[3]  # Big-endian
        k = (msg.arbitration_id, did)
        if k in DID_LIST:
            (name, _, decode_fn) = DID_LIST[k]
            value_str = decode_fn(value)
            return f"{name}: {value}"
        else:
            # Unknown ECU, DID combination
            data_str = ' '.join(f'{b:02X}' for b in msg.data)
            return f"DID {did:04X} Raw {data_str}"

def decode_0C9(msg) -> str:
    """Decode GM SDM (Airbag / Accel sensor) frame 0x0C9."""
    data = msg.data
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
            click.echo(f"Rx {ecu_name} [{msg.dlc}] {decoded}")
        else:
            data_str = ' '.join(f'{b:02X}' for b in msg.data)
            click.echo(f"Rx {ecu_name} [{msg.dlc}] {data_str}")

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
