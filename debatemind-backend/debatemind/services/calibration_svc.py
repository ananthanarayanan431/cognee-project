from cachetools import TTLCache

# Bounded: calibration is a short guided flow, so per-user progress that hasn't
# been touched in a day is safe to forget. An unbounded dict here would grow by
# one entry per user forever (reset() only fires when a flow completes).
_progress: TTLCache = TTLCache(maxsize=4096, ttl=86400)


def get_index(user_id: str) -> int:
    return _progress.get(user_id, 0)


def advance(user_id: str) -> int:
    nxt = _progress.get(user_id, 0) + 1
    _progress[user_id] = nxt
    return nxt


def reset(user_id: str) -> None:
    _progress.pop(user_id, None)
