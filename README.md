# IMPACT — Interactive Molecular Processing and Analysis for Contact/TCRs

**TUI toolkit to stage and launch NAMD preprocessing on local or SLURM systems.**  
Author: Stella Lee (kangheelee@uchicago.edu)

> Status: **alpha** — actively evolving. The core setup flow works; several menu items are placeholders (see _Not Yet Implemented_).

---

## Table of Contents

- [IMPACT — Interactive Molecular Processing and Analysis for Contact/TCRs](#impact--interactive-molecular-processing-and-analysis-for-contacttcrs)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Repository Layout](#repository-layout)
  - [Requirements](#requirements)
  - [Configuration](#configuration)
  - [Launching the TUI](#launching-the-tui)
  - [Workflows](#workflows)
    - [Setup NAMD (local)](#setup-namd-local)
    - [Setup NAMD (SLURM)](#setup-namd-slurm)
    - [Editing Config In-App](#editing-config-in-app)
  - [Keyboard Cheatsheet](#keyboard-cheatsheet)
  - [Logs, Backups, and Output](#logs-backups-and-output)
  - [SLURM Notes](#slurm-notes)
  - [Troubleshooting](#troubleshooting)
  - [Not Yet Implemented](#not-yet-implemented)
  - [Roadmap Ideas](#roadmap-ideas)
  - [License](#license)

---

## Overview

IMPACT is a terminal UI (TUI) to help you:
- Discover available **PDB**s,
- Select sets to process,
- Run the **initial NAMD system generation** (`aux/init_setup.tcl` + `NAMD/gen_system.tcl`) either **locally** or via **SLURM**,
- Watch **live progress** with a split stderr/stdout tail,
- Manage and **restore config backups**.

The TUI is built with Python `curses` and shell helpers.

**Key entry points**
- `IMPACT.py` — main menu / app launcher
- `bin/impact_setup_menu.py` — “Setup NAMD” TUI
- `bin/impact_config_editor.py` — in-app editor with backups
- `bin/impact_setup.sh` — orchestrates local runs and one-job-per-selection SLURM submissions

> Minimum terminal size for the main menu is **87×26**; a bypass exists but rendering may degrade below that.

---

## Repository Layout

```
IMPACT/
├─ IMPACT.py
├─ IMPACT.conf
├─ bin/
│  ├─ impact_setup_menu.py
│  ├─ impact_config_editor.py
│  └─ impact_setup.sh
├─ NAMD/
│  └─ gen_system.tcl
├─ aux/
│  └─ init_setup.tcl
├─ 1_output/                # default processed output root
├─ log/                     # SLURM/local logs
└─ conf_backups/            # auto-made when saving via config editor
```

---

## Requirements

- **Python 3.8+**
- **VMD** available on PATH or as a module (`module load vmd`); headless is used: `-dispdev text`
- For SLURM mode: working SLURM CLI (`sbatch`, `squeue`, `sacct`, `scontrol`)
- A terminal that supports `curses` (most UNIX terminals do)
- Your input **PDB files** in `NAMD/pdb_files_ranked_0/*.pdb` (configurable)

---

## Configuration

Edit `IMPACT.conf` (or use the in-app editor; see below):

```ini
# IMPACT - Interactive Molecular Processing and Analysis for Contact/TCRs

PDB_DIR = NAMD/pdb_files_ranked_0
PDB_PROC_DIR = 1_output/

SLURM_ACCOUNT = SLURM_ACCOUNT_NAME
SLURM_PARTITION = SLURM_PARTITION_NAME
SLURM_CMD = sbatch # or srun or sinteractive
```

- `PDB_DIR`: directory containing source `*.pdb`
- `PDB_PROC_DIR`: destination root; each selection is copied to its own subfolder
- `SLURM_*`: needed to enable SLURM menu item (can be forced in-app with **B** if omitted)

Backups are auto-written to `conf_backups/` when you **Save** via the config editor.

---

## Launching the TUI

From the project root:

```bash
python3 IMPACT.py
```

Minimum terminal size: **87×26**. If smaller, a **bypass** is offered (press **B** twice), but layout may wrap.

Main menu:
- `1) Setup NAMD`
- `2) Run NAMD` *(placeholder)*
- `3) Run GaMD` *(placeholder)*
- `4) Change config`
- `0) Exit`

Controls: **↑/↓** move • **Enter** select • **0–4** quick • **Esc** back

---

## Workflows

### Setup NAMD (local)

1. Open `1) Setup NAMD`.
2. Use **←/→** to move the cursor over PDB names; **Enter** to toggle selection.
3. Or use menu items:
   - `1) Add all nonprocessed (recommended)`
   - `2) Add all`
   - `3) Add selection` (free-typed tokens like `06 07,08`)
   - `4) Remove selection`
   - `5) Remove all`
4. Choose `6) Generate current selection (local)`.

The shell driver `bin/impact_setup.sh` will, for each selection:
- Create `PDB_PROC_DIR/<NAME>/`
- Copy `<PDB_DIR>/<NAME>.pdb` into the folder
- Invoke VMD headless:  
  `vmd -dispdev text -e aux/init_setup.tcl -args <base_dir> NAMD/gen_system.tcl <NAME> "1"`

A **live progress** view displays a progress bar, ETA, and a split pane of `stderr`/`stdout` tails. Keys:
- **q/Esc** cancel current run
- **v** toggle logs
- **s** cycle split ratios (70/30, 50/50, 30/70)

### Setup NAMD (SLURM)

1. Ensure `SLURM_ACCOUNT`, `SLURM_PARTITION`, and `SLURM_CMD` are set in `IMPACT.conf`.  
   If not, you can **press B** to *force* the SLURM submission anyway.
2. Choose `7) Generate current selection (SLURM)`.

Behavior:
- One **job per selection** is submitted with job name `IMPACT_<NAME>`
- SLURM script requests `--time=00:10:00`, `--cpus-per-task=24`, uses your configured account/partition
- Logs go to `log/%x.out` and `log/%x.err` (where `%x` is the JobName)

The UI monitors each job by `jobid`, showing status from `squeue/sacct` and live log tails when files appear. Keys mirror local mode.

### Editing Config In-App

From main menu choose `4) Change config`:
- Navigate parameter list; **Enter** to edit the value
- Footer buttons: `[ Back ] [ Save ] [ Reload ] [ Backups ]`
  - **Save**: writes `IMPACT.conf` and also writes a timestamped backup to `conf_backups/`
  - **Reload**: re-reads `IMPACT.conf` from disk
  - **Backups**: pick a previous backup or the current file; choosing a backup first safeguards the current file by backing it up, then restores

Shortcuts and movement:
- **Tab** switches focus (list/footer)
- **PgUp/PgDn** scroll
- **0** or **Esc** to exit editor quickly

---

## Keyboard Cheatsheet

Global patterns used across TUIs:
- **↑/↓/j/k**: move selection
- **←/→/h/l**: move across PDB tokens
- **Enter**: activate / toggle
- **Tab**: switch focus
- **0** or **Esc**: back/exit
- **B** in Setup menu: toggle SLURM **override** (force submission without SLURM_* config)
- In progress screens: **q/Esc** cancel, **v** toggle logs, **s** change log split

---

## Logs, Backups, and Output

- **Processed outputs**: `PDB_PROC_DIR/<PDB_NAME>/...`
- **Local run temp tails**: kept in system temp dir during execution (auto-cleaned per run)
- **SLURM logs**: `log/IMPACT_<NAME>.out` and `.err`
- **Config backups**: `conf_backups/IMPACT.conf.bak.YYYYMMDD-HHMMSS`

---

## SLURM Notes

- The SLURM flow is **one job per selection**; each job runs the same VMD-based setup pipeline.
- The UI uses `scontrol/sacct/squeue` to resolve job name and status; if these aren’t available, status may show as `UNKNOWN` until logs appear.
- If SLURM isn’t configured in `IMPACT.conf`, you can still submit by pressing **B** (forces `--force` flag).

For day-to-day cluster visibility you may find these handy:

```bash
# All jobs with full-width names, refreshed every 15s
watch -n 15 'squeue -u $USER -o "%10i %9P %20j %8u %2t %10M %5D %R"'

# Only running jobs
watch -n 15 'squeue -u $USER -o "%10i %9P %20j %8u %2t %10M %5D %R" | grep " R "'
```

---

## Troubleshooting

- **“Terminal too small” warning** on the main menu  
  Increase terminal size to ≥ **87×26** or press **B** twice to bypass (rendering may wrap).
- **“SLURM not configured”** when selecting SLURM  
  Fill out `SLURM_ACCOUNT`, `SLURM_PARTITION`, `SLURM_CMD` in `IMPACT.conf`, or press **B** to force.
- **No PDBs listed**  
  Check `PDB_DIR` path in the config and that it contains `*.pdb` files.
- **VMD not found**  
  Ensure `vmd` is on PATH or load via `module load vmd`.
- **Jobs submit but no logs**  
  Ensure `log/` is writable; filenames are `log/IMPACT_<NAME>.out|.err`.
- **Local run canceled**  
  The current selection stops; nothing else is affected.

---

## Not Yet Implemented

The main menu shows items that are placeholders for future flows:

- `2) Run NAMD` — end-to-end NAMD execution after setup (queued or local), including minimization/equilibration recipes
- `3) Run GaMD` — GaMD staging and production scheduling
- Fine-grained **resource selection** (wall-time/cores per job) from within the TUI
- Cross-node parallel local runs; currently local mode runs selections **serially** in a single session
- Rich **error parsing** / actionable hints directly from `.err` contents
- Windows support (currently UNIX-like shells expected)

---

## Roadmap Ideas

- Per-protocol runners (Minimization, NPTx, Production) with templated SLURM scripts
- Batch composer to stitch dependent arrays (e.g., `equil → npt1..npt6 → prod`) with `--dependency=afterok` chains
- Persistent run DB for resuming/skip-done logic
- Inline viewers for generated artifacts (contact maps, summaries)
- Themeable UI and resizable panes
- Unit tests for config parse/restore and SLURM helpers

---

## License

TBD. For now, internal research tooling.
