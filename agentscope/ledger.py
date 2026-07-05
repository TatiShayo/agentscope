# agentscope/ledger.py

import json
import os
from typing import Dict, Any, Optional

def load_ledger(ledger_path: str) -> Dict[str, Any]:
    """Loads the task ledger from file."""
    if not os.path.exists(ledger_path):
        raise FileNotFoundError(f"Task ledger file not found at: {ledger_path}")
    with open(ledger_path, "r") as f:
        return json.load(f)

def save_ledger(ledger_path: str, ledger_data: Dict[str, Any]) -> None:
    """Saves the task ledger to file."""
    with open(ledger_path, "w") as f:
        json.dump(ledger_data, f, indent=2)

def update_task_trace(ledger_path: str, phase_num: int, task_id: str, trace_id: str) -> bool:
    """
    Finds a task by phase number and task ID, updates its status to 'COMPLETED',
    and populates its 'trace_id' field.
    """
    ledger = load_ledger(ledger_path)
    updated = False
    
    for phase in ledger.get("phases", []):
        if phase.get("phase") == phase_num:
            for task in phase.get("tasks", []):
                if task.get("id") == task_id:
                    task["trace_id"] = trace_id
                    task["status"] = "COMPLETED"
                    updated = True
                    break
            if updated:
                break
                
    if updated:
        save_ledger(ledger_path, ledger)
    return updated

def resolve_trace_link(ledger_path: str, phase_num: int, task_id: str, jaeger_host: str = "http://localhost:16686") -> Optional[str]:
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
                        return f"{jaeger_host}/trace/{trace_id}"
    return None
