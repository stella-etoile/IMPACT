import os
import sys
import curses

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
if BIN_DIR not in sys.path:
    sys.path.insert(0, BIN_DIR)

from impact_setup_menu import run_setup_namd
from impact_config_editor import run_config_editor

TITLE = "IMPACT – Interactive Molecular Processing and Analysis for Contact/TCRs"
MENU = ["1) Setup NAMD", "2) Run NAMD", "3) Run GaMD", "4) Change config"]
EXIT = "0) Exit"
CONTROLS = "↑/↓ move • Enter select • 0–4 quick • Esc=Exit/Back"

MIN_W = 87
MIN_H = 26

def safe_addstr(stdscr, y, x, text, attr=0):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass

def center(stdscr, y, text, attr=0):
    h, w = stdscr.getmaxyx()
    x = max(0, (w - len(text)) // 2)
    if 0 <= y < h:
        safe_addstr(stdscr, y, x, text[:max(0, w)], attr)

def setup_attrs():
    hint_attr = curses.A_DIM
    warn_attr = curses.A_BOLD
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except Exception:
            pass
        if getattr(curses, "COLORS", 8) >= 256:
            curses.init_pair(10, 242, -1)
            hint_attr = curses.color_pair(10)
        curses.init_pair(11, curses.COLOR_YELLOW, -1)
        warn_attr = curses.color_pair(11) | curses.A_BOLD
    return hint_attr, warn_attr

def draw_too_small(stdscr, stage, hint_attr, warn_attr):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    center(stdscr, max(0, h // 2 - 2), f"Terminal too small: {w}x{h}")
    center(stdscr, h // 2 - 1, f"Resize to at least {MIN_W}x{MIN_H}.", hint_attr)
    if stage == 1:
        center(stdscr, h // 2 + 1, "Press B to bypass (not recommended).", hint_attr)
        center(stdscr, h // 2 + 2, "Esc/q to exit • Resize to continue", hint_attr)
    else:
        center(stdscr, h // 2 + 1, "Warning: UI may render incorrectly at this size.", warn_attr)
        center(stdscr, h // 2 + 2, "Press B again to continue anyway • Esc/q to cancel", warn_attr)
    stdscr.refresh()

def draw_menu(stdscr, idx, hint_attr, ignore_min=False):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    if not ignore_min and (h < MIN_H or w < MIN_W):
        return False
    center(stdscr, 2, TITLE, curses.A_BOLD)
    center(stdscr, 4, CONTROLS, hint_attr)
    for i, item in enumerate(MENU):
        a = curses.A_REVERSE if i == idx else 0
        center(stdscr, 6 + i * 2, item, a)
    y_exit = max(0, h - 2)
    a = curses.A_REVERSE if idx == len(MENU) else 0
    center(stdscr, y_exit, EXIT, a)
    stdscr.refresh()
    return True

def menu(stdscr, hint_attr, warn_attr):
    curses.curs_set(0)
    stdscr.keypad(True)
    idx = 0
    ignore_min = False
    bypass_stage = 1
    while True:
        ok = draw_menu(stdscr, idx, hint_attr, ignore_min=ignore_min)
        if not ok:
            draw_too_small(stdscr, bypass_stage, hint_attr, warn_attr)
        k = stdscr.getch()
        if not ok:
            if k in (27, ord('q')):
                return len(MENU)
            elif k in (ord('b'), ord('B')):
                if bypass_stage == 1:
                    bypass_stage = 2
                else:
                    ignore_min = True
            elif k == curses.KEY_RESIZE:
                bypass_stage = 1
            continue
        if k in (curses.KEY_UP, ord('k')):
            idx = (idx - 1) % (len(MENU) + 1)
        elif k in (curses.KEY_DOWN, ord('j')):
            idx = (idx + 1) % (len(MENU) + 1)
        elif k in (10, 13, curses.KEY_ENTER):
            return idx
        elif k in (ord('0'), ord('1'), ord('2'), ord('3'), ord('4')):
            if k == ord('0'):
                return len(MENU)
            return int(chr(k)) - 1
        elif k in (27, ord('q')):
            return len(MENU)
        elif k == curses.KEY_RESIZE:
            continue

def main(stdscr):
    hint_attr, warn_attr = setup_attrs()
    while True:
        choice = menu(stdscr, hint_attr, warn_attr)
        if choice == len(MENU) or choice is None:
            break
        if choice == 0:
            run_setup_namd(stdscr, hint_attr)
        elif choice == 3:
            run_config_editor(stdscr, hint_attr)
        else:
            pass

if __name__ == "__main__":
    curses.wrapper(main)