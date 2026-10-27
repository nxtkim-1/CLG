import json
from dataclasses import asdict
from pathlib import Path
import argparse
from .core import collect, mock_restart, write_note

def main():
    a = argparse.ArgumentParser(description='Local Context Freeze prototype; no network, no API keys.')
    a.add_argument('--repo', type=Path, required=True)
    a.add_argument('--selection', type=Path, help='Explicit text file to preview; never global history')
    a.add_argument('--approve', help='Exact digest shown by preview')
    a.add_argument('--out', type=Path)
    args = a.parse_args()
    p = collect(args.repo, args.selection.read_text() if args.selection else '')
    print(json.dumps(asdict(p), indent=2))
    if args.approve:
        if not args.out:
            a.error('--out required with --approve')
        note = mock_restart(p, args.approve)
        write_note(note, p, args.out)
        print('Saved OFFLINE MOCK. No inference, source backup, or command execution.')
if __name__ == '__main__': main()
