# bin/impact_run_namd.py
import os
import re
import subprocess
import curses

CONF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "IMPACT.conf")
STAGES = ["mini", "equil", "NPT1", "NPT2"]

def load_conf(path):
    c = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                c[k.strip()] = v.strip()
    return c

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

def parse_combined(name):
    m = re.match(r"^(.+)_([0-9]+)$", name)
    if not m:
        return None, None
    return m.group(1), m.group(2)

def find_stage_script(stage_dir, combined, stage):
    cand = [
        os.path.join(stage_dir, f"{combined}-{stage}.sh"),
        os.path.join(stage_dir, f"{combined}-{stage.upper()}.sh"),
    ]
    for p in cand:
        if os.path.isfile(p):
            return p
    shs = [os.path.join(stage_dir, x) for x in os.listdir(stage_dir) if x.endswith(".sh")]
    return shs[0] if shs else None

def list_targets_from_namd(namd_root):
    items = []
    if not os.path.isdir(namd_root):
        return items
    for entry in sorted(os.listdir(namd_root)):
        run_dir = os.path.join(namd_root, entry)
        if not os.path.isdir(run_dir):
            continue
        prefix, trial = parse_combined(entry)
        if not prefix:
            continue
        chain = []
        have = []
        for st in STAGES:
            sd = os.path.join(run_dir, st)
            if os.path.isdir(sd):
                sh = find_stage_script(sd, entry, st)
                chain.append({"stage": st, "dir": sd, "script": sh})
                if sh:
                    have.append(st)
        if chain:
            label = f"{entry} :: " + (" → ".join(have) if have else "no scripts")
            items.append({"label": label, "combined": entry, "dir": run_dir, "chain": chain})
    return items

def parse_jobid(s):
    m = re.search(r"\b(\d{3,})\b", (s or "").strip())
    return m.group(1) if m else "?"

def sbatch_submit(sbatch, script_path, extra=None, dependency=None, cwd=None):
    cmd = [sbatch]
    if dependency:
        cmd.append(f"--dependency=afterok:{dependency}")
    if extra:
        cmd += extra
    cmd.append(script_path)
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    ok = (r.returncode == 0)
    out = r.stdout.strip() if r.stdout else r.stderr.strip()
    return ok, parse_jobid(out), out

def job_running(jobid):
    if jobid in ("?", "", None):
        return False
    r = subprocess.run(["squeue", "-j", str(jobid)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return (r.returncode == 0) and (str(jobid) in r.stdout)

def run_vmd(aux_dir, combined, run_dir):
    tcl = os.path.join(aux_dir, "mini.tcl")
    if not os.path.isfile(tcl):
        return
    cmd = 'module load vmd && vmd -dispdev text -e "{}" -args "{}"'.format(tcl.replace('"', '\\"'), combined.replace('"', '\\"'))
    subprocess.run(["bash", "-lc", cmd], cwd=run_dir)

def cleanup_restart_files(mini_dir):
    try:
        for f in os.listdir(mini_dir):
            if f.endswith(".restart.") or ".restart." in f:
                try:
                    os.remove(os.path.join(mini_dir, f))
                except Exception:
                    pass
    except Exception:
        pass

def move_lf_pdb(run_dir, combined):
    src = os.path.join(run_dir, "mini", f"{combined}-mini-LF.pdb")
    dst = os.path.join(run_dir, f"{combined}-mini-LF.pdb")
    if os.path.isfile(src):
        try:
            os.replace(src, dst)
        except Exception:
            pass

def submit_chain_protocol(run_dir, combined, sbatch, sbatch_extra, aux_dir):
    mini_dir = os.path.join(run_dir, "mini")
    equil_dir = os.path.join(run_dir, "equil")
    npt1_dir = os.path.join(run_dir, "NPT1")
    npt2_dir = os.path.join(run_dir, "NPT2")
    mini_sh = find_stage_script(mini_dir, combined, "mini") if os.path.isdir(mini_dir) else None
    equil_sh = find_stage_script(equil_dir, combined, "equil") if os.path.isdir(equil_dir) else None
    npt1_sh = find_stage_script(npt1_dir, combined, "NPT1") if os.path.isdir(npt1_dir) else None
    npt2_sh = find_stage_script(npt2_dir, combined, "NPT2") if os.path.isdir(npt2_dir) else None
    if not mini_sh:
        return False, "mini script missing"
    ok1, jid1, out1 = sbatch_submit(sbatch, mini_sh, extra=sbatch_extra, cwd=mini_dir)
    if not ok1:
        return False, f"mini submit failed: {out1}"
    while job_running(jid1):
        curses.napms(10000)
    cleanup_restart_files(mini_dir)
    run_vmd(aux_dir, combined, run_dir)
    move_lf_pdb(run_dir, combined)
    if not equil_sh:
        return False, "equil script missing"
    ok2, jid2, out2 = sbatch_submit(sbatch, equil_sh, extra=sbatch_extra, cwd=equil_dir)
    if not ok2:
        return False, f"equil submit failed: {out2}"
    if not npt1_sh:
        return False, "NPT1 script missing"
    ok3, jid3, out3 = sbatch_submit(sbatch, npt1_sh, extra=sbatch_extra, dependency=jid2, cwd=npt1_dir)
    if not ok3:
        return False, f"NPT1 submit failed: {out3}"
    if not npt2_sh:
        return False, "NPT2 script missing"
    ok4, jid4, out4 = sbatch_submit(sbatch, npt2_sh, extra=sbatch_extra, dependency=jid3, cwd=npt2_dir)
    if not ok4:
        return False, f"NPT2 submit failed: {out4}"
    return True, f"mini={jid1}, equil={jid2}, npt1={jid3}, npt2={jid4}"

def draw(stdscr, items, sel, idx, msg):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    center(stdscr, 1, "Run NAMD: mini → equil → NPT1 → NPT2", curses.A_BOLD)
    center(stdscr, 3, "↑/↓ move • Space select • A all • N none • Enter run • R refresh • Esc back", curses.A_DIM)
    top = 5
    maxv = max(1, h - top - 3)
    if not items:
        center(stdscr, top, "No runnable targets found in 2_output/. Press R to rescan or Esc to go back.", curses.A_DIM)
    else:
        view_start = 0
        if len(items) > maxv:
            view_start = max(0, min(idx - maxv + 1, len(items) - maxv))
        for i in range(view_start, min(len(items), view_start + maxv)):
            mark = "[x]" if sel[i] else "[ ]"
            a = curses.A_REVERSE if i == idx else 0
            safe_addstr(stdscr, top + (i - view_start), 2, f"{mark} {items[i]['label']}"[:max(0, w - 4)], a)
    if msg:
        safe_addstr(stdscr, h - 2, 2, msg[:max(0, w - 4)], curses.A_BOLD)
    stdscr.refresh()

def run_run_namd(stdscr, hint_attr):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    conf = load_conf(CONF_PATH)
    out2 = conf.get("NAMD_PROC_DIR", "2_output/").strip() or "2_output/"
    if not out2.endswith("/"):
        out2 += "/"
    namd_root = os.path.join(base_dir, out2)
    aux_dir = os.path.join(base_dir, "aux")
    items = list_targets_from_namd(namd_root)
    sel = [False] * len(items)
    idx = 0
    msg = ""
    sbatch = conf.get("SLURM_CMD", "sbatch").strip() or "sbatch"
    extra = conf.get("SBATCH_EXTRA", "").strip()
    sbatch_extra = extra.split() if extra else []
    curses.curs_set(0)
    stdscr.keypad(True)
    while True:
        draw(stdscr, items, sel, idx, msg)
        k = stdscr.getch()
        if k in (27, ord('q')):
            return
        if k in (ord('r'), ord('R')):
            items = list_targets_from_namd(namd_root)
            sel = [False] * len(items)
            idx = 0
            msg = ""
            continue
        if not items:
            continue
        if k in (curses.KEY_UP, ord('k')):
            idx = (idx - 1) % len(items)
        elif k in (curses.KEY_DOWN, ord('j')):
            idx = (idx + 1) % len(items)
        elif k == ord(' '):
            sel[idx] = not sel[idx]
        elif k in (ord('a'), ord('A')):
            sel = [True] * len(items)
        elif k in (ord('n'), ord('N')):
            sel = [False] * len(items)
        elif k in (10, 13, curses.KEY_ENTER):
            chosen = [items[i] for i, s in enumerate(sel) if s]
            if not chosen:
                msg = "No selections"
                continue
            okc = 0
            failc = 0
            last = ""
            for it in chosen:
                ok, detail = submit_chain_protocol(it["dir"], it["combined"], sbatch, sbatch_extra, aux_dir)
                if ok:
                    okc += 1
                    last = f"{it['combined']}: {detail}"
                else:
                    failc += 1
                    last = f"{it['combined']}: {detail}"
            msg = f"Chains submitted={okc} failed={failc}. {last}"