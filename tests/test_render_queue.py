import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from render_queue import RenderQueue
from test_bridge import archive

FAKE='''#!/usr/bin/env python3
import pathlib,sys,time
args=sys.argv
folder=pathlib.Path(args[args.index('--jobs')+1])
mode=pathlib.Path(__file__).with_suffix('.mode').read_text()
print('Building saved design',flush=True)
if mode=='slow':time.sleep(20)
if mode=='fail':sys.exit(3)
if mode=='missing':sys.exit(0)
render=folder/'renders';render.mkdir()
with __import__('zipfile').ZipFile(folder.parent/'source.zip') as z:
 manifest=__import__('json').loads(z.read('range.json'));data=z.read(manifest['jobs'][0]['texture'])
(render/'daybreak_.png').write_bytes(data if mode!='partial' else data[:-12])
pathlib.Path(args[args.index('--save')+1]).write_bytes(b'BLENDER test fixture')
print('Saved result',flush=True)
'''

class QueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.binary=self.root/'fake';self.binary.write_text(FAKE);self.binary.chmod(0o700)
  self.mode=self.binary.with_suffix('.mode');self.mode.write_text('ok')
  self.q=RenderQueue(self.root/'queue','unused',timeout=3)
 def tearDown(self):
  self.q.close();self.tmp.cleanup()
 def submit(self,key=''):
  return self.q.submit(archive(),str(self.binary),{'open':False},key)
 def wait(self,ident,status):
  end=time.time()+8
  while time.time()<end:
   r=next(r for r in self.q.snapshot() if r['id']==ident)
   if r['status'] in status:return r
   time.sleep(.03)
  self.fail(str(self.q.snapshot()))
 def test_complete_idempotency_and_results(self):
  body=archive();r=self.q.submit(body,str(self.binary),{},'same')
  self.assertEqual(self.q.submit(body,str(self.binary),{},'same')['id'],r['id'])
  done=self.wait(r['id'],{'complete'})
  self.assertTrue(self.q.result_file(r['id'],'png').is_file())
  self.assertTrue(done['log']);self.assertEqual(len(self.q.snapshot()),1)
  with self.assertRaises(KeyError):self.q.result_file('../escape','png')
 def test_running_cancel_and_fresh_retry(self):
  self.mode.write_text('slow');r=self.submit();self.wait(r['id'],{'running'})
  self.q.action(r['id'],'cancel');self.wait(r['id'],{'cancelled'})
  with self.assertRaises(KeyError):self.q.result_file(r['id'],'png')
  self.mode.write_text('ok');self.q.action(r['id'],'retry');done=self.wait(r['id'],{'complete'})
  self.assertEqual(done['attempt'],2)
  self.assertIn('attempt-2',str(self.q.result_file(r['id'],'blend')))
 def test_queued_cancel_serial_work_and_restart(self):
  self.mode.write_text('slow');a=self.submit();self.wait(a['id'],{'running'});b=self.submit()
  self.q.action(b['id'],'cancel');self.assertEqual(self.wait(b['id'],{'cancelled'})['status'],'cancelled')
  self.assertEqual(sum(r['status']=='running' for r in self.q.snapshot()),1)
  self.q.close();self.q=RenderQueue(self.root/'queue','unused')
  self.assertEqual(self.wait(a['id'],{'interrupted'})['status'],'interrupted')
  self.assertEqual(self.wait(b['id'],{'cancelled'})['status'],'cancelled')
 def test_failure_timeout_and_no_false_success(self):
  for mode in ['fail','missing','partial','slow']:
   with self.subTest(mode=mode):
    self.mode.write_text(mode);r=self.submit();failed=self.wait(r['id'],{'failed'})
    self.assertIsNone(failed['result'])
 def test_partial_upload_rejected(self):
  with self.assertRaises(zipfile.BadZipFile):self.q.submit(b'PKpartial',str(self.binary),{})

if __name__=='__main__':unittest.main()
