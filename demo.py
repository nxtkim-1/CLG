"""Synthetic local demo. Creates only a temporary synthetic repo and an output note."""
from pathlib import Path
import json
import subprocess
import tempfile
from clg.core import collect, mock_restart, write_note, stale_reason, Snapshot

def main():
    with tempfile.TemporaryDirectory(prefix='clg-synthetic-') as d:
        root=Path(d)
        def git(*args):return subprocess.run(['git','-C',d,*args],check=True,capture_output=True,text=True).stdout.strip()
        git('init');git('config','user.name','Synthetic Demo');git('config','user.email','synthetic@example.invalid')
        (root/'calc.py').write_text('def add(a,b): return a-b\n')
        git('add','calc.py');git('commit','-m','Synthetic demo only')
        p=collect(root,'FAIL test_add: expected 4, got 0\nAPI_KEY=synthetic_secret_canary')
        print('PRIVACY PREVIEW');print(json.dumps(p.__dict__,default=lambda o:o.__dict__,indent=2))
        n=mock_restart(p,p.digest);out=root/'freeze.json';write_note(n,p,out)
        print('OFFLINE MOCK NOTE');print(out.read_text())
        print('STALE-STATE EXAMPLE:',stale_reason(p,Snapshot('other-branch',p.snapshot.commit,(),'')))
        print('No network call, API key, billing or source backup. Synthetic workspace removed on exit.')
if __name__=='__main__':main()
