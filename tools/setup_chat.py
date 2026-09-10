"""Install the optional assistant in an isolated local environment."""
from pathlib import Path
import os
import subprocess
import venv
root=Path(__file__).resolve().parents[1]
folder=root/'.venv-chat'
venv.EnvBuilder(with_pip=True).create(folder)
python=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
subprocess.run([str(python),'-m','pip','install','-r',str(root/'tools/requirements-chat.txt')],check=True)
print('Assistant installed. In Studio choose Help & assistant, connect the bridge, then enter your key under Setup.')
