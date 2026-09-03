# agentscope/ledger.py
"""
Task ledger management and trace ID binding module for AgentScope.
Integrates task executions with OpenTelemetry trace identifiers and direct UI trace links.
"""

import json
import os
import tempfile
import threading
from typing import Dict, Any, Optional

from agentscope.constants import DEFAULT_JAEGER_URL

_ledger_lock = threading.RLock()


def load_ledger(ledger_path: str) -> Dict[str, Any]:
    """Loads and validates the task ledger from file in a thread-safe manner."""
    if not os.path.exists(ledger_path):
        raise FileNotFoundError(f"Task ledger file not found at: {ledger_path}")

    with _ledger_lock:
        with open(ledger_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Corrupt JSON in task ledger at {ledger_path}: {e}")


def save_ledger(ledger_path: str, ledger_data: Dict[str, Any]) -> None:
    """
    Saves the task ledger atomically using a temporary file to prevent corruption
    if interrupted mid-write.
    """
    if not isinstance(ledger_data, dict):
        raise ValueError("ledger_data must be a dictionary.")

    with _ledger_lock:
        dir_name = os.path.dirname(os.path.abspath(ledger_path))
        os.makedirs(dir_name, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(ledger_data, tf, indent=2)
            tf.flush()
            os.fsync(tf.fileno())
            temp_path = tf.name

        os.replace(temp_path, ledger_path)


def update_task_trace(
    ledger_path: str,
    phase_num: int,
    task_id: str,
    trace_id: str,
    status: str = "COMPLETED",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Finds a task by phase number and task ID, updates its status and populates its 'trace_id' field.
    Optionally attaches execution metadata (e.g. token counts, cost).
    """
    if not trace_id or not trace_id.strip():
        raise ValueError("trace_id must not be empty.")

    with _ledger_lock:
        ledger = load_ledger(ledger_path)
        updated = False

        for phase in ledger.get("phases", []):
            if phase.get("phase") == phase_num:
                for task in phase.get("tasks", []):
                    if task.get("id") == task_id:
                        task["trace_id"] = trace_id.strip()
                        task["status"] = status
                        if metadata:
                            task.setdefault("metadata", {}).update(metadata)
                        updated = True
                        break
                if updated:
                    break

        if updated:
            save_ledger(ledger_path, ledger)
        return updated


def resolve_trace_link(
    ledger_path: str,
    phase_num: int,
    task_id: str,
    jaeger_host: str = DEFAULT_JAEGER_URL
) -> Optional[str]:
    """
    Resolves the trace_id for a given task, returning a direct URL to view
    the task's trace in the Jaeger UI backend.
    """
    ledger = load_ledger(ledger_path)
    for phase in ledger.get("phases", []):
        if phase.get("phase") == phase_num:
            for task in phase.get("tasks", []):
                if task.get("id") == task_id:
                    trace_id = task.get("trace_id")
                    if trace_id:
                        return f"{jaeger_host.rstrip('/')}/trace/{trace_id}"
    return None
