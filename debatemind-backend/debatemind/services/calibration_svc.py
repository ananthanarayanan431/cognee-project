_progress: dict[str, int] = {}


def get_index(user_id: str) -> int:
    return _progress.get(user_id, 0)


def advance(user_id: str) -> int:
    nxt = _progress.get(user_id, 0) + 1
    _progress[user_id] = nxt
    return nxt


def reset(user_id: str) -> None:
    _progress.pop(user_id, None)
