import copy
import json
from dataclasses import replace
from unittest.mock import patch
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from clg.core import Snapshot, preview, collect, mock_restart, meta_restart, restart_note, validate_restart, stale_reason, write_note

class CoreTests(unittest.TestCase):
    def snap(self, text='', files=()): return Snapshot('main', 'a'*40, files, text)
    def test_clean_preview(self):
        p=preview(self.snap());self.assertEqual(p.snapshot.branch,'main');self.assertEqual(p.redactions,0)
    def test_secret_canary(self):
        p=preview(self.snap('API_KEY=canary123 password:bad token=secret sk-abcdefghijk ghp_abcdefghijklmnop'))
        for secret in ['canary123','bad','secret','sk-abcdefghijk','ghp_abcdefghijklmnop']: self.assertNotIn(secret,p.snapshot.selected_text)
    def test_paths(self):
        p=preview(self.snap('at /home/thomas/private/main.py and /Users/Thomas/code/a.py'))
        self.assertNotIn('thomas',p.snapshot.selected_text);self.assertNotIn('Thomas',p.snapshot.selected_text)
    def test_sensitive_files(self):
        p=preview(self.snap(files=('.env','../oops','/home/x','keys.pem','src/main.py')))
        self.assertEqual(p.snapshot.changed_files,('src/main.py',))
    def test_input_bound(self):
        with self.assertRaises(ValueError):preview(self.snap('x'*12001))
    def test_digest_changes(self):self.assertNotEqual(preview(self.snap('one')).digest,preview(self.snap('two')).digest)
    def test_approval_gate(self):
        with self.assertRaises(ValueError):mock_restart(preview(self.snap()),'wrong')
    def test_mock_honesty(self):
        p=preview(self.snap('FAIL test_one'));n=mock_restart(p,p.digest);validate_restart(n,p)
        self.assertIn('OFFLINE MOCK',n['mode']);self.assertIn('Unknown',n['blocker'])
    def test_invented_evidence(self):
        p=preview(self.snap());n=mock_restart(p,p.digest);n['evidence'][0]['text']='made up'
        with self.assertRaises(ValueError):validate_restart(n,p)
    def test_invalid_refs(self):
        p=preview(self.snap());n=mock_restart(p,p.digest);n['next_steps'][0]['evidence_ids']=['invented']
        with self.assertRaises(ValueError):validate_restart(n,p)
    def test_malformed_notes_rejected(self):
        p=preview(self.snap());base=mock_restart(p,p.digest)
        invalid=[None, [], 'text']
        for field,value in [('evidence',[None]),('evidence',[{'id': [], 'text': 'x'}]),
                            ('next_steps',[None]),('next_steps',[{'text':12,'evidence_ids':['git']}]),
                            ('next_steps',[{'text':'x','evidence_ids':'git'}]),
                            ('next_steps',[{'text':'x','evidence_ids':[{}]}]),
                            ('unknowns',None),('unknowns',[4])]:
            n=copy.deepcopy(base);n[field]=value;invalid.append(n)
        for note in invalid:
            with self.subTest(note=note),self.assertRaises(ValueError):validate_restart(note,p)
    def test_redaction_edge_cases(self):
        examples = ['Authorization: Bearer unique_auth_canary', 'Authorization: Basic unique_basic_canary',
                    'OPENAI_API_KEY=unique_key_canary', 'DB_PASSWORD=unique_password_canary',
                    '\"password\": \"unique quoted canary\"',
                    '-----BEGIN PRIVATE KEY-----\nunique_pem_canary\n-----END PRIVATE KEY-----']
        for text in examples:
            with self.subTest(text=text):
                p=preview(self.snap(text));self.assertNotIn('canary',p.snapshot.selected_text)
    def test_branch_redaction(self):
        p=preview(Snapshot('feature/token=unique_canary','a'*40,(),''))
        self.assertNotIn('unique_canary',p.snapshot.branch)
    def test_omitted_dirty_state_warns(self):
        p=preview(self.snap(files=('.env',)))
        self.assertEqual(p.snapshot.changed_files,());self.assertEqual(p.snapshot.omitted_files,1)
        self.assertIsNotNone(stale_reason(p,p.snapshot))
    def test_forged_preview_rejected(self):
        p=replace(preview(self.snap()),digest='0'*64)
        with self.assertRaises(ValueError):mock_restart(p,p.digest)
    def test_extra_note_fields_rejected(self):
        p=preview(self.snap());n=mock_restart(p,p.digest);n['unexpected']='value'
        with self.assertRaises(ValueError):validate_restart(n,p)
    def test_secret_output_field_rejected(self):
        p=preview(self.snap());n=mock_restart(p,p.digest);n['task']='password=unique_canary'
        with self.assertRaises(ValueError):validate_restart(n,p)
    def test_stale_commit(self):
        self.assertIsNotNone(stale_reason(preview(self.snap()),Snapshot('main','b'*40,(),'')))
    def test_dirty_always_warns(self):
        p=preview(self.snap(files=('a.py',)));self.assertIsNotNone(stale_reason(p,p.snapshot))
    def test_clean_same(self):
        p=preview(self.snap());self.assertIsNone(stale_reason(p,p.snapshot))
    def test_exclusive_output(self):
        p=preview(self.snap());n=mock_restart(p,p.digest)
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'freeze.json';write_note(n,p,f)
            with self.assertRaises(FileExistsError):write_note(n,p,f)
    def test_real_repo_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)
            def g(*args):return subprocess.run(['git','-C',d,*args],check=True,capture_output=True,text=True).stdout.strip()
            g('init');g('config','user.name','Synthetic Test');g('config','user.email','synthetic@example.invalid')
            (r/'a.py').write_text('before');g('add','a.py');g('commit','-m','Synthetic fixture')
            head=g('rev-parse','HEAD');(r/'a.py').write_text('after')
            with patch.dict(os.environ, {'GIT_DIR':'/nonexistent/synthetic-invalid-git-dir'}):
                p=collect(r,'test failure selected by user')
            self.assertEqual(p.snapshot.commit,head);self.assertEqual(p.snapshot.changed_files,('a.py',))
            self.assertEqual((r/'a.py').read_text(),'after');self.assertEqual(g('rev-parse','HEAD'),head)

if __name__=='__main__':unittest.main()


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps(self.payload).encode()

class MetaSeamTests(unittest.TestCase):
    def snap(self, text='', files=()): return Snapshot('main', 'a'*40, files, text)
    def note_payload(self, p, **over):
        note = {'task': 'Resume the failing test', 'blocker': 'test_resume fails',
                'evidence': [{'id': 'git', 'text': f'Branch {p.snapshot.branch}; commit {p.snapshot.commit}'}],
                'next_steps': [{'text': 'Run the failing test', 'evidence_ids': ['git']}],
                'unknowns': ['Unverified']}
        note.update(over)
        return {'output_text': json.dumps(note)}

    def test_meta_requires_key(self):
        p = preview(self.snap())
        os.environ.pop('MODEL_API_KEY', None)
        with self.assertRaises(RuntimeError) as ctx:
            meta_restart(p, p.digest)
        self.assertIn('MODEL_API_KEY', str(ctx.exception))

    def test_meta_valid_note(self):
        p = preview(self.snap())
        seen = {}
        def opener(req, timeout):
            seen['url'] = req.full_url; seen['auth'] = req.headers.get('Authorization')
            return FakeResponse(self.note_payload(p))
        note = meta_restart(p, p.digest, api_key='syntheticCanary', opener=opener)
        self.assertEqual(note['snapshot_digest'], p.digest)
        self.assertEqual(note['mode'], 'Meta muse-spark-1.3')
        self.assertEqual(seen['url'], 'https://api.meta.ai/v1/responses')
        self.assertEqual(seen['auth'], 'Bearer syntheticCanary')

    def test_meta_rejects_invented_evidence(self):
        p = preview(self.snap())
        def opener(req, timeout):
            return FakeResponse(self.note_payload(p, evidence=[{'id': 'git', 'text': 'invented'}]))
        with self.assertRaises(ValueError):
            meta_restart(p, p.digest, api_key='k', opener=opener)

    def test_meta_rejects_non_json(self):
        p = preview(self.snap())
        def opener(req, timeout): return FakeResponse({'output_text': 'not json'})
        with self.assertRaises(RuntimeError):
            meta_restart(p, p.digest, api_key='k', opener=opener)

    def test_meta_output_items_shape(self):
        p = preview(self.snap())
        shaped = {'output': [{'content': [{'text': json.dumps(self.note_payload(p) and json.loads(self.note_payload(p)['output_text']))}]}]}
        def opener(req, timeout): return FakeResponse(shaped)
        note = meta_restart(p, p.digest, api_key='k', opener=opener)
        self.assertEqual(note['task'], 'Resume the failing test')

    def test_dispatcher_defaults_to_mock(self):
        p = preview(self.snap())
        self.assertEqual(restart_note(p, p.digest)['mode'], 'OFFLINE MOCK - no Meta inference')
        with self.assertRaises(ValueError):
            restart_note(p, p.digest, provider='nope')
