import curses
import random
import time

# ------------------ DATA DEFINITIONS ------------------

def decode_temp(msg: bytes) -> str:
    return f"{20 + (msg[0] % 80):.1f} °C"

def decode_percent(msg: bytes) -> str:
    return f"{(msg[0] % 100):.1f} %"

def decode_rpm(msg: bytes) -> str:
    val = (msg[0] << 8) | msg[1]
    return f"{val % 8000} rpm"

master_list = [
    (0x7E0, 0x01,   0x0C, "Engine RPM", "Engine speed in revolutions per minute", decode_rpm, True),
    (0x7E0, 0x01,   0x05, "Coolant Temp", "Engine coolant temperature", decode_temp, True),
    (0x7E8, 0x22, 0x1234, "Oil Pressure", "Measured oil pressure", decode_percent, False),
    (0x7E8, 0x22, 0x1235, "Throttle", "Throttle position", decode_percent, True),
    (0x7E8, 0x22, 0x1236, "Battery Volt", "System voltage", decode_percent, True),
    (0x7E8, 0x22, 0x1237, "Fuel Level", "Fuel tank level", decode_percent, True),
    (0x7E8, 0x22, 0x1238, "Manifold Temp", "Air manifold temperature", decode_temp, False),
    (0x7E8, 0x22, 0x1239, "Oil Temp", "Engine oil temperature", decode_temp, False),
    (0x7E8, 0x22, 0x1240, "Torque", "Delivered engine torque", decode_percent, True),
    (0x7E8, 0x22, 0x1241, "MAP", "Manifold absolute pressure", decode_percent, True),
]

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

def render_view(stdscr, scroll_offset):
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

    visible_rows = bottom - top - 1
    active = [e for e in master_list if e[-1]]
    visible = active[scroll_offset: scroll_offset + visible_rows]

    row_y = top + 1
    for ecu, sid, pid, label, desc, fn, enabled in visible:
        msg = bytes([random.randint(0, 255) for _ in range(2)])
        val = fn(msg)
        safe_addstr(
            stdscr,
            row_y,
            left + 2,
            f"{ecu:6X} {sid:3X} {pid:04X} {label[:15]:15} {val[:15]:>15}"
        )
        row_y += 1

    stdscr.refresh()

def render_configure(stdscr, selected, scroll_offset):
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

    visible_rows = bottom - top - 1
    visible = master_list[scroll_offset: scroll_offset + visible_rows]

    row_y = top + 1
    for i, entry in enumerate(visible):
        ecu, sid, pid, label, desc, fn, enabled = entry
        mark = "[X]" if enabled else "[ ]"
        line = f"{mark:4} {ecu:6X} {sid:3X} {pid:04X} {label[:15]:15} {desc[:w - 45]}"
        global_index = scroll_offset + i
        if global_index == selected:
            stdscr.attron(curses.A_REVERSE)
            safe_addstr(stdscr, row_y, left + 1, line)
            stdscr.attroff(curses.A_REVERSE)
        else:
            safe_addstr(stdscr, row_y, left + 1, line)
        row_y += 1

    stdscr.refresh()

# ------------------ MAIN LOOP ------------------

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    mode_configure = False
    selected = 0
    scroll_offset = 0

    while True:
        h, w = stdscr.getmaxyx()
        visible_rows = max(1, h - 4)

        if not mode_configure:
            render_view(stdscr, scroll_offset)
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('c'):
                mode_configure = True
                selected = 0
                scroll_offset = 0
            elif key in (curses.KEY_DOWN, ord('j')):
                active = [e for e in master_list if e[-1]]
                if scroll_offset + visible_rows < len(active):
                    scroll_offset += 1
            elif key in (curses.KEY_UP, ord('k')):
                if scroll_offset > 0:
                    scroll_offset -= 1
            else:
                time.sleep(0.1)

        else:
            render_configure(stdscr, selected, scroll_offset)
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('v'):
                mode_configure = False
                scroll_offset = 0
            elif key in (curses.KEY_UP, ord('k')):
                if selected > 0:
                    selected -= 1
                    if selected - scroll_offset < 2 and scroll_offset > 0:
                        scroll_offset -= 1
            elif key in (curses.KEY_DOWN, ord('j')):
                if selected < len(master_list) - 1:
                    selected += 1
                    if selected - scroll_offset > visible_rows - 3:
                        scroll_offset += 1
            elif key == ord(' '):
                ecu, sid, pid, label, desc, fn, enabled = master_list[selected]
                master_list[selected] = (ecu, sid, pid, label, desc, fn, not enabled)

# ------------------ RUN ------------------

if __name__ == "__main__":
    curses.wrapper(main)
