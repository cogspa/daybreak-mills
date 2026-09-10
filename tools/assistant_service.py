"""Paired local gateway. No project files or credentials are sent as context."""
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = ROOT / '.gemini-key'
PYTHON = ROOT / '.venv-chat' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
LOCK = threading.Lock()
LAST_REQUEST = 0.0


class AssistantError(ValueError):
    """Fixed user-facing messages, never provider exception text."""


def api_key():
    try:
        return KEY_FILE.read_text().strip()
    except FileNotFoundError:
        return os.environ.get('GEMINI_API_KEY', '') or os.environ.get('GOOGLE_API_KEY', '')


def status():
    return {'configured': bool(api_key()), 'installed': PYTHON.is_file(),
            'model': os.environ.get('DAYBREAK_CHAT_MODEL', 'gemini-flash-latest')}


def save_key(data):
    key = data.get('key') if isinstance(data, dict) else None
    if not isinstance(key, str):
        raise AssistantError('Paste the API key itself into the key field.')
    key = key.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ('"', "'"):
        key = key[1:-1].strip()
    # Provider credentials are opaque. Do not assume one prefix, alphabet or
    # legacy token length; Google validates the credential on the first call.
    if not 20 <= len(key) <= 4096:
        raise AssistantError('The pasted key is too short or too long. Copy the complete API key, not its name.')
    if any(c.isspace() or not 33 <= ord(c) <= 126 for c in key):
        raise AssistantError('The key contains spaces, line breaks or non-ASCII characters. Paste only the API key, without a command or surrounding text.')
    import tempfile
    fd, name = tempfile.mkstemp(prefix='.gemini-key-', dir=ROOT)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(key)
        os.replace(name, KEY_FILE)
        os.chmod(KEY_FILE, 0o600)
    finally:
        if os.path.exists(name):os.unlink(name)
    return {'saved': True}


def validate(data):
    if not isinstance(data, dict):raise AssistantError('Invalid assistant request.')
    message=data.get('message');history=data.get('history',[]);context=data.get('context',{})
    if not isinstance(message,str) or not message.strip() or len(message)>4000:raise AssistantError('Enter a question of up to 4,000 characters.')
    if not isinstance(history,list) or len(history)>12:raise AssistantError('Too much conversation history.')
    clean=[]
    for item in history:
        if not isinstance(item,dict) or item.get('role') not in ('user','assistant') or not isinstance(item.get('text'),str) or len(item['text'])>8000:raise AssistantError('Invalid conversation history.')
        clean.append({'role':item['role'],'text':item['text']})
    if not isinstance(context,dict):raise AssistantError('Invalid app context.')
    safe={}
    for k in ['view','panel','size','shelf_layout','missing_fields','overflow_count']:
        if k in context:
            if not isinstance(context[k],(str,int)) or len(str(context[k]))>100:raise AssistantError('Invalid app context.')
            safe[k]=context[k]
    market=data.get('market','unspecified')
    if market not in ['unspecified','US','CA','UK','EU']:raise AssistantError('Choose a supported market.')
    return {'message':message.strip(),'history':clean,'context':safe,'market':market}


def answer(data):
    global LAST_REQUEST
    clean=validate(data)
    if not api_key():raise AssistantError('Add your Gemini API key in Assistant setup.')
    if not PYTHON.is_file():raise AssistantError('Install the assistant runtime using tools/setup_chat.py.')
    if not LOCK.acquire(blocking=False):raise AssistantError('The assistant is answering another question. Try again shortly.')
    try:
        if time.monotonic()-LAST_REQUEST<2:raise AssistantError('Please wait a moment before asking again.')
        LAST_REQUEST=time.monotonic()
        clean.update(key=api_key(),model=status()['model'])
        env={**os.environ,'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
        for k in ['LANGSMITH_API_KEY','LANGCHAIN_API_KEY']:env.pop(k,None)
        result=subprocess.run([str(PYTHON),str(ROOT/'tools/chat_worker.py')],input=json.dumps(clean),capture_output=True,text=True,timeout=75,env=env)
        if result.returncode:raise AssistantError('Gemini could not answer. Check the key, model access, quota and internet connection. No project changes were made.')
        payload=json.loads(result.stdout)
        if payload.get('error_code'):
            errors={
                'model_not_found':'The configured Gemini model is unavailable. Update DAYBREAK_CHAT_MODEL or use the default Gemini Flash model.',
                'quota':'Google rejected this request because of API quota or rate limits. Check your Google AI project quota/billing and retry later.',
                'authentication':'Google rejected the API credentials or permissions. Check the saved key and its API restrictions.',
                'network':'Could not connect to Gemini. Check the internet connection and retry.',
                'timeout':'Gemini timed out. Try a shorter question.',
            }
            raise AssistantError(errors.get(payload['error_code'],'Gemini could not answer this request. Try again or check model access.'))
        if not payload.get('answer'):raise AssistantError('Gemini returned no answer. Try a shorter question.')
        return payload
    except subprocess.TimeoutExpired:
        raise AssistantError('The assistant timed out. Try again with a shorter question.') from None
    finally:LOCK.release()
