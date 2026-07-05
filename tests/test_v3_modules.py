# Tests for the V3 spec modules: schemas, rationale, cycles, delegation.

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.schemas import (
    SchemaValidationError,
    validate_findings_report,
    validate_test_results,
    load_validated_report,
    summarize_findings,
    summarize_test_results,
)
from agentscope.rationale import log_dispatch_rationale, read_rationale_log
from agentscope.cycles import get_cycle_count, increment_cycle, assert_can_dispatch
from agentscope.delegation import sign_delegation, verify_delegation, read_audit_log
from agentscope.ledger import save_ledger


VALID_FINDING = {
    "severity": "high",
    "category": "injection",
    "file": "src/api/route.ts",
    "line": 42,
    "description": "User input concatenated into SQL string.",
    "recommended_fix": "Use a parameterized query.",
    "provenance": "src/api/route.ts",
}


class TestFindingsSchema:
    def test_valid_report_passes(self):
        ok, violations = validate_findings_report({"findings": [VALID_FINDING]})
        assert ok, violations

    def test_bare_list_passes(self):
        ok, _ = validate_findings_report([VALID_FINDING])
        assert ok

    def test_freeform_severity_rejected(self):
        bad = dict(VALID_FINDING, severity="URGENT!!! FIX NOW")
        ok, violations = validate_findings_report([bad])
        assert not ok
        assert any("severity" in v for v in violations)

    def test_unknown_field_rejected(self):
        bad = dict(VALID_FINDING, execute_this="rm -rf /")
        ok, violations = validate_findings_report([bad])
        assert not ok

    def test_missing_required_rejected(self):
        ok, violations = validate_findings_report([{"severity": "low"}])
        assert not ok

    def test_load_validated_report_raises_on_bad_file(self, tmp_path):
        p = tmp_path / "FINDINGS.json"
        p.write_text(json.dumps([{"severity": "banana"}]))
        with pytest.raises(SchemaValidationError):
            load_validated_report(str(p), "findings")

    def test_summary_contains_no_free_text(self):
        summary = summarize_findings([VALID_FINDING])
        assert summary["total_findings"] == 1
        assert summary["severity_histogram"]["high"] == 1
        assert not summary["clean"]
        # Row 1: the Lead's view must not carry description/recommended_fix text.
        flat = json.dumps(summary)
        assert "SQL" not in flat


class TestTestResultsSchema:
    def test_valid(self):
        ok, _ = validate_test_results({
            "status": "fail", "passed": 10, "failed": 1,
            "failures": [{"test_name": "test_x", "error_output": "boom", "repro_command": "pytest -k x"}],
        })
        assert ok

    def test_bad_status_rejected(self):
        ok, violations = validate_test_results({"status": "mostly-fine"})
        assert not ok

    def test_summary(self):
        s = summarize_test_results({"status": "pass", "passed": 12, "failed": 0, "failures": []})
        assert s["clean"] and s["passed"] == 12


class TestRationaleLog:
    def test_write_and_read(self, tmp_path):
        log = str(tmp_path / "rationale.jsonl")
        log_dispatch_rationale("Diff ready; dispatching Security and QA in parallel",
                               action="dispatch", target_agent="security_agent",
                               backlog_item_id="item-7", cycle=1, log_path=log)
        entries = read_rationale_log(log)
        assert len(entries) == 1
        assert entries[0]["target_agent"] == "security_agent"
        assert entries[0]["cycle"] == 1

    def test_empty_rationale_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            log_dispatch_rationale("   ", action="dispatch", log_path=str(tmp_path / "r.jsonl"))

    def test_last_n(self, tmp_path):
        log = str(tmp_path / "rationale.jsonl")
        for i in range(5):
            log_dispatch_rationale(f"entry {i}", action="dispatch", log_path=log)
        assert len(read_rationale_log(log, last_n=2)) == 2


class TestCycleCounter:
    def _ledger(self, tmp_path):
        p = str(tmp_path / "TASK_LEDGER.json")
        save_ledger(p, {"project": "test", "phases": []})
        return p

    def test_increment_and_cap(self, tmp_path):
        ledger = self._ledger(tmp_path)
        assert get_cycle_count(ledger, "item-1") == 0
        r1 = increment_cycle(ledger, "item-1")
        assert r1["cycle"] == 1 and not r1["cap_reached"]
        increment_cycle(ledger, "item-1")
        r3 = increment_cycle(ledger, "item-1")
        assert r3["cycle"] == 3 and r3["cap_reached"]

    def test_dispatch_guard_raises_at_cap(self, tmp_path):
        ledger = self._ledger(tmp_path)
        for _ in range(3):
            increment_cycle(ledger, "item-2")
        with pytest.raises(RuntimeError):
            assert_can_dispatch(ledger, "item-2")

    def test_items_tracked_independently(self, tmp_path):
        ledger = self._ledger(tmp_path)
        increment_cycle(ledger, "a")
        assert get_cycle_count(ledger, "b") == 0

    def test_compact_rules_returned(self, tmp_path):
        ledger = self._ledger(tmp_path)
        result = increment_cycle(ledger, "item-3")
        assert "project_lead_agent" in result["compact_rules"]


class TestDelegation:
    def test_sign_and_verify(self, tmp_path):
        audit = str(tmp_path / "AUDIT_LOG.jsonl")
        key = str(tmp_path / "key")
        record = sign_delegation("lead-run1", "dev-run1", "item-9", "single_backlog_item",
                                 ["read_file", "write_file"], audit_log_path=audit, key_path=key)
        assert verify_delegation(record, key_path=key)

    def test_tamper_detected(self, tmp_path):
        audit = str(tmp_path / "AUDIT_LOG.jsonl")
        key = str(tmp_path / "key")
        record = sign_delegation("lead-run1", "dev-run1", "item-9", "single_backlog_item",
                                 ["read_file"], audit_log_path=audit, key_path=key)
        record["tools_granted"] = ["read_file", "run_command"]
        assert not verify_delegation(record, key_path=key)

    def test_read_audit_log_flags_validity(self, tmp_path):
        audit = str(tmp_path / "AUDIT_LOG.jsonl")
        key = str(tmp_path / "key")
        sign_delegation("lead-run1", "qa-run1", "item-9", "single_backlog_item",
                        ["run_tests"], audit_log_path=audit, key_path=key)
        # Append a forged, unsigned record.
        with open(audit, "a", encoding="utf-8") as f:
            f.write(json.dumps({"issuer": "evil", "subject": "dev", "signature": "00"}) + "\n")
        records = read_audit_log(audit, key_path=key)
        assert records[0]["signature_valid"] is True
        assert records[1]["signature_valid"] is False
