# BG3 PS5 Campaign Automation — Local Starter

This is a working **local processing pipeline**, not yet a fully unattended Larian download or a ChatGPT Project API integration. The PS5 campaign save is the source of truth. `player-notes.json` stores separate human annotations. The pipeline **never modifies a save**.

## 1. Prerequisites

- Python 3.10+ and Git.
- The [bg3-savefile-parser](https://github.com/DanFinchUK/bg3-savefile-parser) CLI.
- A PS5 save downloaded from [Larian My Saves](https://larian.com/account) after cross-save finishes.

Install the parser in a separate local directory (not inside this starter):

```powershell
# Run in a folder where you keep developer tools
 git clone https://github.com/DanFinchUK/bg3-savefile-parser.git
 cd bg3-savefile-parser
 # Install uv first if you don't already have it: https://docs.astral.sh/uv/
 uv sync
 uv run bg3save --help
```

Then ensure `bg3save` is on your PATH (for example via `pip install .` in a dedicated virtual environment), **or** run this starter with `--parser-command` pointing to the parser's `uv run` entry point. See example below.

## 2. First run

1. In PS5 BG3, enable cross-save. Make a new save using the hosting player's account and allow synchronization to finish.
2. On a PC, visit Larian account → **My Saves** and download the relevant `.lsv` save.
3. Copy it into this project's `incoming/` directory (keep the original download separately).
4. From this project's root, run:

```powershell
python scripts/run_pipeline.py --parser-command 'bg3save {save} --all --json'
```

If `bg3save` is not on PATH, from a PowerShell terminal:

```powershell
python scripts/run_pipeline.py --parser-command 'uv run --project C:\dev\bg3-savefile-parser bg3save {save} --all --json'
```

Replace `C:\dev\bg3-savefile-parser` with the actual checkout location. The parser's documented flags are `--all --json`. The first actual save will validate whether both flags work together in your installed revision.

Outputs:

- `output/campaign-state.json` — unmodified parser JSON (authoritative extraction, not a gameplay guarantee)
- `output/latest-meta.json` — save hash, source, timestamp
- `output/changes.json` — changes in recognized quest records
- `output/act3-guide.md` — **provisional** save-derived quest index, not a true spoiler-aware walkthrough yet

Re-running an unchanged file does nothing. Use `--force` to regenerate outputs after changing code or notes.

## 3. Windows scheduling (after first successful run)

On a Windows PC, use Task Scheduler → Create Task:

- Trigger: your desired days/times, **after play sessions and Larian synchronization**.
- Action / Program: `python` (prefer the absolute path to your Python executable).
- Arguments: `scripts\run_pipeline.py --parser-command "bg3save {save} --all --json"`
- Start in: full path of this starter project.
- Run only when the user is logged on at first; later configure unattended operation if appropriate.

**Important:** this job only processes `.lsv` files already present in `incoming/`. It will not fetch a new cloud save on its own. Browser automation is a separate, unimplemented acquisition adapter. Avoid scheduling a process that silently ingests an older save; validate source name and freshness when acquisition is automated.

## 4. Larian acquisition integration (next step)

Larian publicly documents manual downloads through account → My Saves, not a supported public save-download API. Candidate acquisition mechanisms:

1. Manually download the file to `incoming/` (initial reliable baseline).
2. Test ChatGPT Work computer/browser interaction with Larian on your PC in a logged-in session.
3. If Work cannot fully automate it, optionally implement locally controlled Playwright browser automation with an interactive authentication step, explicit download verification, and a dedicated persistent profile. Do not store passwords in source code.

Website sessions can expire, so plan for login-required notifications and a fail-closed acquisition step. New downloads must be verified as `.lsv` and never overwrite the only original.

## 5. Rebuilding a real Act 3 guide

The prototype guide lists best-effort quest records only. It does **not** infer full Act 3 progression, quest ordering, or completion status from undocumented internal flags. After inspecting a real parsed JSON example, replace `find_quests` with a schema-specific mapping, stable quest identifiers, confidence categories, and explicit quest dependencies.

Source-of-truth policy:

- Save-derived game state wins when game facts conflict with notes.
- Manual checkbox state is a UX annotation, *not* evidence of game completion.
- An absent quest record does not mean a quest is completed.
- Never leak future Act 3 quest spoilers from a generic walkthrough without a progression gate.

## 6. Connecting the results to ChatGPT

Start by uploading `campaign-state.json`, `changes.json`, and `act3-guide.md` to your BG3 project. An automatic replacement of project attachments is **not implemented**. Alternatively, use a local Work workflow pointed at this directory and have it read the updated files when regenerating a report. A Git repository can hold scripts but should not include raw saves or detailed state unless you intentionally choose secure/private storage.

## Security and limitations

Do not commit PSN/Larian credentials, session cookies, or raw saves. Keep cloud-sync and download access restricted to the hosting player's account. This pipeline has no game write-back. The included guide is a proof of concept and has not been validated against your real save.
