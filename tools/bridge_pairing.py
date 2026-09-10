"""Short-lived browser pairing requests, approved by the local computer owner."""
import secrets
import subprocess
import sys
import threading
import time


def approve_on_mac(code):
    if sys.platform != 'darwin':
        return False
    # Arguments are data, never interpolated into AppleScript source.
    script = '''on run argv
    set answer to display dialog (item 1 of argv) with title "Connect Daybreak Studio" buttons {"Cancel", "Allow"} default button "Cancel" cancel button "Cancel" giving up after 90
    return (button returned of answer)
end run'''
    message = ('Daybreak Studio wants to use the local Blender bridge.\n\n'
               'Approve only if you just clicked Connect to Blender and Studio shows this code:\n\n'
               + code + '\n\nThis allows Studio to submit renders and access their results.')
    try:
        result = subprocess.run(['osascript', '-e', script, message], capture_output=True,
                                text=True, timeout=95)
        return result.returncode == 0 and result.stdout.strip() == 'Allow'
    except (OSError, subprocess.TimeoutExpired):
        return False


class PairingRequests:
    def __init__(self, approve=approve_on_mac, clock=time.monotonic):
        self.approve, self.clock = approve, clock
        self.lock = threading.Lock()
        self.request = None
        self.last_start = float('-inf')

    def start(self):
        with self.lock:
            now = self.clock()
            if now-self.last_start < 10 or self.request and self.request['status'] == 'pending' and now < self.request['expires']:
                raise ValueError('A connection request is already open. Finish it before trying again.')
            r = dict(id=secrets.token_hex(32), code=f'{secrets.randbelow(1000000):06}',
                     status='pending', expires=now+100)
            self.request = r
            self.last_start = now
        threading.Thread(target=self._approve, args=(r,), daemon=True).start()
        return {'id': r['id'], 'code': r['code'], 'expires_in': 100}

    def _approve(self, r):
        try:
            approved = self.approve(r['code'])
        except Exception:
            approved = False
        with self.lock:
            if self.request is r and self.clock() < r['expires']:
                r['status'] = 'approved' if approved else 'denied'

    def poll(self, ident, token):
        with self.lock:
            r = self.request
            if not isinstance(ident, str) or not r or not secrets.compare_digest(ident, r['id']) or self.clock() >= r['expires']:
                return {'status': 'expired'}
            if r['status'] == 'approved':
                # The secret poll ID stays usable briefly so a lost HTTP response
                # can be retried, but no later than the original expiry.
                return {'status': 'approved', 'token': token}
            return {'status': r['status']}
