# agentscope/delegation.py
"""
Delegation authorization and audit trail signing module for AgentScope.
Generates HMAC-signed delegation records appended to an audit log at every subagent dispatch.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Any, Dict, List, Optional

DEFAULT_AUDIT_LOG_PATH = "AUDIT_LOG.jsonl"
DEFAULT_KEY_PATH = os.path.join(os.path.expanduser("~"), ".agentscope_hmac_key")

_delegation_lock = threading.RLock()


def _load_or_create_key(key_path: str = DEFAULT_KEY_PATH) -> bytes:
    """Loads the local HMAC key, creating it with secure random bytes on first use."""
    with _delegation_lock:
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                return f.read()

        dir_name = os.path.dirname(os.path.abspath(key_path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        key = secrets.token_bytes(32)
        with open(key_path, "wb") as f:
            f.write(key)
        return key


def _canonical_payload(record: Dict[str, Any]) -> bytes:
    """Deterministic serialization of the record body (excluding signature)."""
    body = {k: v for k, v in record.items() if k != "signature" and k != "signature_valid"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_delegation(
    issuer: str,
    subject: str,
    backlog_item_id: str,
    scope: str,
    tools_granted: List[str],
    audit_log_path: str = DEFAULT_AUDIT_LOG_PATH,
    key_path: str = DEFAULT_KEY_PATH,
) -> Dict[str, Any]:
    """
    Creates, signs, and appends a delegation record to the audit log.

    issuer: the dispatching agent instance (e.g. "lead-run42")
    subject: the dispatched agent instance (e.g. "dev-run42")
    scope: what the grant covers (e.g. "single_backlog_item")
    tools_granted: list of allowed tool names
    """
    if not issuer or not subject:
        raise ValueError("issuer and subject must be non-empty.")

    record: Dict[str, Any] = {
        "issuer": str(issuer),
        "subject": str(subject),
        "backlog_item_id": str(backlog_item_id),
        "scope": str(scope),
        "tools_granted": sorted(list(tools_granted)),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    key = _load_or_create_key(key_path)
    record["signature"] = hmac.new(key, _canonical_payload(record), hashlib.sha256).hexdigest()

    with _delegation_lock:
        dir_name = os.path.dirname(os.path.abspath(audit_log_path))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    return record


def verify_delegation(record: Dict[str, Any], key_path: str = DEFAULT_KEY_PATH) -> bool:
    """Verifies a delegation record's HMAC signature against the local key."""
    if not isinstance(record, dict):
        return False

    signature = record.get("signature")
    if not signature or not isinstance(signature, str):
        return False

    try:
        key = _load_or_create_key(key_path)
        expected = hmac.new(key, _canonical_payload(record), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def read_audit_log(
    audit_log_path: str = DEFAULT_AUDIT_LOG_PATH,
    verify: bool = True,
    key_path: str = DEFAULT_KEY_PATH,
) -> List[Dict[str, Any]]:
    """
    Reads the audit log. With verify=True, each record gains a 'signature_valid' boolean
    indicating whether the HMAC matches the record content.
    """
    if not os.path.exists(audit_log_path):
        return []

    records: List[Dict[str, Any]] = []
    with _delegation_lock:
        with open(audit_log_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if isinstance(record, dict):
                        if verify:
                            record["signature_valid"] = verify_delegation(record, key_path)
                        records.append(record)
                except json.JSONDecodeError:
                    # Ignore or record corrupted log line
                    continue

    return records
