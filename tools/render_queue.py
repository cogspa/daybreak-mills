"""Durable, serial Blender work. Every attempt owns its input and output folder."""
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time
import zipfile
from bridge_security import validate_range

TERMINAL = {'complete', 'failed', 'cancelled', 'interrupted'}


class RenderQueue:
    def __init__(self, folder, pipeline, build_lock=None, opener=None, timeout=900):
        self.root = Path(folder)
        self.root.mkdir(parents=True, exist_ok=True)
        self.pipeline, self.opener, self.timeout = str(pipeline), opener, timeout
        self.lock = threading.RLock()
        self.build_lock = build_lock or threading.Lock()
        self.wake, self.stop = threading.Event(), threading.Event()
        self.records, self.process = [], None
        self.active = None
        self.file = self.root/'queue.json'
        if self.file.exists():
            self.records = json.loads(self.file.read_text())
        for r in self.records:
            if r['status'] in ('running', 'cancelling'):
                r.update(status='interrupted', message='Bridge stopped during this attempt. Retry to rebuild.', finished=time.time())
        self._save()
        self.worker = threading.Thread(target=self._work, daemon=True, name='render-queue')
        self.worker.start()
        self.wake.set()

    def _save(self):
        temp = self.file.with_suffix('.pending')
        temp.write_text(json.dumps(self.records))
        os.replace(temp, self.file)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.records))

    def submit(self, body, blender, cfg, request_id=''):
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            manifest = validate_range(z)
        digest = hashlib.sha256(body).hexdigest()
        with self.lock:
            if request_id:
                found = next((r for r in self.records if r['request_id'] == request_id), None)
                if found:
                    if found['sha256'] != digest:
                        raise ValueError('This submission ID already belongs to another package.')
                    return dict(found)
            if sum(r['status'] not in TERMINAL for r in self.records) >= 20:
                raise ValueError('Queue is full. Wait for a build or cancel queued work.')
            ident = secrets.token_hex(16)
            folder = self.root/ident
            folder.mkdir()
            (folder/'source.zip').write_bytes(body)
            r = dict(id=ident, request_id=request_id or ident, sha256=digest, status='queued',
                     created=time.time(), attempt=1, blender=blender, cfg=dict(cfg),
                     design=manifest.get('design_export'), boxes=len(manifest['jobs']),
                     message='Waiting for Blender', log=[], result=None)
            self.records.append(r)
            self._save()
            self.wake.set()
            return dict(r)

    def action(self, ident, action):
        with self.lock:
            r = next((r for r in self.records if r['id'] == ident), None)
            if not r:
                raise KeyError('Queue entry not found')
            if action == 'cancel':
                if r['status'] == 'queued':
                    r.update(status='cancelled', message='Cancelled before starting', finished=time.time())
                elif r['status'] == 'running':
                    r.update(status='cancelling', message='Stopping Blender')
            elif action == 'retry':
                if r['status'] not in {'failed', 'cancelled', 'interrupted'}:
                    raise ValueError('Only failed, cancelled or interrupted jobs can be retried.')
                r.update(status='queued', message='Waiting to retry', attempt=r['attempt']+1, result=None, log=[])
                r.pop('finished', None)
            else:
                raise ValueError('Unknown queue action')
            self._save()
            self.wake.set()
            return dict(r)

    def result_file(self, ident, kind):
        with self.lock:
            r = next((r for r in self.records if r['id'] == ident), None)
            if not r or r['status'] != 'complete' or kind not in ('png', 'blend'):
                raise KeyError('Completed result not found')
            return self.root/ident/('attempt-'+str(r['attempt']))/('result.blend' if kind == 'blend' else 'renders/daybreak_.png')

    def _update(self, r, **fields):
        with self.lock:
            r.update(fields)
            self._save()

    def _work(self):
        while not self.stop.is_set():
            self.wake.wait(0.25)
            self.wake.clear()
            with self.lock:
                r = next((r for r in self.records if r['status'] == 'queued'), None)
            if not r:
                continue
            # Folder-watcher work and queue work share one Blender slot.
            if not self.build_lock.acquire(timeout=.25):
                self.wake.set()
                continue
            try:
                with self.lock:
                    if r['status'] != 'queued':
                        continue
                    self.active = r['id']
                    self._update(r, status='running', started=time.time(), message='Preparing saved package')
                self._run(r)
            except Exception as e:
                self._update(r, status='failed', message=str(e), finished=time.time(), result=None)
            finally:
                self.active, self.process = None, None
                self.build_lock.release()
                self.wake.set()

    def _terminate(self, p):
        if p.poll() is not None:
            return
        try:
            if os.name == 'posix':
                os.killpg(p.pid, signal.SIGTERM)
            else:
                p.terminate()
        except ProcessLookupError:
            pass
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
            p.wait()

    def _run(self, r):
        folder = self.root/r['id']/('attempt-'+str(r['attempt']))
        folder.mkdir()
        with zipfile.ZipFile(self.root/r['id']/'source.zip') as z:
            validate_range(z)
            z.extractall(folder)
        args = [r['blender'], '--background', '--python', self.pipeline, '--', '--jobs', str(folder), '--render', '--save', str(folder/'result.blend')]
        if r['boxes'] == 1:
            args.append('--hero')
        if r['cfg'].get('hdri'):
            args += ['--hdri', r['cfg']['hdri']]
        self._update(r, message='Building and rendering in Blender')
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', start_new_session=(os.name == 'posix'))
        self.process = p
        def read():
            with (folder/'build.log').open('w') as log_file:
                for line in p.stdout:
                    log_file.write(line)
                    with self.lock:
                        r['log'] = (r['log']+[line.strip()[-400:]])[-16:]
                        if 'UV check' in line:
                            r['message'] = 'Building box geometry'
                        elif any(t in line for t in ('Rendering', 'Sample', 'Fra:')):
                            r['message'] = 'Rendering image'
                        elif 'Saved' in line or 'saved' in line:
                            r['message'] = 'Saving results'
                        self._save()
            p.stdout.close()
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        reason = None
        while p.poll() is None:
            if self.stop.is_set():
                reason = 'interrupted'
            elif r['status'] == 'cancelling':
                reason = 'cancelled'
            elif time.time()-r['started'] > self.timeout:
                reason = 'failed'
            if reason:
                self._terminate(p)
                break
            time.sleep(.1)
        reader.join(timeout=3)
        if r['status'] == 'cancelling':
            reason = 'cancelled'
        if reason or p.returncode:
            self._update(r, status=reason or 'failed', finished=time.time(), message=('Blender exceeded the time limit' if reason == 'failed' else reason or 'Blender exited '+str(p.returncode)), result=None)
            return
        png, blend = folder/'renders/daybreak_.png', folder/'result.blend'
        if not png.is_file() or not blend.is_file() or blend.stat().st_size == 0:
            raise ValueError('Blender exited without a complete render and scene.')
        with png.open('rb') as f:
            if f.read(8) != b'\x89PNG\r\n\x1a\n':
                raise ValueError('Invalid rendered PNG')
            f.seek(-12, 2)
            if f.read() != b'\x00\x00\x00\x00IEND\xaeB`\x82':
                raise ValueError('Incomplete rendered PNG')
        with self.lock:
            if r['status'] == 'cancelling':
                self._update(r, status='cancelled', finished=time.time(), message='Cancelled', result=None)
                return
            self._update(r, status='complete', finished=time.time(), message='Render and scene ready', result={'png':f'/queue/{r["id"]}/png', 'blend':f'/queue/{r["id"]}/blend'})
        if r['cfg'].get('open') and self.opener:
            try:
                self.opener(r['blender'], str(blend))
            except Exception as e:
                self._update(r, message='Render ready; could not open Blender: '+str(e))

    def close(self):
        self.stop.set()
        self.wake.set()
        self.worker.join(timeout=8)
