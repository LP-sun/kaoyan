"""Share in-process locks across service objects opening the same SQLite file."""
import os
import threading
from weakref import WeakValueDictionary
_guard=threading.Lock()
_locks=WeakValueDictionary()


def database_lock(path):
    key=os.path.normcase(str(path))
    with _guard:
        lock=_locks.get(key)
        if lock is None:
            lock=threading.RLock()
            _locks[key]=lock
        return lock
