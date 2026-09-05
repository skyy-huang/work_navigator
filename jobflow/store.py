"""职航数据持久化：JSON 文件存储"""

import json
import os

from jobflow.seed import DEFAULT_PROFILE, JOBS

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_STORE_FILE = os.path.join(_DATA_DIR, "jobflow_store.json")


def _new_store():
    return {
        "profile": dict(DEFAULT_PROFILE),
        "resume": None,
        "jobs": [dict(job) for job in JOBS],
        "applications": [],
    }


def load_store():
    """读取商店数据；文件不存在或损坏时使用默认种子。"""
    os.makedirs(_DATA_DIR, exist_ok=True)
    if os.path.exists(_STORE_FILE):
        try:
            with open(_STORE_FILE, "r", encoding="utf-8") as fh:
                store = json.load(fh)
            store.setdefault("profile", dict(DEFAULT_PROFILE))
            store.setdefault("resume", None)
            store.setdefault("jobs", [dict(job) for job in JOBS])
            store.setdefault("applications", [])
            return store
        except (json.JSONDecodeError, OSError):
            pass
    store = _new_store()
    save_store(store)
    return store


def save_store(store):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_STORE_FILE, "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2)
