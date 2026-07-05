# agentscope/rationale.py
#
# V3 spec row 4: the dispatch rationale log. The Lead writes a one-line rationale
# BEFORE every dispatch/routing decision; the log is continuously readable by every
# subagent and the human. Distinct from OTel tracing (after-the-fact) and from the
# audit log (delegation records) — this is the Lead's reasoning, legible as it happens.

import json
import os
import time
from typing import Any, Dict, List, Optional

DEFAULT_LOG_PATH = "DISPATCH_RATIONALE.jsonl"


def log_dispatch_rationale(
    rationale: str,
    action: str,
    target_agent: Optional[str] = None,
    backlog_item_id: Optional[str] = None,
    cycle: Optional[int] = None,
    log_path: str = DEFAULT_LOG_PATH,
) -> Dict[str, Any]:
    """
    Appends a one-line dispatch rationale entry. Call this BEFORE taking the action,
    not after — the point is that the reasoning is visible before it's acted on.
    Returns the entry written.
    """
    if not rationale or not rationale.strip():
        raise ValueError("A dispatch rationale may not be empty — that defeats its purpose.")

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": action,
        "rationale": rationale.strip(),
    }
    if target_agent:
        entry["target_agent"] = target_agent
    if backlog_item_id:
        entry["backlog_item_id"] = backlog_item_id
    if cycle is not None:
        entry["cycle"] = cycle

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_rationale_log(log_path: str = DEFAULT_LOG_PATH, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
    """Reads the rationale log (whole log, or the last N entries). Safe for any agent to call."""
    if not os.path.exists(log_path):
        return []
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[-last_n:] if last_n else entries
