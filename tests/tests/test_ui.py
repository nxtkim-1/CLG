import http.client
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
from clg.ui import make_server

class UITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.repo=Path(self.temp.name)
        def g(*a):return subprocess.run(['git','-C',str(self.repo),*a],check=True,capture_output=True)
        g('init');g('config','user.name','Synthetic');g('config','user.email','fixture@example.invalid')
        (self.repo/'a.py').write_text('original');g('add','.');g('commit','-m','fixture')
        self.server=make_server(self.repo);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        self.conn.request('GET','/');r=self.conn.getresponse();page=r.read().decode();self.assertEqual(r.status,200)
        self.token=re.search("const token='([^']+)'",page).group(1)
    def tearDown(self):
        self.conn.close();self.server.shutdown();self.server.server_close();self.temp.cleanup()
    def post(self,path,data,token=None,extra=None):
        headers={'Content-Type':'application/json','X-Context-Freeze':self.token if token is None else token};headers.update(extra or {})
        self.conn.request('POST',path,json.dumps(data),headers);r=self.conn.getresponse();return r.status,json.loads(r.read())
    def test_preview_gate_and_resume(self):
        code,p=self.post('/preview',{'selection':'API_KEY=canaryValue FAIL test_resume'});self.assertEqual(code,200)
        self.assertNotIn('canaryValue',json.dumps(p));self.assertEqual(self.post('/freeze',{'digest':'wrong'})[0],400)
        code,n=self.post('/freeze',{'digest':p['digest']});self.assertEqual(code,200);self.assertIn('OFFLINE MOCK',n['restart']['mode'])
        self.assertIsNone(self.post('/resume',{'digest':p['digest']})[1]['warning'])
        (self.repo/'a.py').write_text('changed');self.assertIn('Tracked changes',self.post('/resume',{'digest':p['digest']})[1]['warning'])
    def test_cross_origin_and_token_rejected(self):
        self.assertEqual(self.post('/preview',{},token='wrong')[0],403)
        self.assertEqual(self.post('/preview',{},extra={'Origin':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.post('/preview',{},extra={'Host':'attacker.invalid'})[0],403)
    def test_invalid_input(self):
        self.assertEqual(self.post('/preview',{'selection':'x'*12001})[0],400)
        self.assertEqual(self.post('/preview',{'selection':1})[0],400)
        self.assertEqual(self.post('/freeze',{'digest':'x'})[0],400)
    def test_new_preview_invalidates_old(self):
        _,p=self.post('/preview',{'selection':'one'});self.post('/preview',{'selection':'two'})
        self.assertEqual(self.post('/freeze',{'digest':p['digest']})[0],400)
if __name__=='__main__':unittest.main()
