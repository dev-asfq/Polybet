"""Lightweight JSON persistence — swap for Postgres in production."""

import json, os, threading
from typing import Dict, List
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "/tmp/pmbot.json")
_lock = threading.Lock()


def _load() -> Dict:
    if not os.path.exists(DB_PATH):
        return {"users": {}}
    try:
        with open(DB_PATH) as f:
            return json.load(f)
    except Exception:
        return {"users": {}}


def _save(data: Dict):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, default=str)


def get_user(uid: int) -> Dict:
    with _lock:
        db = _load()
        k = str(uid)
        if k not in db["users"]:
            db["users"][k] = {
                "id": uid,
                "alerts": True,
                "alert_arb": True,
                "alert_signals": True,
                "alert_insider": True,
                "min_profit_pct": 2.0,
                "joined": datetime.now().isoformat(),
            }
            _save(db)
        return db["users"][k]


def update_user(uid: int, data: Dict):
    with _lock:
        db = _load()
        k = str(uid)
        db["users"].setdefault(k, {}).update(data)
        _save(db)


def all_users() -> List[Dict]:
    with _lock:
        return list(_load().get("users", {}).values())
