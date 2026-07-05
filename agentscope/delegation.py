# agentscope/delegation.py
#
# V3 spec row 11: a signed delegation record appended to the audit log at every
# dispatch — who dispatched, for which backlog item, what scope/tools, to which
# agent instance. HMAC over a local key is deliberate: the boundary here is the
# operator's own filesystem, not a third party, so a full PKI/AIP chain is
# disproportionate. AIP is the named upgrade path if delegation ever crosses
# a trust boundary the operator doesn't control.

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional

DEFAULT_AUDIT_LOG_PATH = "AUDIT_LOG.jsonl"
DEFAULT_KEY_PATH = os.path.join(os.path.expanduser("~"), ".agentscope_hmac_key")


def _load_or_create_key(key_path: str = DEFAULT_KEY_PATH) -> bytes:
    """Loads the local HMAC key, creating it on first use."""
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    key = secrets.token_bytes(32)
    with open(key_path, "wb") as f:
        f.write(key)
    return key


def _canonical_payload(record: Dict[str, Any]) -> bytes:
    """Deterministic serialization of the record body (everything except the signature)."""
    body = {k: v for k, v in record.items() if k != "signature"}
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

    issuer:  the dispatching agent instance (e.g. "lead-run42")
    subject: the dispatched agent instance (e.g. "dev-run42")
    scope:   what the grant covers (e.g. "single_backlog_item")
    """
    record = {
        "issuer": issuer,
        "subject": subject,
        "backlog_item_id": backlog_item_id,
        "scope": scope,
        "tools_granted": sorted(tools_granted),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    key = _load_or_create_key(key_path)
    record["signature"] = hmac.new(key, _canonical_payload(record), hashlib.sha256).hexdigest()

    with open(audit_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def verify_delegation(record: Dict[str, Any], key_path: str = DEFAULT_KEY_PATH) -> bool:
    """Verifies a delegation record's HMAC signature against the local key."""
    signature = record.get("signature")
    if not signature:
        return False
    key = _load_or_create_key(key_path)
    expected = hmac.new(key, _canonical_payload(record), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def read_audit_log(
    audit_log_path: str = DEFAULT_AUDIT_LOG_PATH,
    verify: bool = True,
    key_path: str = DEFAULT_KEY_PATH,
) -> List[Dict[str, Any]]:
    """
    Reads the audit log. With verify=True each record gains a "signature_valid"
    field so tampering is visible rather than silently accepted.
    """
    if not os.path.exists(audit_log_path):
        return []
    records = []
    with open(audit_log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if verify:
                record["signature_valid"] = verify_delegation(record, key_path)
            records.append(record)
    return records
