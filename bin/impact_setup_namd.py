import os
import time
import curses
from curses import textpad, ascii
import tempfile
import subprocess
from typing import Optional, List, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DEFAULT_CONF = os.path.join(ROOT_DIR, "IMPACT.conf")
RUN_TESTS_SH = os.path.join(BASE_DIR, "impact_setup_namd.sh")

SUBTITLE = "Setup NAMD"
EXAMPLES_ADD = "Add: e.g., 06 07,08 09"
EXAMPLES_REMOVE = "Remove: e.g., 06 07,08 09"

# -------------------- config helpers --------------------

def find_conf():
    if os.path.exists(DEFAULT_CONF):
        return DEFAULT_CONF
    p = os.path.join(os.getcwd(), "IMPACT.conf")
    return p if os.path.exists(p) else None

def read_config():
    """
    Returns: (pdb_proc_dir, namd_proc_dir, conf_path_abs)
    """
    conf = find_conf()
    pdb_proc_dir = "."
    namd_proc_dir = os.path.join(ROOT_DIR, "1_output")
    if conf and os.path.exists(conf):
        base = os.path.dirname(conf)
        with open(conf) as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("PDB_PROC_DIR"):
                    _, v = s.split("=", 1)
                    pdb_proc_dir = os.path.abspath(os.path.join(base, v.strip().strip('"').strip("'")))
                elif s.startswith("NAMD_PROC_DIR"):
                    _, v = s.split("=", 1)
                    namd_proc_dir = os.path.abspath(os.path.join(base, v.strip().strip('"').strip("'")))
    return pdb_proc_dir, namd_proc_dir, (conf if conf else DEFAULT_CONF)

# -------------------- UI helpers --------------------

def wrap_tokens(stdscr, y, x, w, tokens, hi_idx=None, attr_hi=0, attr_norm=0):
    if w <= 4:
        return 0
    cx, cy = x, y
    used = 1
    for i, tok in enumerate(tokens):
        t = tok + " "
        if cx + len(t) > w - 2:
            cy += 1
            cx = x
            used += 1
        attr = attr_hi if (hi_idx is not None and i == hi_idx) else attr_norm
        try:
            stdscr.addstr(cy, cx, t, attr)
        except curses.error:
            pass
        cx += len(t)
    return used

def wrap_line(s, w):
    if w <= 0:
        return [""]
    out, cur = [], ""
    for tok in s.split():
        if len(cur) + len(tok) + (1 if cur else 0) <= w:
            cur = (cur + " " + tok).strip()
        else:
            out.append(cur)
            cur = tok
    if cur:
        out.append(cur)
    return out or [""]

def tokens_from(s):
    s = s.replace(",", " ")
    return [t.strip() for t in s.split() if t.strip()]

def init_colors():
    err_attr = curses.A_BOLD
    hint_attr = curses.A_DIM
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except Exception:
            pass
        curses.init_pair(1, curses.COLOR_RED, -1)
        err_attr = curses.color_pair(1) | curses.A_BOLD
        if getattr(curses, "COLORS", 8) >= 256:
            curses.init_pair(10, 244, -1)
            hint_attr = curses.color_pair(10)
        curses.init_pair(11, curses.COLOR_YELLOW, -1)
    return err_attr, hint_attr

def tail_lines(path, n=50, w=120):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size <= 0:
                return []
            block = 4096
            chunks = []
            read = 0
            while size > 0 and read < 1024 * 1024 and sum(c.count(b"\n") for c in chunks) <= n + 4:
                to_read = block if size >= block else size
                size -= to_read
                f.seek(size)
                chunks.insert(0, f.read(to_read))
                read += to_read
            data = b"".join(chunks)
            lines = data.decode(errors="ignore").splitlines()[-n:]
            return [ln[: max(0, w - 6)] for ln in lines]
    except Exception:
        return []

def list_processed_systems(pdb_proc_dir):
    if not os.path.isdir(pdb_proc_dir):
        return []
    names = []
    for f in os.listdir(pdb_proc_dir):
        p = os.path.join(pdb_proc_dir, f)
        if os.path.isdir(p):
            names.append(f)
        elif f.lower().endswith(".pdb"):
            names.append(os.path.splitext(f)[0])
    return sorted(set(names))

def list_namd_prepared(namd_proc_dir, names):
    ready = set()
    if not os.path.isdir(namd_proc_dir):
        return ready
    existing = set(os.listdir(namd_proc_dir))
    for n in names:
        if n in existing:
            ready.add(n)
            continue
        base = os.path.join(namd_proc_dir, n)
        if os.path.isdir(base):
            try:
                for _root, _dirs, files in os.walk(base):
                    for fn in files:
                        lf = fn.lower()
                        if lf.endswith((".psf", ".conf", ".namd", ".prm", ".xsc", ".pbc", ".pdb")):
                            ready.add(n)
                            raise StopIteration
            except StopIteration:
                pass
        else:
            for suf in (".psf", ".conf", ".namd", ".xsc"):
                if os.path.exists(os.path.join(namd_proc_dir, n + suf)):
                    ready.add(n)
                    break
    return ready

# -------------------- drawing helpers --------------------

def draw_trial_widget(stdscr, y, trial_num, focused, hint_attr):
    """
    Draw a centered trial widget at row y.
    If focused, show ▲/▼ on rows y-1 and y+1 and highlight the widget.
    """
    h, w = stdscr.getmaxyx()
    label = f"Trial: [{trial_num}]"
    x = max(0, (w - len(label)) // 2)

    if focused and y - 1 >= 0:
        try:
            stdscr.addstr(y - 1, x + len(label)//2, "▲", hint_attr)
        except Exception:
            try: stdscr.addstr(y - 1, x + len(label)//2, "^", hint_attr)
            except curses.error: pass
    attr = curses.A_REVERSE | curses.A_BOLD if focused else curses.A_BOLD
    try:
        stdscr.addstr(y, x, label, attr)
    except curses.error:
        pass
    if focused and y + 1 < h:
        try:
            stdscr.addstr(y + 1, x + len(label)//2, "▼", hint_attr)
        except Exception:
            try: stdscr.addstr(y + 1, x + len(label)//2, "v", hint_attr)
            except curses.error: pass

# -------------------- progress UI (batch run) --------------------

def draw_progress(
    stdscr, y0, name, idx, total, started_at, item_started_at,
    avg_sec, out_tail, err_tail, hint_attr, err_attr, split_label,
    extra_line: Optional[str] = None
):
    h, w = stdscr.getmaxyx()
    elapsed = int(time.time() - started_at)
    cur_dt = time.time() - item_started_at
    done = idx - 1
    remain_count = max(0, total - idx)
    est = int(remain_count * avg_sec) if avg_sec > 0 else 0
    pct = int((done / total) * 100) if total > 0 else 0
    bar_w = max(20, w - 10)
    filled = max(0, int((pct / 100.0) * (bar_w - 2)))
    bar = "[" + "#" * filled + "-" * ((bar_w - 2) - filled) + "]"

    stdscr.clear()
    try:
        stdscr.addstr(y0, 2, "Running… (q/Esc=cancel, v=toggle logs, s=change split)", hint_attr)
        if extra_line:
            stdscr.addstr(y0, 50, f" {extra_line} ", hint_attr)
        stdscr.addstr(y0 + 1, 2, f"{idx}/{total} • {name} • {cur_dt:.1f}s")
        stdscr.addstr(y0 + 2, 2, f"{pct:3d}% {bar}")
        stdscr.addstr(y0 + 3, 2, f"ETA ~ {est//60:d}m {est%60:d}s • Elapsed {elapsed//60}m {elapsed%60}s")

        y = y0 + 5
        stdscr.addstr(y, 2, "── stderr ", err_attr); y += 1
        for ln in err_tail:
            if y >= h - 2: break
            stdscr.addstr(y, 2, ln, err_attr); y += 1

        if y < h - 3:
            stdscr.addstr(y, 2, f"── stdout ({split_label}) ", hint_attr); y += 1
            for ln in out_tail:
                if y >= h - 1: break
                stdscr.addstr(y, 2, ln); y += 1

    except curses.error:
        pass
    stdscr.refresh()

def run_local_with_progress(
    stdscr, selections: List[str], conf_path: str, trial_num: int,
    hint_attr, err_attr
):
    """
    Runs impact_namd_setup.sh once for all selections using a temp selection file.
    Shows live stdout/stderr tails. Cancel with q/Esc.
    """
    if not selections:
        return False, "Selection is empty"
    if not os.path.isfile(RUN_TESTS_SH):
        return False, f"Missing {RUN_TESTS_SH}"
    if not os.path.isfile(conf_path):
        return False, f"Missing {conf_path}"

    # write temp selection list
    with tempfile.NamedTemporaryFile("w", delete=False, prefix="impact_sel_", suffix=".txt") as fsel:
        for n in selections:
            fsel.write(n + "\n")
        sel_path = fsel.name

    out_path = os.path.join(tempfile.gettempdir(), "impact_namd_batch.out")
    err_path = os.path.join(tempfile.gettempdir(), "impact_namd_batch.err")
    out_f = open(out_path, "w")
    err_f = open(err_path, "w")

    cmd = [RUN_TESTS_SH, "--conf", conf_path, "--trial", str(trial_num), sel_path]

    t_start = time.time()
    t0 = time.time()
    times: List[float] = []
    verbose = True
    splits = [(0.7, 0.3), (0.5, 0.5), (0.3, 0.7)]
    split_idx = 0

    stdscr.nodelay(True)
    try:
        p = subprocess.Popen(cmd, stdout=out_f, stderr=err_f, text=True, cwd=ROOT_DIR)
        while True:
            try:
                ch = stdscr.getch()
                if ch in (27, ord('q')):
                    p.terminate()
                    try: p.wait(timeout=5)
                    except Exception: pass
                    out_f.close(); err_f.close()
                    try: os.unlink(sel_path)
                    except Exception: pass
                    return False, "Cancelled"
                elif ch in (ord('v'), ord('V')):
                    verbose = not verbose
                elif ch in (ord('s'), ord('S')):
                    split_idx = (split_idx + 1) % len(splits)
            except curses.error:
                pass

            rc = p.poll()

            h, w = stdscr.getmaxyx()
            y0 = 2
            header_rows = 5
            available_rows = max(0, (h - (y0 + header_rows)) - 2)
            if verbose and available_rows >= 6:
                so, se = splits[split_idx]
                out_n = max(3, int(available_rows * so))
                err_n = max(3, available_rows - out_n)
                out_tail = tail_lines(out_path, n=out_n, w=w)
                err_tail = tail_lines(err_path, n=err_n, w=w)
                split_label = f"{int(so*100)}/{int(se*100)}"
            else:
                out_tail, err_tail, split_label = [], [], "logs hidden"

            avg = (sum(times) / len(times)) if times else max(1.0, time.time() - t0)

            draw_progress(
                stdscr, y0=y0, name=f"{len(selections)} system(s)", idx=1, total=1,
                started_at=t_start, item_started_at=t0,
                avg_sec=avg, out_tail=out_tail, err_tail=err_tail,
                hint_attr=hint_attr, err_attr=err_attr, split_label=split_label
            )

            if rc is not None:
                break
            time.sleep(0.1)

        out_f.flush(); err_f.flush()
        out_f.close(); err_f.close()
        dt = time.time() - t0
        times.append(dt)
    finally:
        stdscr.nodelay(False)
        try: os.unlink(sel_path)
        except Exception: pass

    total_dt = int(time.time() - t_start)
    return True, f"Completed in {total_dt//60}m {total_dt%60}s"

# -------------------- layout math --------------------

def compute_input_y(stdscr, names, ready, selection):
    h, w = stdscr.getmaxyx()
    names_lines = max(1, len(wrap_line(" ".join(names), max(10, w - 4))))
    ready_line = " ".join(sorted(set(names) & set(ready))) or "(none)"
    ready_lines = max(1, len(wrap_line(ready_line, max(10, w - 4))))
    sel_line = " ".join(sorted(selection)) if selection else "(empty)"
    sel_lines = max(1, len(wrap_line(sel_line, max(10, w - 4))))
    cur_y = 11 + names_lines
    cur2_y = cur_y + 1 + ready_lines + 1
    menu_y = cur2_y + 2 + sel_lines + 1
    return menu_y + 10

# -------------------- drawing --------------------

def draw(
    stdscr, title, hint_attr, pdb_proc_dir, namd_proc_dir,
    names, ready, selection, cursor_idx, focus, menu_cursor,
    trial_num,
    msg="", msg_attr=0, err_attr=0
) -> Tuple[int, int]:
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    tx = max(0, (w - len(title)) // 2)
    try:
        stdscr.addstr(1, tx, title, curses.A_BOLD)
        draw_trial_widget(stdscr, 2, trial_num, focused=(focus == "trial"), hint_attr=hint_attr)

        stdscr.addstr(4, 2, "Focus: Tab switches • Esc/0 Back • Enter activates", hint_attr)
        stdscr.addstr(5, 2, "Menu: ↑/↓ or j/k move • 1–7 shortcuts • At trial: ↑/↓ to change", hint_attr)
        stdscr.addstr(6, 2, "Processed: ←/→ or h/l move • Enter toggles add/remove • ←/→ moves between systems ⇄ trial ⇄ menu", hint_attr)

        stdscr.addstr(8, 2, f"PDB_PROC_DIR:  {pdb_proc_dir}", hint_attr)
        stdscr.addstr(9, 2, f"NAMD_PROC_DIR: {namd_proc_dir}", hint_attr)
        stdscr.addstr(11, 2, "Processed systems:", curses.A_UNDERLINE)
    except curses.error:
        pass

    hi_idx = cursor_idx if (names and focus == "proc") else None
    lines_used = wrap_tokens(stdscr, 12, 2, w, names, hi_idx=hi_idx, attr_hi=curses.A_REVERSE, attr_norm=0)

    cur_y = 12 + max(1, lines_used)
    try:
        stdscr.addstr(cur_y, 2, "Already NAMD-prepared: will be in the directory specified in NAMD_PROC_DIR in conf", curses.A_UNDERLINE)
    except curses.error:
        pass

    shown_ready = sorted(set(names) & set(ready))
    ready_line = " ".join(shown_ready) if shown_ready else "(none)"
    for j, line in enumerate(wrap_line(ready_line, max(10, w - 4))):
        try: stdscr.addstr(cur_y + 1 + j, 2, line)
        except curses.error: pass

    cur2_y = cur_y + 2 + max(1, len(wrap_line(ready_line, max(10, w - 4))))
    try: stdscr.addstr(cur2_y, 2, "Current selection:", curses.A_UNDERLINE)
    except curses.error: pass
    sel_line = " ".join(sorted(selection)) if selection else "(empty)"
    for k, line in enumerate(wrap_line(sel_line, max(10, w - 4))):
        try: stdscr.addstr(cur2_y + 1 + k, 2, line)
        except curses.error: pass

    menu_y = cur2_y + 3 + max(1, len(wrap_line(sel_line, max(10, w - 4))))
    options = [
        "1) Add all nonprepared (recommended)",
        "2) Add all",
        "3) Add selection",
        "4) Remove selection",
        "5) Remove all",
        f"6) Set trial number (current: {trial_num})",
        "7) Generate current selection (local)",
        "0) Back",
    ]
    for idx, opt in enumerate(options):
        attr = curses.A_REVERSE if (focus == "menu" and idx == menu_cursor) else 0
        try: stdscr.addstr(menu_y + idx, 2, opt, attr)
        except curses.error: pass

    info_y = menu_y + len(options) + 1
    if msg:
        try: stdscr.addstr(info_y, 2, msg[: max(0, w - 4)], msg_attr)
        except curses.error: pass

    stdscr.refresh()
    return menu_y, len(options)

# -------------------- small prompt --------------------

def prompt(stdscr, top_line, hint_attr, y_start=None):
    h, w = stdscr.getmaxyx()
    if y_start is None:
        y_start = h - 6
    try:
        stdscr.addstr(y_start, 2, top_line, hint_attr)
        stdscr.addstr(y_start + 1, 2, "Separate by space or comma • Esc=Back", hint_attr)
        stdscr.addstr(y_start + 3, 2, "> ")
    except curses.error:
        pass
    tb_win = curses.newwin(1, max(1, w - 6), y_start + 3, 4)
    curses.curs_set(1)
    box = textpad.Textbox(tb_win)
    cancelled = {"v": False}

    def validate(ch):
        if ch == 27:
            cancelled["v"] = True
            return ascii.BEL
        return ch

    s = box.edit(validate).strip()
    curses.curs_set(0)
    if cancelled["v"]:
        return None
    return s

# -------------------- controller --------------------

def run_setup_namd(stdscr, inherited_hint_attr=None):
    pdb_proc_dir, namd_proc_dir, conf_path = read_config()
    curses.curs_set(0)
    stdscr.keypad(True)
    err_attr, hint_attr_local = init_colors()
    hint_attr = inherited_hint_attr if inherited_hint_attr is not None else hint_attr_local

    selection = set()
    focus = "menu"
    menu_cursor = 0
    proc_cursor = 0
    trial_num = 1

    while True:
        names = list_processed_systems(pdb_proc_dir)
        ready = list_namd_prepared(namd_proc_dir, names)
        if proc_cursor >= len(names):
            proc_cursor = max(0, len(names) - 1)

        _, options_len = draw(
            stdscr, SUBTITLE, hint_attr,
            pdb_proc_dir, namd_proc_dir,
            names, ready, selection, proc_cursor, focus, menu_cursor,
            trial_num
        )

        k = stdscr.getch()
        choice = None

        if k in (9, curses.KEY_BTAB):
            focus = "proc" if focus == "menu" else ("trial" if focus == "proc" else "menu")

        elif k in (curses.KEY_UP, ord('k')):
            if focus == "menu":
                if menu_cursor == 0:
                    focus = "proc"
                else:
                    menu_cursor = (menu_cursor - 1) % options_len
            elif focus == "trial":
                trial_num = max(1, trial_num - 1)
            elif focus == "proc":
                pass

        elif k in (curses.KEY_DOWN, ord('j')):
            if focus == "menu":
                menu_cursor = (menu_cursor + 1) % options_len
            elif focus == "trial":
                trial_num = max(1, trial_num + 1)
            elif focus == "proc":
                focus = "menu"

        elif k in (curses.KEY_LEFT, ord('h')):
            if focus == "menu":
                if menu_cursor == 5:
                    trial_num = max(1, trial_num - 1)
                else:
                    focus = "trial"
            elif focus == "trial":
                trial_num = max(1, trial_num - 1)
            elif focus == "proc":
                proc_cursor = max(0, proc_cursor - 1) if names else 0

        elif k in (curses.KEY_RIGHT, ord('l')):
            if focus == "proc":
                if names:
                    proc_cursor = min(len(names) - 1, proc_cursor + 1)
            elif focus == "trial":
                trial_num = max(1, trial_num + 1)
            elif focus == "menu":
                if menu_cursor == 5:
                    trial_num = max(1, trial_num + 1)
                else:
                    pass

        elif k in (10, 13, curses.KEY_ENTER):
            if focus == "menu":
                choice = menu_cursor
            elif focus == "proc":
                if names:
                    n = names[proc_cursor]
                    if n in selection:
                        selection.discard(n)
                    else:
                        selection.add(n)
            elif focus == "trial":
                pass

        elif k in (ord('0'),):
            focus = "menu"
            choice = options_len - 1

        elif k in (ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6'), ord('7')):
            if focus != "trial":
                focus = "menu"
                desired = int(chr(k)) - 1
                if desired < options_len:
                    choice = desired

        elif k in (27, ord('q')):
            focus = "menu"
            choice = options_len - 1

        if choice is None:
            continue

        # ---- map indices to actions ----
        if choice == 0:  # Add all nonprepared
            nonprepared = [t for t in names if t not in ready]
            if not nonprepared:
                draw(stdscr, SUBTITLE, hint_attr, pdb_proc_dir, namd_proc_dir,
                     names, ready, selection, proc_cursor, focus, menu_cursor,
                     trial_num, "All processed systems appear NAMD-ready", err_attr, err_attr)
                stdscr.getch()
            else:
                selection.update(nonprepared)

        elif choice == 1:  # Add all
            selection = set(names)

        elif choice == 2:  # Add selection (text prompt)
            y_in = compute_input_y(stdscr, names, ready, selection)
            s = prompt(stdscr, EXAMPLES_ADD, hint_attr, y_start=y_in)
            if s:
                toks = tokens_from(s)
                invalid = [t for t in toks if t not in names]
                valid = [t for t in toks if t in names]
                if valid:
                    selection.update(valid)
                if invalid:
                    draw(stdscr, SUBTITLE, hint_attr, pdb_proc_dir, namd_proc_dir,
                         names, ready, selection, proc_cursor, focus, menu_cursor,
                         trial_num, "Invalid: " + ", ".join(invalid), err_attr, err_attr)
                    stdscr.getch()

        elif choice == 3:  # Remove selection (text prompt)
            y_in = compute_input_y(stdscr, names, ready, selection)
            s = prompt(stdscr, EXAMPLES_REMOVE, hint_attr, y_start=y_in)
            if s:
                toks = tokens_from(s)
                not_in_list = [t for t in toks if t not in names]
                not_selected = [t for t in toks if t in names and t not in selection]
                to_remove = [t for t in toks if t in selection]
                for t in to_remove:
                    selection.discard(t)
                msgs = []
                if not_in_list:   msgs.append("Not found: " + ", ".join(not_in_list))
                if not_selected:  msgs.append("Not in selection: " + ", ".join(not_selected))
                if msgs:
                    draw(stdscr, SUBTITLE, hint_attr, pdb_proc_dir, namd_proc_dir,
                         names, ready, selection, proc_cursor, focus, menu_cursor,
                         trial_num, " | ".join(msgs), err_attr, err_attr)
                    stdscr.getch()

        elif choice == 4:  # Remove all
            selection = set()

        elif choice == 5:  # Set trial number (prompt fallback)
            s = prompt(stdscr, "Trial number (default 1):", hint_attr)
            if s:
                try:
                    trial_num = max(1, int(s))
                except Exception:
                    trial_num = 1

        elif choice == 6:  # Generate current selection (local)
            if not selection:
                draw(stdscr, SUBTITLE, hint_attr, pdb_proc_dir, namd_proc_dir,
                     names, ready, selection, proc_cursor, focus, menu_cursor,
                     trial_num, "Selection is empty", err_attr, err_attr)
                stdscr.getch()
            else:
                sels = sorted(selection)
                ok, msg = run_local_with_progress(
                    stdscr, sels, conf_path=DEFAULT_CONF, trial_num=trial_num,
                    hint_attr=hint_attr, err_attr=err_attr
                )
                draw(stdscr, SUBTITLE, hint_attr, pdb_proc_dir, namd_proc_dir,
                     names, ready, selection, proc_cursor, focus, menu_cursor,
                     trial_num, msg, 0 if ok else err_attr, err_attr)
                stdscr.getch()

        elif choice == options_len - 1:  # Back
            return

# -------------------- entry --------------------

def main():
    curses.wrapper(run_setup_namd)

if __name__ == "__main__":
    main()
