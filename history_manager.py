import threading
from datetime import date

_user_history_mem = {}
_lock = threading.Lock()

def _today():
    return date.today().isoformat()

def save_history(email, video_id, title):
    with _lock:
        if email not in _user_history_mem:
            _user_history_mem[email] = []
        
        hist = _user_history_mem[email]
        if not hist or hist[0]['video_id'] != video_id:
            hist.insert(0, {
                'video_id': video_id,
                'title': title,
                'date': _today()
            })
            if len(hist) > 50:
                _user_history_mem[email] = hist[:50]

def get_history(email):
    with _lock:
        return _user_history_mem.get(email, [])
