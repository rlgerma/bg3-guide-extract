#!/usr/bin/env python3
"""Local, read-only BG3 save pipeline. No Larian credentials are stored here."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / 'incoming'
OUTPUT = ROOT / 'output'

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for buf in iter(lambda: f.read(1024 * 1024), b''):
            h.update(buf)
    return h.hexdigest()

def atomic_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')
        temp = Path(f.name)
    os.replace(temp, path)

def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        f.write(value)
        temp = Path(f.name)
    os.replace(temp, path)

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return default

def find_quests(data):
    """Best-effort: capture quest-like records, with no inferred game completion."""
    results = []
    seen = set()
    def walk(node, path='', depth=0):
        if depth > 18 or len(results) >= 500:
            return
        if isinstance(node, dict):
            leaf = path.split('.')[-1].lower()
            if 'quest' in leaf or 'journal' in leaf:
                if isinstance(node, dict) and any(k.lower() in ('title','name','quest_name','display_name') for k in node):
                    add(node, path)
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    walk(v, f'{path}.{k}' if path else str(k), depth + 1)
        elif isinstance(node, list):
            leaf = path.split('.')[-1].lower()
            if 'quest' in leaf or 'journal' in leaf:
                for item in node:
                    if isinstance(item, dict):
                        add(item, path)
            for idx, value in enumerate(node[:2000]):
                if isinstance(value, (dict, list)):
                    walk(value, f'{path}[{idx}]', depth + 1)
    def add(node, path):
        title = next((str(node[k]) for k in ('title','name','quest_name','display_name') if k in node and isinstance(node[k], (str, int))), None)
        if not title or title in seen:
            return
        seen.add(title)
        status = next((str(node[k]) for k in ('status','state','completed','is_completed','closed') if k in node), 'unknown')
        results.append({'title': title, 'raw_status': status, 'source_path': path})
    walk(data)
    return results

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--save', type=Path, help='Specific .lsv save; otherwise latest by file modification time in incoming/')
    p.add_argument('--parser-command', default='bg3save {save} --all --json', help='Command argv template, with {save} placeholder. No shell used.')
    p.add_argument('--force', action='store_true')
    args = p.parse_args()
    INCOMING.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)
    if args.save:
        save = args.save.resolve()
    else:
        candidates = list(INCOMING.glob('*.lsv'))
        if not candidates:
            print('No .lsv files found. Download from Larian My Saves and place one in incoming/.', file=sys.stderr)
            return 2
        save = max(candidates, key=lambda f: (f.stat().st_mtime_ns, f.name))
    if not save.is_file() or save.suffix.lower() != '.lsv':
        print(f'Not a readable .lsv save: {save}', file=sys.stderr)
        return 2
    fingerprint = digest(save)
    previous_meta = load_json(OUTPUT / 'latest-meta.json', {})
    if previous_meta.get('sha256') == fingerprint and not args.force:
        print(f'UNCHANGED: {save.name}. No files regenerated.')
        return 0
    if '{save}' not in args.parser_command:
        print('Parser command must include {save}', file=sys.stderr)
        return 2
    argv = [part.replace('{save}', str(save)) for part in shlex.split(args.parser_command, posix=(os.name != 'nt'))]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=240)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'Parser unavailable or timed out: {exc}', file=sys.stderr)
        return 3
    if proc.returncode:
        print(f'Parser returned {proc.returncode}: {proc.stderr[-2000:]}', file=sys.stderr)
        return 3
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f'Parser did not return valid JSON: {exc}; stderr: {proc.stderr[-1000:]}', file=sys.stderr)
        return 3
    previous = load_json(OUTPUT / 'campaign-state.json', None)
    quests = find_quests(parsed)
    notes = load_json(ROOT / 'player-notes.json', {'completed_task_ids': [], 'notes': []})
    if not isinstance(notes, dict):
        print('player-notes.json must contain an object', file=sys.stderr)
        return 3
    old_quests = {q['title']: q['raw_status'] for q in find_quests(previous)} if previous is not None else {}
    new_quests = {q['title']: q['raw_status'] for q in quests}
    change = {'added_quest_titles': sorted(set(new_quests) - set(old_quests)),
              'removed_quest_titles': sorted(set(old_quests) - set(new_quests)),
              'changed_quest_statuses': [{'title': k, 'before': old_quests[k], 'after': new_quests[k]}
                  for k in sorted(set(old_quests) & set(new_quests)) if old_quests[k] != new_quests[k]],
              'full_save_changed': previous is not None and parsed != previous}
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata = {'source_filename': save.name, 'sha256': fingerprint, 'processed_at_utc': timestamp,
                'parser_command': args.parser_command, 'quest_records_detected': len(quests)}
    lines = ['# Act 3 campaign guide — save-derived index', '',
             '> This is an automatically generated **quest index**, not a comprehensive Act 3 walkthrough. '
             'Its quest scope and status fields depend on parser coverage. '
             'It does not claim that a quest is complete without verified interpretation.', '',
             f'- Save: `{save.name}`', f'- Processed (UTC): {timestamp}',
             f'- SHA-256: `{fingerprint}`', '',
             '## Extracted quest and journal records', '']
    if quests:
        for q in sorted(quests, key=lambda x:x['title'].casefold()):
            lines += [f"- [ ] {q['title']} — raw status: `{q['raw_status']}`"]
    else:
        lines += ['No quest records recognized by this generic extractor. The full parsed state is still available in `campaign-state.json`. The extraction mapping should be calibrated against your save.']
    lines += ['', '## Player-confirmed notes (not inferred from save)', '']
    for note in notes.get('notes', []):
        lines.append(f'- {note}')
    if not notes.get('notes'):
        lines.append('_No notes yet._')
    lines += ['', '## Changes since previous processed save', '',
              f"- New quest records: {len(change['added_quest_titles'])}",
              f"- Missing quest records: {len(change['removed_quest_titles'])}",
              f"- Changed raw quest statuses: {len(change['changed_quest_statuses'])}",
              '', '## Important', '',
              'Checklist boxes here are **rendered unchecked by default**; they are not persisted. '
              'Keep player acknowledgements in `player-notes.json` and treat the save as authoritative for the current game state. '
              'A future reconciler should use stable quest IDs rather than titles once the parser schema is validated.', '']
    # Publish after successful parse and rendering. Avoid changing outputs on parser failure.
    atomic_json(OUTPUT / 'campaign-state.json', parsed)
    atomic_json(OUTPUT / 'latest-meta.json', metadata)
    atomic_json(OUTPUT / 'changes.json', change)
    atomic_text(OUTPUT / 'act3-guide.md', '\n'.join(lines))
    print(f'UPDATED: {save.name}; {len(quests)} quest records; output/act3-guide.md')
    return 0

if __name__ == '__main__':
    sys.exit(main())
