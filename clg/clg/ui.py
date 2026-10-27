"""Loopback-only review UI; explicit repo, no remote calls or automatic commands."""
import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
from .core import collect, mock_restart, validate_restart, stale_reason

def make_server(repo: Path, port=0):
    repo = repo.resolve(strict=True)
    token = secrets.token_urlsafe(32)
    page = Path(__file__).with_name('ui.html').read_text(encoding='utf-8').replace('__TOKEN__', token).encode()
    state = {'preview': None}
    class Handler(BaseHTTPRequestHandler):
        timeout = 10
        def log_message(self, *args): pass  # selected evidence never enters request logs
        def reply(self, status, value, mime='application/json'):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(body)
        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            if not self.valid_host(): return self.reply(403, {'error':'Invalid host'})
            if self.path != '/': return self.reply(404, {'error':'Not found'})
            self.reply(200, page, 'text/html; charset=utf-8')
        def do_POST(self):
            origin=self.headers.get('Origin')
            expected=f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or (origin and origin != expected) or not secrets.compare_digest(self.headers.get('X-Context-Freeze',''), token):
                return self.reply(403, {'error':'Local request verification failed'})
            if self.headers.get('Content-Type') != 'application/json': return self.reply(415, {'error':'JSON required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 60000: raise ValueError('Request too large or empty')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError('JSON object required')
                if self.path == '/preview':
                    text=data.get('selection','')
                    if not isinstance(text,str):raise ValueError('Selection must be text')
                    p=collect(repo,text);state['preview']=p
                    return self.reply(200,asdict(p))
                p=state['preview']
                if p is None or data.get('digest') != p.digest: raise ValueError('Create and approve the current exact preview first')
                if self.path == '/freeze':
                    n=mock_restart(p,data['digest']);validate_restart(n,p)
                    return self.reply(200,{'preview':asdict(p),'restart':n})
                if self.path == '/resume':
                    now=collect(repo,'')
                    return self.reply(200,{'warning':stale_reason(p,now.snapshot)})
                self.reply(404,{'error':'Not found'})
            except (ValueError, TypeError, OSError) as e:self.reply(400,{'error':str(e)})
            except Exception:self.reply(400,{'error':'Repository check failed; verify the selected Git repository'})
    return HTTPServer(('127.0.0.1',port),Handler)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=make_server(args.repo,args.port)
    print(f'Local offline mock: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
