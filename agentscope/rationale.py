# agentscope/rationale.py
"""
Dispatch rationale log module for AgentScope.
Records one-line reasoning statements from orchestrators prior to dispatching actions.
"""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

DEFAULT_LOG_PATH = "DISPATCH_RATIONALE.jsonl"
_rationale_lock = threading.RLock()


def log_dispatch_rationale(
    rationale: str,
    action: str,
    target_agent: Optional[str] = None,
    backlog_item_id: Optional[str] = None,
    cycle: Optional[int] = None,
    log_path: str = DEFAULT_LOG_PATH,
) -> Dict[str, Any]:
    """
    Appends a one-line dispatch rationale entry. Must be called BEFORE taking an action.
    Returns the entry dictionary that was written.
    """
    if not rationale or not rationale.strip():
        raise ValueError("A dispatch rationale may not be empty — that defeats its purpose.")

    entry: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": str(action),
        "rationale": rationale.strip(),
    }
    if target_agent:
        entry["target_agent"] = str(target_agent)
    if backlog_item_id:
        entry["backlog_item_id"] = str(backlog_item_id)
    if cycle is not None:
        entry["cycle"] = int(cycle)

    with _rationale_lock:
        dir_name = os.path.dirname(os.path.abspath(log_path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    return entry


def read_rationale_log(log_path: str = DEFAULT_LOG_PATH, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
    """Reads the rationale log (whole log or last N entries). Thread-safe and fault-tolerant."""
    if not os.path.exists(log_path):
        return []

    entries: List[Dict[str, Any]] = []
    with _rationale_lock:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return entries[-last_n:] if (last_n is not None and last_n > 0) else entries
