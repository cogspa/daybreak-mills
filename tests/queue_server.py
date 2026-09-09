"""Disposable bridge and fake Blender for end-to-end queue controls."""
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import bridge as B
from bridge_security import pairing_key
from render_queue import RenderQueue
from test_render_queue import FAKE
folder=Path(sys.argv[1]);binary=folder/'fake';binary.write_text(FAKE);binary.chmod(0o700);binary.with_suffix('.mode').write_text('slow')
B.W.JOBS=str(folder)
B.STATE.update(token=pairing_key(folder),blender=str(binary),cfg={'open':False,'hdri':''},history=[],led={},folders=[])
B.STATE['queue']=RenderQueue(folder/'.render-queue','unused',B.STATE['lock'])
try:
 with patch.object(B.W,'list_blenders',return_value=[{'path':str(binary),'version':'5.1.0'}]),patch.object(B.W,'blender_version',return_value=(5,1,0)):
  with B.ThreadingHTTPServer(('127.0.0.1',0),B.Handler) as server:
   print(server.server_port,flush=True);server.serve_forever()
finally:B.STATE['queue'].close()
