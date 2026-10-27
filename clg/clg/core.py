"""Selected-evidence workflow. Local-only by default: the offline mock makes no network calls.
The optional meta provider calls the documented Meta Model API only when explicitly selected
with MODEL_API_KEY set; it never runs by default. No shell execution."""
from dataclasses import dataclass, asdict
import hashlib
import hmac
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

@dataclass(frozen=True)
class Snapshot:
    branch: str
    commit: str
    changed_files: tuple[str, ...]
    selected_text: str
    omitted_files: int = 0

@dataclass(frozen=True)
class Preview:
    snapshot: Snapshot
    digest: str
    redactions: int
    warnings: tuple[str, ...]

SECRET = re.compile(r'''(?ix)[\w.-]{0,40}(?:api[_-]?key|passw(?:or)?d|secret|token|private[_-]?key)[\w.-]{0,40}["']?\s*[:=]\s*(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)''')
AUTH = re.compile(r'''(?im)\bauthorization\b["']?\s*[:=].*$''')
PEM = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)', re.S)
BEARER = re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+')
KNOWN_KEY = re.compile(r'\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{12,}|AKIA[A-Z0-9]{16})\b')

def redact(text):
    count = 0
    for pattern in (PEM, AUTH, BEARER, KNOWN_KEY, SECRET):
        text, n = pattern.subn('[REDACTED]', text); count += n
    text, n = re.subn(r'(?i)(?:/Users/|/home/|[A-Z]:\\Users\\)[^\s:]+', '[LOCAL_PATH]', text)
    return text, count + n

def digest(snapshot):
    return hashlib.sha256(json.dumps(asdict(snapshot), sort_keys=True).encode()).hexdigest()

def check_preview(p):
    if not hmac.compare_digest(p.digest, digest(p.snapshot)):
        raise ValueError('Preview digest does not match contents')

def preview(snapshot: Snapshot) -> Preview:
    if len(snapshot.selected_text) > 12000:
        raise ValueError('Select at most 12000 characters, not unrestricted history.')
    files = []
    omitted = 0
    for name in snapshot.changed_files:
        parts = Path(name).parts
        if Path(name).is_absolute() or '..' in parts or any(p.startswith('.') for p in parts) or re.search(r'(?i)(credential|secret|token|password|\.pem$|\.key$)', name):
            omitted += 1
        else:
            files.append(name)
    text, redactions = redact(snapshot.selected_text)
    branch, n = redact(snapshot.branch); redactions += n
    clean = Snapshot(branch, snapshot.commit, tuple(files), text, snapshot.omitted_files + omitted)
    preview_digest = digest(clean)
    warnings = ['Heuristic redaction is not a secret guarantee. Review every visible field.',
                'A summary does not save unstaged source changes. No Git write is performed.']
    if omitted:
        warnings.append(f'{omitted} sensitive or unsafe filenames omitted.')
    return Preview(clean, preview_digest, redactions, tuple(warnings))

def collect(repo: Path, selected_text: str) -> Preview:
    root = repo.resolve(strict=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    def git(*args):
        r = subprocess.run(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', str(root), *args], capture_output=True, text=True, errors='replace', env=env, stdin=subprocess.DEVNULL, check=True, timeout=5)
        return r.stdout
    # Tracked changes only, no file contents or global terminal history.
    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD') if git('rev-parse', '--abbrev-ref', 'HEAD').strip() != 'HEAD' else '(detached)'
    branch = branch.strip()
    commit = git('rev-parse', 'HEAD').strip()
    files = git('diff', '--no-ext-diff', '--no-textconv', '--name-only', '-z', 'HEAD', '--').split('\0')
    files = [name for name in files if name]
    return preview(Snapshot(branch, commit, tuple(files), selected_text))

def mock_restart(p: Preview, approved_digest: str) -> dict:
    check_preview(p)
    if approved_digest != p.digest:
        raise ValueError('Preview approval does not match these exact inputs.')
    evidence = [{'id': 'git', 'text': f'Branch {p.snapshot.branch}; commit {p.snapshot.commit}'}]
    if p.snapshot.selected_text:
        evidence.append({'id': 'selection', 'text': p.snapshot.selected_text})
    return {'mode': 'OFFLINE MOCK - no Meta inference', 'snapshot_digest': p.digest,
            'task': 'Unknown: user task not supplied',
            'blocker': 'Unknown: no inferred blocker in offline mode',
            'evidence': evidence,
            'next_steps': [{'text': 'Review the selected evidence and confirm your task.', 'evidence_ids': ['git']},
                           {'text': 'Choose the next action yourself; no command runs automatically.', 'evidence_ids': ['git']}],
            'unknowns': ['No model call made.', 'Source changes are not backed up by this note.']}


META_BASE_URL = 'https://api.meta.ai/v1'
META_DEFAULT_MODEL = 'muse-spark-1.3'

def meta_prompt(p: Preview) -> str:
    check_preview(p)
    evidence = json.dumps([{'id': 'git', 'text': f'Branch {p.snapshot.branch}; commit {p.snapshot.commit}'}] +
                          ([{'id': 'selection', 'text': p.snapshot.selected_text}] if p.snapshot.selected_text else []))
    return ('You are Context Freeze. From ONLY the evidence JSON below, infer the user task, '
            'the blocker, one to three bounded next steps, and up to five unknowns. '
            'Return ONLY a JSON object with keys: task, blocker, evidence, next_steps, unknowns. '
            'Copy the evidence array exactly as given; never invent or alter evidence. '
            'Each next_steps item is {"text": ..., "evidence_ids": [...]} referencing evidence IDs. '
            'No commands, no Markdown, no secrets. Evidence JSON:\n' + evidence)

def meta_restart(p: Preview, approved_digest: str, *, api_key: str | None = None,
                 model: str = META_DEFAULT_MODEL, base_url: str = META_BASE_URL, opener=None) -> dict:
    check_preview(p)
    if approved_digest != p.digest:
        raise ValueError('Preview approval does not match these exact inputs.')
    key = api_key or os.environ.get('MODEL_API_KEY')
    if not key:
        raise RuntimeError('MODEL_API_KEY is not set; offline mock remains the default.')
    body = json.dumps({'model': model, 'input': meta_prompt(p)}).encode('utf-8')
    request = urllib.request.Request(base_url + '/responses', data=body, method='POST',
                                     headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as err:
        detail = err.read()[:200].decode('utf-8', 'replace')
        raise RuntimeError(f'Meta API error {err.code}: {redact(detail)[0]}') from None
    text = payload.get('output_text')
    if not isinstance(text, str):
        text = ''.join(part.get('text', '') for item in payload.get('output', []) if isinstance(item, dict)
                       for part in item.get('content', []) if isinstance(part, dict))
    try:
        note = json.loads(text)
    except ValueError:
        raise RuntimeError('Meta response was not valid JSON.') from None
    if not isinstance(note, dict):
        raise RuntimeError('Meta response was not a note object.')
    # The host binds the note to this approved preview; the model cannot supply these.
    note['snapshot_digest'] = p.digest
    note['mode'] = f'Meta {model}'
    validate_restart(note, p)
    return note

def restart_note(p: Preview, approved_digest: str, provider: str = 'mock', **kwargs) -> dict:
    if provider == 'mock':
        return mock_restart(p, approved_digest)
    if provider == 'meta':
        return meta_restart(p, approved_digest, **kwargs)
    raise ValueError('Unknown provider')

def validate_restart(note: dict, p: Preview) -> None:
    check_preview(p)
    if not isinstance(note, dict) or set(note) != {'mode','snapshot_digest','task','blocker','evidence','next_steps','unknowns'}:
        raise ValueError('Restart note must be an object')
    if note.get('snapshot_digest') != p.digest:
        raise ValueError('Wrong snapshot digest')
    expected = {'git': f'Branch {p.snapshot.branch}; commit {p.snapshot.commit}'}
    if p.snapshot.selected_text:
        expected['selection'] = p.snapshot.selected_text
    actual = note.get('evidence')
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValueError('Evidence inventory mismatch')
    if any(not isinstance(e, dict) or set(e) != {'id','text'} or not isinstance(e.get('id'), str) or not isinstance(e.get('text'), str) for e in actual):
        raise ValueError('Evidence entries must have text IDs and content')
    if {e.get('id'): e.get('text') for e in actual} != expected:
        raise ValueError('Evidence has been changed or invented')
    for field in ('task', 'blocker', 'mode'):
        if not isinstance(note.get(field), str) or not note[field].strip() or len(note[field]) > 300 or redact(note[field])[1]:
            raise ValueError('Missing required text field')
    steps = note.get('next_steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
        raise ValueError('Require one to three bounded steps')
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'text','evidence_ids'} or not isinstance(step.get('text'), str) or not step['text'].strip() or len(step['text']) > 300 or redact(step['text'])[1]:
            raise ValueError('Step must contain nonempty text')
        refs = step.get('evidence_ids')
        if not isinstance(refs, list) or not refs or any(not isinstance(e, str) or e not in expected for e in refs):
            raise ValueError('Step missing valid evidence')
    unknowns = note.get('unknowns')
    if not isinstance(unknowns, list) or not 1 <= len(unknowns) <= 5 or any(not isinstance(u, str) or not u.strip() or len(u) > 200 or redact(u)[1] for u in unknowns):
        raise ValueError('Unknowns must be a nonempty list of text')

def stale_reason(p: Preview, current: Snapshot) -> str | None:
    if (p.snapshot.branch, p.snapshot.commit) != (current.branch, current.commit):
        return 'Branch or commit changed. Review before resuming.'
    # Dirty-state contents are deliberately not read; names alone cannot prove equality.
    if p.snapshot.changed_files or current.changed_files or p.snapshot.omitted_files or current.omitted_files:
        return 'Tracked changes exist. File contents may have changed; review the diff yourself.'
    return None

def write_note(note: dict, p: Preview, destination: Path) -> None:
    validate_restart(note, p)
    serialized = json.dumps({'preview': asdict(p), 'restart': note}, indent=2)
    # Exclusive create prevents silent overwrite; no source contents are saved.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(serialized)
