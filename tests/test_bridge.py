import http.client
import io
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
import bridge as B
from bridge_security import validate_range, pairing_key, MAX_UPLOAD

ROOT = pathlib.Path(__file__).resolve().parents[1]

def archive(extra=None):
    job = json.loads((ROOT/'jobs/daybreak_mini_cocoa_job.json').read_text())
    files = {'mini_job.json': json.dumps(job), job['texture']: (ROOT/'jobs'/job['texture']).read_bytes(),
             'range.json': json.dumps({'format':'daybreak-range/1', 'jobs':[{'job':'mini_job.json','texture':job['texture']} ]})}
    files.update(extra or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, value in files.items(): z.writestr(name, value)
    return out.getvalue()

class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        B.STATE.update(token='a'*64, blender='/detected/blender', cfg={'open':False,'hdri':''}, history=[], led={})
        cls.server = B.ThreadingHTTPServer(('127.0.0.1', 0), B.Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.worker.join()
    def request(self, path='/status', method='GET', body=None, **headers):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        c.request(method,path,body,headers); r=c.getresponse(); data=r.read(); result=(r.status,dict(r.getheaders()),json.loads(data) if data else {});c.close();return result
    def test_discovery_exposes_no_paths(self):
        status, _, data=self.request(); self.assertEqual(status,200);self.assertEqual(set(data),{'bridge','version','pairing_required'})
    def test_remote_origin_denied_even_with_key(self):
        status,headers,_=self.request(Origin='https://example.com', **{'X-Daybreak-Token':'a'*64});self.assertEqual(status,403);self.assertNotIn('Access-Control-Allow-Origin',headers)
    def test_rebinding_host_denied(self):
        self.assertEqual(self.request(Host='evil.example')[0],403)
    def test_null_origin_is_not_authentication(self):
        self.assertEqual(self.request('/select','POST','{}',Origin='null')[0],401)
        self.assertEqual(self.request('/history',Origin='null')[0],401)
    def test_preflight(self):
        code,headers,_=self.request(method='OPTIONS',Origin='null');self.assertEqual(code,204);self.assertEqual(headers['Access-Control-Allow-Origin'],'null')
    def test_paired_status(self):
        with patch.object(B.W,'list_blenders',return_value=[]), patch.object(B.W,'blender_version',return_value=(5,1,0)):
            self.assertEqual(self.request(**{'X-Daybreak-Token':'a'*64})[2]['blender'],'/detected/blender')
    def test_arbitrary_executable_rejected_before_probe(self):
        with patch.object(B.W,'list_blenders',return_value=[]),patch.object(B.W,'blender_version') as probe:
            self.assertEqual(self.request('/select','POST',json.dumps({'path':'/bin/sh'}),**{'X-Daybreak-Token':'a'*64})[0],400);probe.assert_not_called()
    def test_detected_blender_accepted(self):
        with patch.object(B.W,'list_blenders',return_value=[{'path':'/detected/blender','version':'5.1.0'}]),patch.object(B.os.path,'isfile',return_value=True),patch.object(B.W,'write_config'),patch.object(B.W,'blender_version',return_value=(5,1,0)):
            self.assertEqual(self.request('/select','POST',json.dumps({'path':'/detected/blender'}),**{'X-Daybreak-Token':'a'*64})[0],200)
    def test_upload_limits_before_read(self):
        for length,code in [(str(MAX_UPLOAD+1),413),('-1',413),('bad',400)]:
            self.assertEqual(self.request('/deploy','POST',b'',**{'X-Daybreak-Token':'a'*64,'Content-Length':length})[0],code)
    def test_invalid_zip(self):
        self.assertEqual(self.request('/deploy','POST',b'PKbroken',**{'X-Daybreak-Token':'a'*64})[0],400)
    def test_valid_deploy(self):
        with tempfile.TemporaryDirectory() as d,patch.object(B.W,'JOBS',d),patch.object(B.W,'process_range',return_value={'ok':True,'boxes':1}):
            self.assertEqual(self.request('/deploy','POST',archive(),**{'X-Daybreak-Token':'a'*64})[0],200)
            self.assertEqual(len(list(pathlib.Path(d).glob('*.zip'))),1)
    def test_archive_contract(self):
        with zipfile.ZipFile(io.BytesIO(archive())) as z: self.assertEqual(len(validate_range(z)['jobs']),1)
        for extras in [{'../escape.json':'{}'}, {'evil.py':'print(1)'}, {'range.json':'{}'}, {'mini_job.json':'[]'}]:
            with self.subTest(extras=extras),zipfile.ZipFile(io.BytesIO(archive(extras))) as z,self.assertRaises(ValueError):validate_range(z)
    def test_truncated_png(self):
        with zipfile.ZipFile(io.BytesIO(archive({'daybreak_mini_cocoa_4096.png':b'\x89PNG\r\n\x1a\nBAD'}))) as z,self.assertRaises(ValueError):validate_range(z)
    def test_duplicate_and_symlink_entries(self):
        for link in (False, True):
            out = io.BytesIO(archive())
            with zipfile.ZipFile(out, 'a') as z:
                info = zipfile.ZipInfo('link.png' if link else 'range.json')
                if link: info.external_attr = 0o120777 << 16
                z.writestr(info, 'outside')
            with zipfile.ZipFile(out) as z, self.assertRaises(ValueError):
                validate_range(z)
    def test_expansion_limit(self):
        with zipfile.ZipFile(io.BytesIO(archive())) as z, patch('bridge_security.MAX_EXPANDED', 16), self.assertRaises(ValueError):
            validate_range(z)
    def test_manifest_cannot_reference_external_texture(self):
        job = json.loads((ROOT/'jobs/daybreak_mini_cocoa_job.json').read_text())
        job['texture'] = '/outside.png'
        with zipfile.ZipFile(io.BytesIO(archive({'mini_job.json':json.dumps(job)}))) as z, self.assertRaises(ValueError):
            validate_range(z)
    def test_key_persisted_privately(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pairing_key(d),pairing_key(d));self.assertEqual((pathlib.Path(d)/'bridge-pairing.json').stat().st_mode & 0o777,0o600)

if __name__ == '__main__': unittest.main()
