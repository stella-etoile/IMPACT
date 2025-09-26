import os
import re
import time
import curses
from curses import textpad, ascii
import tempfile
import subprocess
import shutil
from typing import List, Tuple, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DEFAULT_CONF = os.path.join(ROOT_DIR, "IMPACT.conf")
SETUP_SH = os.path.join(ROOT_DIR, "bin", "impact_setup_pdb.sh")
LOG_DIR = os.path.join(ROOT_DIR, "log")
os.makedirs(LOG_DIR, exist_ok=True)

SUBTITLE = "Setup PDB"
EXAMPLES_ADD = "Add: e.g., 06 07,08 09"
EXAMPLES_REMOVE = "Remove: e.g., 06 07,08 09"

def stdbuf_prefix():
    return ['stdbuf','-oL','-eL'] if shutil.which('stdbuf') else []

def find_conf():
    if os.path.exists(DEFAULT_CONF):
        return DEFAULT_CONF
    p = os.path.join(os.getcwd(), "IMPACT.conf")
    return p if os.path.exists(p) else None

def read_config():
    conf = find_conf()
    pdb_dir = "."
    pdb_proc_dir = "."
    slurm = {}
    if conf and os.path.exists(conf):
        base = os.path.dirname(conf)
        with open(conf) as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("PDB_DIR"):
                    _, v = s.split("=", 1)
                    pdb_dir = os.path.abspath(os.path.join(base, v.strip().strip('"').strip("'")))
                elif s.startswith("PDB_PROC_DIR"):
                    _, v = s.split("=", 1)
                    pdb_proc_dir = os.path.abspath(os.path.join(base, v.strip().strip('"').strip("'")))
                elif s.startswith("SLURM_"):
                    k, v = s.split("=", 1)
                    slurm[k.strip()] = v.strip().strip('"').strip("'")
    has_slurm = (
        bool(slurm.get("SLURM_ACCOUNT")) and
        bool(slurm.get("SLURM_PARTITION")) and
        bool(slurm.get("SLURM_CMD"))
    )
    return pdb_dir, pdb_proc_dir, slurm, has_slurm, (conf if conf else DEFAULT_CONF)

def wrap_tokens(stdscr, y, x, w, tokens, hi_idx=None, attr_hi=0, attr_norm=0):
    if w <= 4:
        return 0
    cx, cy = x, y
    used = 1
    for i, tok in enumerate(tokens):
        t = tok + " "
        if cx + len(t) > w - 2:
            cy += 1; cx = x; used += 1
        attr = attr_hi if (hi_idx is not None and i == hi_idx) else attr_norm
        try: stdscr.addstr(cy, cx, t, attr)
        except curses.error: pass
        cx += len(t)
    return used

def wrap_line(s, w):
    if w <= 0: return [""]
    out, cur = [], ""
    for tok in s.split():
        if len(cur) + len(tok) + (1 if cur else 0) <= w:
            cur = (cur + " " + tok).strip()
        else:
            out.append(cur); cur = tok
    if cur: out.append(cur)
    return out or [""]

def list_pdbs(pdb_dir):
    if not os.path.isdir(pdb_dir): return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(pdb_dir) if f.lower().endswith(".pdb"))

def list_processed(pdb_proc_dir):
    if not os.path.isdir(pdb_proc_dir): return set()
    out = set()
    for f in os.listdir(pdb_proc_dir):
        p = os.path.join(pdb_proc_dir, f)
        out.add(f if os.path.isdir(p) else os.path.splitext(f)[0])
    return out

def tokens_from(s):
    s = s.replace(",", " ")
    return [t.strip() for t in s.split() if t.strip()]

def init_colors():
    err_attr = curses.A_BOLD
    hint_attr = curses.A_DIM
    if curses.has_colors():
        curses.start_color()
        try: curses.use_default_colors()
        except Exception: pass
        curses.init_pair(1, curses.COLOR_RED, -1)
        err_attr = curses.color_pair(1) | curses.A_BOLD
        if getattr(curses, "COLORS", 8) >= 256:
            curses.init_pair(10, 242, -1)
            hint_attr = curses.color_pair(10)
    return err_attr, hint_attr

def draw(stdscr, title, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection,
         pdb_cursor, focus, menu_cursor, has_slurm, slurm, msg="", msg_attr=0, err_attr=0,
         slurm_override=False):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    tx = max(0, (w - len(title)) // 2)
    try:
        stdscr.addstr(1, tx, title, curses.A_BOLD)
        stdscr.addstr(3, 2, "Focus: Tab • Esc/0 Back • Enter activate", hint_attr)
        stdscr.addstr(4, 2, "Menu: ↑/↓ or j/k • 1–7 shortcuts", hint_attr)
        stdscr.addstr(5, 2, "PDBs: ←/→ or h/l • Enter toggles", hint_attr)
        stdscr.addstr(7, 2, f"PDB_DIR: {pdb_dir}", hint_attr)
        stdscr.addstr(8, 2, f"PDB_PROC_DIR: {pdb_proc_dir}", hint_attr)
        stdscr.addstr(10, 2, "Available PDBs:", curses.A_UNDERLINE)
    except curses.error:
        pass

    hi_idx = pdb_cursor if (pdbs and focus == "pdb") else None
    lines_used = wrap_tokens(stdscr, 11, 2, w, pdbs, hi_idx=hi_idx, attr_hi=curses.A_REVERSE, attr_norm=0)

    cur_y = 11 + max(1, lines_used)
    try: stdscr.addstr(cur_y, 2, "Already processed:", curses.A_UNDERLINE)
    except curses.error: pass
    shown_proc = sorted(set(pdbs) & set(processed))
    proc_line = " ".join(shown_proc) if shown_proc else "(none)"
    for j, line in enumerate(wrap_line(proc_line, max(10, w - 4))):
        try: stdscr.addstr(cur_y + 1 + j, 2, line)
        except curses.error: pass

    cur2_y = cur_y + 2 + max(1, len(wrap_line(proc_line, max(10, w - 4))))
    try: stdscr.addstr(cur2_y, 2, "Current selection:", curses.A_UNDERLINE)
    except curses.error: pass
    sel_line = " ".join(sorted(selection)) if selection else "(empty)"
    for k, line in enumerate(wrap_line(sel_line, max(10, w - 4))):
        try: stdscr.addstr(cur2_y + 1 + k, 2, line)
        except curses.error: pass

    menu_y = cur2_y + 3 + max(1, len(wrap_line(sel_line, max(10, w - 4))))
    options = [
        "1) Add all nonprocessed (recommended)",
        "2) Add all",
        "3) Add selection",
        "4) Remove selection",
        "5) Remove all",
        "6) Generate current selection (local)",
        "7) Submit all (SLURM, show progress)",
        "0) Back"
    ]
    for idx, opt in enumerate(options):
        attr = 0
        text = opt
        if idx == 6 and not has_slurm:
            if slurm_override:
                text += "  [FORCED]"
            else:
                text += "  [disabled — press B to force]"
                attr = hint_attr
        if focus == "menu" and idx == menu_cursor:
            attr |= curses.A_REVERSE
        try: stdscr.addstr(menu_y + idx, 2, text, attr)
        except curses.error: pass

    info_y = menu_y + len(options) + 1
    if has_slurm:
        acct = slurm.get("SLURM_ACCOUNT", "(none)")
        part = slurm.get("SLURM_PARTITION", "(none)")
        cmd  = slurm.get("SLURM_CMD", "(none)")
        try: stdscr.addstr(info_y, 2, f"SLURM target: account={acct} partition={part} via {cmd}", hint_attr)
        except curses.error: pass
    else:
        missing = [k for k in ("SLURM_ACCOUNT","SLURM_PARTITION","SLURM_CMD") if not slurm.get(k)]
        try:
            stdscr.addstr(info_y, 2, "SLURM disabled: missing " + ", ".join(missing), err_attr)
            stdscr.addstr(info_y + 1, 2,
                          f"Current SLURM config: ACCOUNT={slurm.get('SLURM_ACCOUNT','(none)')} "
                          f"PARTITION={slurm.get('SLURM_PARTITION','(none)')} "
                          f"CMD={slurm.get('SLURM_CMD','(none)')}", hint_attr)
            stdscr.addstr(info_y + 2, 2, "Add these to IMPACT.conf to enable SLURM, or press B to force.", hint_attr)
        except curses.error:
            pass

    if msg:
        try: stdscr.addstr(info_y + 4, 2, msg[: max(0, w - 4)], msg_attr)
        except curses.error: pass

    stdscr.refresh()
    return menu_y, len(options), options

def prompt(stdscr, top_line, hint_attr, y_start=None):
    h, w = stdscr.getmaxyx()
    if y_start is None: y_start = h - 6
    try:
        stdscr.addstr(y_start, 2, top_line, hint_attr)
        stdscr.addstr(y_start + 1, 2, "Separate by space or comma • Esc=Back", hint_attr)
        stdscr.addstr(y_start + 3, 2, "> ")
    except curses.error: pass
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
    if cancelled["v"]: return None
    return s

def compute_input_y(stdscr, pdbs, processed, selection):
    h, w = stdscr.getmaxyx()
    pdb_lines = max(1, len(wrap_line(" ".join(pdbs), max(10, w - 4))))
    proc_lines = max(1, len(wrap_line(" ".join(sorted(set(pdbs) & set(processed))) or "(none)", max(10, w - 4))))
    sel_lines = max(1, len(wrap_line(" ".join(sorted(selection)) if selection else "(empty)", max(10, w - 4))))
    cur_y = 11 + pdb_lines
    cur2_y = cur_y + 1 + proc_lines + 1
    menu_y = cur2_y + 2 + sel_lines + 1
    return menu_y + 10

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

def draw_progress(stdscr, y0, name, idx, total, started_at, item_started_at,
                  avg_sec, out_tail, err_tail, hint_attr, err_attr, split_label,
                  extra_line: Optional[str] = None):
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
        stdscr.addstr(y0, 2, "Running… (q/Esc=cancel, v=logs, s=split)", hint_attr)
        if extra_line:
            stdscr.addstr(y0, 60, f"{extra_line}", hint_attr)
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

def _run(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        res = subprocess.run(cmd, text=True, capture_output=True)
        return res.returncode, res.stdout or "", res.stderr or ""
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except Exception as e:
        return 1, "", str(e)

def parse_jobid_from_sbatch(out: str) -> Optional[str]:
    s = (out or "").strip()
    m = re.search(r"Submitted\s+batch\s+job\s+(\d+)", s)
    if m: return m.group(1)
    m = re.search(r"\b(\d{5,})\b", s)
    return m.group(1) if m else None

_TERMINAL = {"COMPLETED","FAILED","CANCELLED","TIMEOUT","OUT_OF_MEMORY","PREEMPTED","BOOT_FAIL"}

def slurm_state(jobid: str) -> Optional[str]:
    rc, out, err = _run(["sacct", "-j", jobid, "-n", "--format=State"])
    if rc == 0 and out.strip() and "disabled" not in (out+err).lower():
        return out.strip().splitlines()[0].split()[0]
    rc, out, _ = _run(["scontrol", "show", "job", jobid])
    if rc == 0 and out:
        m = re.search(r"JobState=([A-Za-z_]+)", out)
        if m:
            return m.group(1)
    rc, out, _ = _run(["squeue", "-j", jobid, "-h", "-o", "%T"])
    if rc == 0:
        st = out.strip()
        if st:
            return st
    return "UNKNOWN_GONE"

def is_terminal(state: Optional[str]) -> bool:
    if not state: return False
    u = state.upper()
    return u in _TERMINAL or u == "UNKNOWN_GONE"

def slurm_log_paths(jobname: str) -> Tuple[str, str]:
    outp = os.path.join(LOG_DIR, f"{jobname}.out")
    errp = os.path.join(LOG_DIR, f"{jobname}.err")
    return outp, errp

def run_local_with_progress(stdscr, selections, conf_path, script_path, hint_attr, err_attr):
    if not selections: return False, "Selection is empty"
    if not os.path.isfile(script_path): return False, f"Missing {script_path}"
    if not os.path.isfile(conf_path): return False, f"Missing {conf_path}"
    total = len(selections)
    t_start = time.time()
    times = []
    verbose = True
    splits = [(0.7, 0.3), (0.5, 0.5), (0.3, 0.7)]
    split_idx = 0
    stdscr.nodelay(True)
    try:
        for idx, name in enumerate(selections, 1):
            with tempfile.NamedTemporaryFile("w", delete=False, prefix=f"{name}_", suffix=".sel") as fsel:
                fsel.write(name + "\n")
                sel_path = fsel.name
            out_path = os.path.join(tempfile.gettempdir(), f"impact_{name}.out")
            err_path = os.path.join(tempfile.gettempdir(), f"impact_{name}.err")
            out_f = open(out_path, "w"); err_f = open(err_path, "w")
            cmd = stdbuf_prefix() + [script_path, "--local", "--conf", conf_path, sel_path]
            p = subprocess.Popen(cmd, stdout=out_f, stderr=err_f, text=True)
            t0 = time.time()
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
                    elif ch in (ord('v'), ord('V')): verbose = not verbose
                    elif ch in (ord('s'), ord('S')): split_idx = (split_idx + 1) % len(splits)
                except curses.error:
                    pass
                rc = p.poll()
                h, w = stdscr.getmaxyx()
                y0 = 2
                available_rows = max(0, (h - (y0 + 5)) - 2)
                if verbose and available_rows >= 6:
                    so, se = splits[split_idx]
                    out_n = max(5, int(available_rows * so))
                    err_n = max(5, available_rows - out_n)
                    out_tail = tail_lines(out_path, n=out_n, w=w)
                    err_tail = tail_lines(err_path, n=err_n, w=w)
                    split_label = f"{int(so*100)}/{int(se*100)}"
                else:
                    out_tail = tail_lines(out_path, n=5, w=w)
                    err_tail = tail_lines(err_path, n=5, w=w)
                    split_label = "compact"
                avg = (sum(times) / len(times)) if times else max(1.0, time.time() - t0)
                draw_progress(stdscr, y0, name, idx, total, t_start, t0, avg, out_tail, err_tail, hint_attr, err_attr, split_label)
                if rc is not None: break
                time.sleep(0.1)
            out_f.close(); err_f.close()
            dt = time.time() - t0
            try: os.unlink(sel_path)
            except Exception: pass
            if rc != 0:
                h, w = stdscr.getmaxyx()
                long_err = "\n".join(tail_lines(err_path, n=max(12, h - 10), w=w))
                stdscr.nodelay(False)
                stdscr.clear()
                try:
                    stdscr.addstr(2, 2, f"Error on {name} (exit {rc})", err_attr)
                    stdscr.addstr(4, 2, long_err, err_attr)
                    stdscr.addstr(h - 2, 2, "Press any key…", hint_attr)
                except curses.error:
                    pass
                stdscr.refresh()
                stdscr.getch()
                return False, f"Error on {name} (exit {rc})"
            times.append(dt)
    finally:
        stdscr.nodelay(False)
    total_dt = int(time.time() - t_start)
    return True, f"Completed {total} in {total_dt//60}m {total_dt%60}s"

def run_slurm_submit_sequential_progress(stdscr, selections, conf_path, script_path, hint_attr, err_attr, slurm_override=False):
    if not selections: return False, "Selection is empty"
    if not os.path.isfile(script_path): return False, f"Missing {script_path}"
    if not os.path.isfile(conf_path): return False, f"Missing {conf_path}"
    total = len(selections)
    t_start = time.time()
    times = []
    stdscr.nodelay(True)
    try:
        for idx, name in enumerate(selections, 1):
            with tempfile.NamedTemporaryFile("w", delete=False, prefix=f"{name}_", suffix=".sel") as fsel:
                fsel.write(name + "\n")
                sel_path = fsel.name
            env = os.environ.copy()
            cmd = [script_path, "--slurm"] + (["--force"] if slurm_override else []) + ["--conf", conf_path, sel_path]
            res = subprocess.run(cmd, text=True, capture_output=True, env=env)
            try: os.unlink(sel_path)
            except Exception: pass
            if res.returncode != 0:
                msg = (res.stderr or res.stdout or "").strip()
                stdscr.nodelay(False)
                return False, f"{name}: {msg[-300:]}"
            jobid = parse_jobid_from_sbatch((res.stdout or "") + " " + (res.stderr or ""))
            if not jobid:
                stdscr.nodelay(False)
                return False, f"{name}: could not parse job id"
            jname = f"IMPACT_{name}"
            outp, errp = slurm_log_paths(jname)
            os.makedirs(LOG_DIR, exist_ok=True)
            open(outp, "a").close(); open(errp, "a").close()
            t0 = time.time()
            verbose = True
            splits = [(0.7, 0.3), (0.5, 0.5), (0.3, 0.7)]
            split_idx = 0
            while True:
                try:
                    ch = stdscr.getch()
                    if ch in (27, ord('q')):
                        _run(["scancel", jobid])
                        stdscr.nodelay(False)
                        return False, f"Cancelled {name}"
                    elif ch in (ord('v'), ord('V')): verbose = not verbose
                    elif ch in (ord('s'), ord('S')): split_idx = (split_idx + 1) % len(splits)
                except curses.error:
                    pass
                state = slurm_state(jobid) or "SUBMITTED"
                h, w = stdscr.getmaxyx()
                y0 = 2
                available_rows = max(0, (h - (y0 + 5)) - 2)
                if verbose and available_rows >= 6:
                    so, se = splits[split_idx]
                    out_n = max(5, int(available_rows * so))
                    err_n = max(5, available_rows - out_n)
                    out_tail = tail_lines(outp, n=out_n, w=w)
                    err_tail = tail_lines(errp, n=err_n, w=w)
                    split_label = f"{int(so*100)}/{int(se*100)}"
                else:
                    out_tail = tail_lines(outp, n=5, w=w)
                    err_tail = tail_lines(errp, n=5, w=w)
                    split_label = "compact"
                avg = (sum(times) / len(times)) if times else max(1.0, time.time() - t0)
                draw_progress(stdscr, y0, f"{name} [{state}]", idx, total, t_start, t0, avg, out_tail, err_tail, hint_attr, err_attr, split_label)
                if is_terminal(state):
                    dt = time.time() - t0
                    times.append(dt)
                    break
                time.sleep(0.5)
    finally:
        stdscr.nodelay(False)
    total_dt = int(time.time() - t_start)
    return True, f"All {total} jobs reached terminal state in {total_dt//60}m {total_dt%60}s"

def run_slurm_submit(selections, conf_path, script_path):
    if not selections: return False, "Selection is empty"
    if not os.path.isfile(script_path): return False, f"Missing {script_path}"
    if not os.path.isfile(conf_path): return False, f"Missing {conf_path}"
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        for n in selections:
            f.write(n + "\n")
        sel_path = f.name
    cmd = [script_path, "--slurm", "--conf", conf_path, sel_path]
    try:
        res = subprocess.run(cmd, text=True, capture_output=True)
    finally:
        try: os.unlink(sel_path)
        except Exception: pass
    if res.returncode == 0:
        out = (res.stdout or "").strip()
        m = re.search(r"Submitted\s+batch\s+job\s+(\d+)", out)
        if m: return True, f"Submitted: job {m.group(1)}"
        return True, f"Submitted: {out[-2000:]}" if out else "Submitted"
    else:
        err = (res.stderr or res.stdout or "").strip()
        return False, f"Error ({res.returncode}): {err[-2000:]}"

def run_slurm_submit_all_progress(*args, **kwargs):
    return run_slurm_submit_sequential_progress(*args, **kwargs)

def run_setup_pdb(stdscr, inherited_hint_attr=None):
    pdb_dir, pdb_proc_dir, slurm_cfg, has_slurm, conf_path = read_config()
    curses.curs_set(0)
    stdscr.keypad(True)
    err_attr, hint_attr_local = init_colors()
    hint_attr = inherited_hint_attr if inherited_hint_attr is not None else hint_attr_local
    selection = set()
    focus = "menu"
    menu_cursor = 0
    pdb_cursor = 0
    slurm_override = False
    def skip_disabled(idx, direction, total_opts):
        if has_slurm or slurm_override: return idx
        if idx == 6: return (idx + direction) % total_opts
        return idx
    while True:
        pdbs = list_pdbs(pdb_dir)
        processed = list_processed(pdb_proc_dir)
        if pdb_cursor >= len(pdbs):
            pdb_cursor = max(0, len(pdbs) - 1)
        draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, err_attr=err_attr, slurm_override=slurm_override)
        k = stdscr.getch()
        choice = None
        if k in (9, curses.KEY_BTAB):
            focus = "pdb" if focus == "menu" else "menu"
        elif k in (curses.KEY_UP, ord('k')):
            focus = "menu"; menu_cursor = (menu_cursor - 1) % 8; menu_cursor = skip_disabled(menu_cursor, -1, 8)
        elif k in (curses.KEY_DOWN, ord('j')):
            focus = "menu"; menu_cursor = (menu_cursor + 1) % 8; menu_cursor = skip_disabled(menu_cursor, +1, 8)
        elif k in (curses.KEY_LEFT, ord('h')):
            if pdbs: focus = "pdb"; pdb_cursor = max(0, pdb_cursor - 1)
        elif k in (curses.KEY_RIGHT, ord('l')):
            if pdbs: focus = "pdb"; pdb_cursor = min(len(pdbs) - 1, pdb_cursor + 1)
        elif k in (ord('b'), ord('B')):
            slurm_override = not slurm_override
        elif k in (10, 13, curses.KEY_ENTER):
            if focus == "menu":
                if (not has_slurm) and (menu_cursor == 6) and (not slurm_override):
                    draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, "SLURM not configured. Press B to force submission anyway.", err_attr, err_attr, slurm_override=slurm_override)
                    stdscr.getch()
                else:
                    choice = menu_cursor
            else:
                if pdbs:
                    name = pdbs[pdb_cursor]
                    if name in selection: selection.discard(name)
                    else: selection.add(name)
        elif k in (ord('0'),):
            focus = "menu"; choice = 7
        elif k in (ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6'), ord('7')):
            focus = "menu"
            desired = int(chr(k)) - 1
            if (not has_slurm) and (desired == 6) and (not slurm_override):
                draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, "SLURM not configured. Press B to force submission anyway.", err_attr, err_attr, slurm_override=slurm_override)
                stdscr.getch()
            else:
                choice = desired
        elif k in (27, ord('q')):
            focus = "menu"; choice = 7
        if choice is None:
            continue
        if choice == 0:
            nonprocessed = [t for t in pdbs if t not in processed]
            if not nonprocessed:
                draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, "All available are already processed", err_attr, err_attr, slurm_override=slurm_override)
                stdscr.getch()
            else:
                selection.update(nonprocessed)
        elif choice == 1:
            selection = set(pdbs)
        elif choice == 2:
            y_in = compute_input_y(stdscr, pdbs, processed, selection)
            s = prompt(stdscr, EXAMPLES_ADD, hint_attr, y_start=y_in)
            if s:
                toks = tokens_from(s)
                invalid = [t for t in toks if t not in pdbs]
                valid = [t for t in toks if t in pdbs]
                if valid: selection.update(valid)
                if invalid:
                    draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, "Invalid: " + ", ".join(invalid), err_attr, err_attr, slurm_override=slurm_override)
                    stdscr.getch()
        elif choice == 3:
            y_in = compute_input_y(stdscr, pdbs, processed, selection)
            s = prompt(stdscr, EXAMPLES_REMOVE, hint_attr, y_start=y_in)
            if s:
                toks = tokens_from(s)
                not_in_list = [t for t in toks if t not in pdbs]
                not_selected = [t for t in toks if t in pdbs and t not in selection]
                to_remove = [t for t in toks if t in selection]
                for t in to_remove: selection.discard(t)
                msgs = []
                if not_in_list: msgs.append("Not found: " + ", ".join(not_in_list))
                if not_selected: msgs.append("Not in selection: " + ", ".join(not_selected))
                if msgs:
                    draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, " | ".join(msgs), err_attr, err_attr, slurm_override=slurm_override)
                    stdscr.getch()
        elif choice == 4:
            selection = set()
        elif choice == 5:
            sels = sorted(selection)
            ok, msg = run_local_with_progress(stdscr, sels, conf_path=conf_path, script_path=SETUP_SH, hint_attr=hint_attr, err_attr=err_attr)
            draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, msg, 0 if ok else err_attr, err_attr, slurm_override=slurm_override)
            stdscr.getch()
        elif choice == 6:
            sels = sorted(selection)
            ok, msg = run_slurm_submit_all_progress(stdscr, sels, conf_path=conf_path, script_path=SETUP_SH, hint_attr=hint_attr, err_attr=err_attr, slurm_override=slurm_override)
            draw(stdscr, SUBTITLE, hint_attr, pdb_dir, pdb_proc_dir, pdbs, processed, selection, pdb_cursor, focus, menu_cursor, has_slurm, slurm_cfg, msg, 0 if ok else err_attr, err_attr, slurm_override=slurm_override)
            stdscr.getch()
        elif choice == 7:
            return

def main():
    curses.wrapper(run_setup_pdb)

if __name__ == "__main__":
    main()