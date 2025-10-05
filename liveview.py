import my_uds

import click
import curses
from itertools import islice
import json
from pathlib import Path
import queue
import random
import sys
import time
import traceback
from typing import Any, Iterator, Tuple, Callable#, List, Tuple, Union

STATE_FILE = Path("active_ids.json")

# ------------------ DATA DEFINITIONS ------------------

def decode_temp(msg: bytes) -> str:
    return f"{20 + (msg[0] % 80):.1f} °C"

def decode_percent(msg: bytes) -> str:
    return f"{(msg[0] % 100):.1f} %"

def decode_rpm(msg: bytes) -> str:
    val = (msg[0] << 8) | msg[1]
    return f"{val % 8000} rpm"

def iter_all_signals() -> Iterator[Tuple[Tuple[int, int, int], Tuple[str, str, Callable[[my_uds.CanMsgData], str]]]]:
    """Yield all PID and DID entries with the proper service ID inserted."""
    # Mode 1 (Service 0x01) for OBD-II PIDs
    for (ecu, pid), info in my_uds.PID_LIST:
        yield ((ecu, 0x01, pid), info)

    # Mode 22 (Service 0x22) for UDS Data Identifiers
    for (ecu, did), info in my_uds.DID_LIST:
        yield ((ecu, 0x22, did), info)

global master_list, value_cache
master_list = list(iter_all_signals())
value_cache = {}

# ------------------ DRAW HELPERS ------------------

def safe_addstr(win, y:int, x:int, text) -> None:
    """Add string safely without crashing when window too small."""
    try:
        height, width = win.getmaxyx()
        if 0 <= y < height:
            win.addstr(y, x, text[: max(0, width - x - 1)])
    except curses.error:
        pass

def draw_box(win, top:int, left:int, bottom:int, right:int) -> None:
    """Draw a rectangular box."""
    try:
        win.hline(top, left + 1, curses.ACS_HLINE, right - left - 1)
        win.hline(bottom, left + 1, curses.ACS_HLINE, right - left - 1)
        win.vline(top + 1, left, curses.ACS_VLINE, bottom - top - 1)
        win.vline(top + 1, right, curses.ACS_VLINE, bottom - top - 1)
        win.addch(top, left, curses.ACS_ULCORNER)
        win.addch(top, right, curses.ACS_URCORNER)
        win.addch(bottom, left, curses.ACS_LLCORNER)
        win.addch(bottom, right, curses.ACS_LRCORNER)
    except curses.error:
        pass

# ------------------ RENDER FUNCTIONS ------------------

def render_view(stdscr, active_keys, scroll_offset):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    title = "VIEW MODE  (↑↓ scroll, 'c'=configure, 'q'=quit)"
    safe_addstr(stdscr, 0, 0, title[: w - 1])

    top, bottom  = 1, h - 1
    left, right = 0, w - 2
    draw_box(stdscr, top, left, bottom, right)

    # Column headers over the top line of box
    header_y = top
    safe_addstr(stdscr, header_y, left + 2,
                f"{'ECU':6} {'SID':4} {'PID':4} {'Label':15} {'Value':>15}")

    n_visible = bottom - top - 1
    active_list = [
        (key, value) for key, value in master_list
        if key in active_keys
    ]
    #visible_rows = active_list[scroll_offset: scroll_offset + n_visible]
    # This avoids building the full list in memory but still lets you scroll window
    visible_rows = list(islice(iter_all_signals(), scroll_offset, scroll_offset + n_visible))
    row_y = top + 1
    for (can_id, sid, pid), (label, descr, decode_fn) in visible_rows:
        #(label, descr, decode_fn, display_flag) = master_list[(can_id, sid, pid)]
        msg = bytes([random.randint(0, 255) for _ in range(2)])
        value = value_cache.get((can_id & 0xFFF7, sid, pid), 'loading')
        safe_addstr(
            stdscr,
            row_y,
            left + 2,
            f"{can_id:6X} {sid:3X} {pid:04X} {label[:15]:15} {value[:15]:>15}"
        )
        row_y += 1

    stdscr.refresh()

def render_configure(stdscr, active_keys, selected, scroll_offset):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    title = "CONFIGURE MODE  (↑↓/j/k move, space=toggle, v=view, q=quit)"
    safe_addstr(stdscr, 0, 0, title[: w - 1])

    top, bottom  = 1, h - 1
    left, right = 0, w - 2
    draw_box(stdscr, top, left, bottom, right)

    # Column headers over the top line of box
    header_y = top
    safe_addstr(stdscr, header_y, left + 2,
                f"{' ':4} {'ECU':6} {'SID':4} {'PID':4} {'Label':15} {'Description'}")

    n_visible = bottom - top - 1
    visible = master_list[scroll_offset: scroll_offset + n_visible]
    row_y = top + 1
    for i, entry in enumerate(visible):
        (can_id, sid, pid), (label, desc, fn) = entry
        mark = "[X]" if (can_id, sid, pid) in active_keys else "[ ]"
        line = f"{mark:4} {can_id:6X} {sid:3X} {pid:04X} {label[:15]:15} {desc[:w - 45]}"
        global_index = scroll_offset + i
        if global_index == selected:
            stdscr.attron(curses.A_REVERSE)
            safe_addstr(stdscr, row_y, left + 1, line)
            stdscr.attroff(curses.A_REVERSE)
        else:
            safe_addstr(stdscr, row_y, left + 1, line)
        row_y += 1

    stdscr.refresh()

# --- Click CLI Definition ---
@click.command()
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode for more detailed error reporting (prints full tracebacks).",
    default=False
)
@click.option(
    "--simulate",
    is_flag=True,
    help="Run in simulation mode (no real CAN bus connection).",
)
def main(debug:bool, simulate:bool):
    """
    Launches a curses-based live view of CAN bus data.
    """
    click.echo(f"xxxx", err=True)
    can_bus = None
    try:
        if simulate:
            import sim_can as can
            click.echo(f"Simulated CAN Bus", err=True)
        else:
            try:
                import can
            except ImportError:
                click.echo("Error: 'python-can' library not found. Cannot connect to CAN bus. Use --simulate.", err=True)
                sys.exit(1)
        # Set up a receive thread
        try:
            can_bus = can.interface.Bus() #config=config_path, bustype=bustype, channel=channel, bitrate=bitrate)
        except can.exceptions.CanError as e:
            click.echo(f"CAN connection failed: {e}", err=True)
            sys.exit(1)
        #bustype, channel, bitrate = None, None, None
        #click.echo(f"Connected to CAN Bus {bustype} on {channel} @ {bitrate}bps", err=True)

        # 2. Set up a notifier to listen for incoming messages
        class LiveViewListener(can.Listener):
            """
            A CAN listener that puts received messages into a queue.
            """
            def __init__(self, msg_queue: queue.Queue):
                self.msg_queue = msg_queue

            def on_message_received(self, msg: can.Message) -> None:
                """
                Called automatically by the Notifier when a message is received.
                """
                self.msg_queue.put(msg)

            def on_error(self, exc: Exception) -> None:
                """
                Called automatically by the Notifier if an error occurs.
                """
                print(f"CAN Listener Error: {exc}", file=sys.stderr)
        
        msg_queue = queue.Queue()
        notifier = can.Notifier(can_bus, [LiveViewListener(msg_queue)]) #, timeout=2)

        # Correct curses initialization and cleanup using try...finally
        stdscr = None
        try:
            stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            stdscr.keypad(True)

            run_liveview_curses(stdscr, can_bus, msg_queue) # Call the curses application logic
        except Exception as e:
            if stdscr:
                stdscr.addstr(str(e))
                stdscr.addstr(traceback.format_exc())
                click.echo(traceback.format_exc(), err=True)
                time.sleep(15);
            else:
                click.echo('here 1', err=True)
                click.echo(traceback.format_exc(), err=True)
            sys.exit(1)
        finally:
            if stdscr:
                stdscr.keypad(False)
                curses.echo()
                curses.nocbreak()
                curses.endwin()
                click.echo("Exited curses live view.", err=True)
            click.echo('here 3', err=True)
            click.echo(traceback.format_exc(), err=True)
            #traceback.print_exc()
    except Exception as e:
        click.echo('here 2', err=True)
        traceback.print_exc()
        sys.exit(1)
    finally:
        if can_bus:
            can_bus.shutdown()
        click.echo("Liveview finished.", err=True)

def run_liveview_curses(stdscr, can_bus, msg_queue: queue.Queue):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.timeout(200)

    # Init colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)

    # Load persistent activation state
    active_keys = load_active_flags(master_list)

    mode_configure = False
    selected = 0  # Cursor row
    scroll_offset = 0

    draw_all:bool = True

    # ------------------ MAIN LOOP ------------------
    while True:
        h, w = stdscr.getmaxyx()
        visible_rows = max(1, h - 4)

        if not mode_configure:
            if draw_all:
                render_view(stdscr, active_keys, scroll_offset)
                draw_all = False
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('c'):
                mode_configure = True
                draw_all = True
                selected = 0
                scroll_offset = 0
            elif key in (curses.KEY_DOWN, ord('j')):
                active = [e for e in master_list if e[-1]]
                if scroll_offset + visible_rows < len(active):
                    scroll_offset += 1
                draw_all = True
            elif key in (curses.KEY_UP, ord('k')):
                if scroll_offset > 0:
                    scroll_offset -= 1
                draw_all = True
            else:
                pass #time.sleep(0.1)

        else:
            if draw_all:
                render_configure(stdscr, active_keys, selected, scroll_offset)
                draw_all = False
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('v'):
                save_active_flags(active_keys)
                mode_configure = False
                scroll_offset = 0
                draw_all = True
            elif key in (curses.KEY_UP, ord('k')):
                if selected > 0:
                    selected -= 1
                    if selected - scroll_offset < 2 and scroll_offset > 0:
                        scroll_offset -= 1
                draw_all = True
            elif key in (curses.KEY_DOWN, ord('j')):
                if selected < len(master_list) - 1:
                    selected += 1
                    if selected - scroll_offset > visible_rows - 3:
                        scroll_offset += 1
                draw_all = True
            elif key == ord(' '):
                rowkey, rowval = master_list[selected]
                if rowkey in active_keys:
                    active_keys.remove(rowkey)
                else:
                    active_keys.add(rowkey)
                draw_all = True

        def on_didpid(arb_id, sid, pid, label, desc, value):#msg: can.Message):
            h, w = stdscr.getmaxyx()
            top, bottom  = 1, h - 1
            left, right = 0, w - 2
            n_visible = bottom - top - 1
            active_list = [
                (key, value) for key, value in master_list
                if key in active_keys
            ]
            #visible_rows = active_list[scroll_offset: scroll_offset + n_visible]
            visible_rows = list(islice(iter_all_signals(), scroll_offset, scroll_offset + n_visible))
            for i, entry in enumerate(visible_rows):
                (e_can_id, e_sid, e_pid), (_, _, _) = entry
                if (arb_id & 0xFFF7, sid, pid) == (e_can_id & 0xFFF7, e_sid, e_pid):
                    safe_addstr(stdscr, top+1+i, 42, f"{value[:15]:15}")
                    stdscr.clrtoeol()
                    break
            # Store it for rapid screen updates
            value_cache[(arb_id & 0xFFF7, sid, pid)] = value

        # --- Process CAN Messages (from Queue) ---
        while not msg_queue.empty():
            try:
                msg = msg_queue.get_nowait()
                if not mode_configure:
                    if msg.arbitration_id & 0x08 == 0:
                        # Requests silent
                        continue
                    # TODO Define UDSListener
                    my_uds.framing(msg,
                        lambda arb_id, pid, name, desc, value_str: on_didpid(arb_id, 0x01, pid, name, desc, value_str),
                        lambda arb_id, pid, name, desc, value_str: on_didpid(arb_id, 0x22, pid, name, desc, value_str))
            except queue.Empty:
                pass # Should not happen with empty() check, but good practice
        stdscr.refresh()
        #time.sleep(5)

def load_active_flags(master_list):
    """Load saved active (enabled) IDs from file."""
    #if STATE_FILE.exists():
    try:
        data = json.loads(STATE_FILE.read_text())
        active_set = {tuple(item) for item in data}
        print('loaded', active_set)
    except Exception as e:
        #traceback.print_exc()
        active_set = {k for k,_ in master_list}
        #print('load failed', e, active_set)
        #time.sleep(2)
    return active_set            

def save_active_flags(active_keys):
    """Save active IDs (can_id, sid, pid) only."""
    try:
        STATE_FILE.write_text(json.dumps(list(active_keys), indent=2))
    except Exception as e:
        print(f"Warning: could not save active IDs: {e}")
        time.sleep(1)

# ------------------ RUN ------------------
if __name__ == "__main__":
    main()
