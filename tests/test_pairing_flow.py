import threading
import time
import unittest
from unittest.mock import patch
import test_bridge as fixture
B=fixture.B
from bridge_pairing import PairingRequests, approve_on_mac

class PairingTests(unittest.TestCase):
 def wait(self,p,r):
  for _ in range(100):
   result=p.poll(r['id'],'test-secret')
   if result['status']!='pending':return result
   time.sleep(.005)
  self.fail('Approval did not finish')
 def test_approval_and_private_poll(self):
  gate=threading.Event();p=PairingRequests(lambda code:gate.wait(1));r=p.start()
  self.assertEqual(p.poll('wrong','test-secret'),{'status':'expired'})
  self.assertEqual(p.poll(r['id'],'test-secret'),{'status':'pending'})
  with self.assertRaises(ValueError):p.start()
  gate.set();self.assertEqual(self.wait(p,r),{'status':'approved','token':'test-secret'})
 def test_denied_and_expired_never_disclose_token(self):
  now=[0];p=PairingRequests(lambda code:False,lambda:now[0]);r=p.start()
  self.assertEqual(self.wait(p,r),{'status':'denied'})
  now[0]=101;self.assertEqual(p.poll(r['id'],'test-secret'),{'status':'expired'})
 def test_late_approval_does_not_revive_expired_request(self):
  now=[0];gate=threading.Event();p=PairingRequests(lambda code:gate.wait(1),lambda:now[0]);r=p.start();now[0]=101;gate.set()
  self.assertEqual(p.poll(r['id'],'test-secret'),{'status':'expired'})
 def test_native_prompt_uses_explicit_allow(self):
  with patch('bridge_pairing.sys.platform','darwin'),patch('bridge_pairing.subprocess.run') as run:
   run.return_value.returncode=0;run.return_value.stdout='Cancel\n';self.assertFalse(approve_on_mac('123456'))
   run.return_value.stdout='Allow\n';self.assertTrue(approve_on_mac('123456'))
   self.assertIn('123456',run.call_args.args[0][-1])

class PairingHTTPTests(unittest.TestCase):
 setUpClass=classmethod(fixture.SecurityTests.setUpClass.__func__)
 tearDownClass=classmethod(fixture.SecurityTests.tearDownClass.__func__)
 request=fixture.SecurityTests.request
 def test_pairing_endpoints_require_local_origin_and_explicit_approval(self):
  with patch.object(B,'PAIRING',PairingRequests(lambda code:False)):
   self.assertEqual(self.request('/pair/start','POST','',Origin='https://example.com')[0],403)
   code,_,request=self.request('/pair/start','POST','',Origin='null');self.assertEqual(code,202)
   result=self.request('/pair/result','POST',__import__('json').dumps({'id':request['id']}),Origin='null')[2]
   self.assertNotIn('token',result)
   self.assertEqual(self.request('/pair/start','POST','',Origin='null')[0],429)
