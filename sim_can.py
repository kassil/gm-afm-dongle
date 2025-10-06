# sim_can.py
"""
Simulated CAN bus for offline testing and development.

Provides:
    - Bus: drop-in replacement for python-can's Bus
    - Notifier: drop-in replacement for python-can's Notifier

Supports random PID/DID simulation or playback from a log file.
"""

import random
import threading
import time
import queue
import types
from typing import List, Optional, Any

ONE_BYTE_PIDS = {
    0x04,  # Calculated Engine Load
    0x05,  # Engine Coolant Temperature
    0x06,  # Short Term Fuel Trim - Bank 1
    0x07,  # Long Term Fuel Trim - Bank 1
    0x08,  # Short Term Fuel Trim - Bank 2
    0x09,  # Long Term Fuel Trim - Bank 2
    0x0B,  # Intake Manifold Pressure
    0x0D,  # Vehicle Speed
    0x0E,  # Timing Advance
    0x0F,  # Intake Air Temperature
    0x11,  # Throttle Position
    0x2F,  # Fuel Level Input
    0x33,  # Barometric Pressure
    0x46,  # Ambient Air Temperature
    0x47,  # Absolute Throttle Position B
    0x48,  # Absolute Throttle Position C
    0x49,  # Accelerator Pedal Position D
    0x4A,  # Accelerator Pedal Position E
    0x4B,  # Accelerator Pedal Position F
    0x4C,  # Commanded Throttle Actuator
}
TWO_BYTE_PIDS = {
    0x0A,  # Fuel Pressure (gauge)
    0x0C,  # Engine RPM
    0x10,  # MAF Air Flow Rate
    0x1F,  # Run Time Since Engine Start
    0x21,  # Distance Travelled with MIL On
    0x2D,  # EGR Error
    0x2E,  # Fuel Trim Bank 1
    0x2F,  # Fuel Level (some ECUs use 2B)
    0x31,  # Distance Since Codes Cleared
    0x5C,  # Engine Oil Temperature
    0x5E,  # Engine Fuel Rate
}
FOUR_BYTE_PIDS = {
    0x14,  # Oxygen Sensor Voltage + Short Term Fuel Trim (Bank 1 Sensor 1)
    0x15,  # Oxygen Sensor Voltage + Short Term Fuel Trim (Bank 1 Sensor 2)
    0x16,  # Oxygen Sensor Voltage + Short Term Fuel Trim (Bank 2 Sensor 1)
    0x17,  # Oxygen Sensor Voltage + Short Term Fuel Trim (Bank 2 Sensor 2)
    0x1C,  # OBD Standards this vehicle conforms to
    0x20,  # PIDs supported [21-40]
    0x40,  # PIDs supported [41-60]
    0x60,  # PIDs supported [61-80]
}

# -----------------------------
# Exceptions
# -----------------------------
class CanError(Exception):
    """Simulated version of python-can.exceptions.CanError"""
    pass

class Listener:
    """Base class for CAN message listeners (simulation stub)."""
    def on_message_received(self, msg: "Message"):
        """Called when a CAN message is received."""
        pass

    def on_error(self, exc: Exception):
        """Optional: handle bus errors."""
        pass

# Define a minimal CAN-like message class
class Message:
    """Lightweight stand-in for python-can.Message."""
    def __init__(self, arbitration_id: int, data: bytes, is_extended_id: bool = False):
        self.arbitration_id = arbitration_id
        self.data = data
        self.dlc = len(data)  # ✅ Data Length Code
        self.is_extended_id = is_extended_id
        self.timestamp = time.time()
        self.channel = "sim"  # optional, for display/logging consistency

    def __repr__(self):
        data_str = " ".join(f"{b:02X}" for b in self.data)
        return f"<SimMessage id=0x{self.arbitration_id:X} dlc={self.dlc} data=[{data_str}]>"

# -----------------------------------------------------------------------------
# Simulated Bus
# -----------------------------------------------------------------------------
class Bus:
    """
    Simulated CAN bus.
    - Generates random CAN frames at a periodic interval.
    - Optionally replays from a text file containing CAN logs.
    """

    #def __init__(self, playback_file: Optional[str] = None, interval: float = 0.25):
    def __init__(self):
        #self.playback_file = playback_file
        #self.interval = interval
        self.interval = 0.05
        self.local_echo = True
        playback_file = None
        self.running = False
        self._queue: queue.Queue[Message] = queue.Queue()
        self._thread: Optional[threading.Thread] = None

        if playback_file:
            self._frames = self._load_log(playback_file)
        else:
            self._frames = []
        self.channel_info = 'Simulated CAN bus'

    def _load_log(self, path: str) -> List[Message]:
        frames = []
        try:
            with open(path, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 2:
                        continue
                    arb_id = int(parts[0], 16)
                    data_bytes = bytes(int(b, 16) for b in parts[1:])
                    frames.append(Message(arb_id, data_bytes))
        except Exception as e:
            print(f"[SimBus] Failed to load log {path}: {e}")
        return frames

    def start(self):
        """Start background message generation."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def shutdown(self):
        """Stop message generation.
           API-compatible with python-can Bus.shutdown()."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        print("[SimBus] shutdown() complete")

    def _loop(self):
        i = 0
        if not self._frames:
            all_pids = list(ONE_BYTE_PIDS | TWO_BYTE_PIDS | FOUR_BYTE_PIDS)
            r = lambda: random.randint(0, 255)
            arb_id = 0x7E8
        while self.running:
            if self._frames:
                # Replay from log cyclically
                msg = self._frames[i % len(self._frames)]
            else:
                # Random mode: generate Mode 1 PID-like messages
                #pid = random.choice(list(ONE_BYTE_PIDS | TWO_BYTE_PIDS | FOUR_BYTE_PIDS))
                pid = all_pids[i % len(all_pids)]
                if pid in ONE_BYTE_PIDS:
                    data = bytes([3, 0x41, pid, r()])
                elif pid in TWO_BYTE_PIDS:
                    data = bytes([4, 0x41, pid, r(), r()])
                else:
                    data = bytes([6, 0x41, pid, r(), r(), r(), r()])
                msg = Message(arb_id, data)
            i += 1
            self._queue.put(msg)
            time.sleep(self.interval)

    def recv(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Receive a simulated CAN message."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def send(self, msg: Message):
        """Send message (no-op in simulation)."""
        if self.local_echo:
            self._queue.put(msg)


# -----------------------------------------------------------------------------
# Simulated Notifier
# -----------------------------------------------------------------------------
class Notifier:
    """
    Drop-in simulated version of python-can.Notifier.
    Continuously calls listener.on_message_received(msg)
    for each message from the simulated bus.
    """

    def __init__(self, bus: Bus, listeners: List[Any]):
        self.bus = bus
        self.listeners = listeners
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.bus.start()
        self.thread.start()

    def _loop(self):
        while self.running:
            msg = self.bus.recv(timeout=0.1)
            if msg:
                for listener in self.listeners:
                    #if hasattr(listener, "on_message_received"):
                    listener.on_message_received(msg)
            time.sleep(0.01)

    def stop(self):
        self.running = False
        self.thread.join(timeout=1.0)

# -----------------------------
# Compatibility shims: namespace sim_can.interface
# -----------------------------
# Mimic "can.interface.Bus"
interface = types.SimpleNamespace(Bus=Bus)

# Mimic "can.exceptions.CanError"
exceptions = types.SimpleNamespace(CanError=CanError)

## Expose Notifier for "can.Notifier"
#Notifier = Notifier

#__all__ = ["Bus", "Notifier", "Message", "Listener"]
