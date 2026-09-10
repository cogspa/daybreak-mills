"""Isolated real bridge HTTP handler for browser pairing integration tests."""
import pathlib
import sys
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import bridge as B
from bridge_security import pairing_key
from bridge_pairing import PairingRequests
folder=sys.argv[1]
if "--approve-pairing" in sys.argv:
    B.PAIRING=PairingRequests(lambda code:True)
B.STATE.update(token=pairing_key(folder), blender=sys.executable, cfg={'open':False,'hdri':''}, history=[],led={},folders=[])
with patch.object(B.W,'list_blenders',return_value=[{'path':sys.executable,'version':'5.1.0'}]),patch.object(B.W,'blender_version',return_value=(5,1,0)):
    with B.ThreadingHTTPServer(('127.0.0.1',0),B.Handler) as server:
        print(server.server_port,flush=True)
        server.serve_forever()
