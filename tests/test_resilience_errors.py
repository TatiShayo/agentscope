# tests/test_resilience_errors.py
"""
Resilience, edge cases, and security error tests for AgentScope.
Verifies graceful error handling on unreachable endpoints, corrupted files,
invalid schemas, and cryptographic tampering.
"""

import json
import os
import sys
import urllib.error
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.cost import aggregate_cost, aggregate_cost_from_spans
from agentscope.ledger import load_ledger, save_ledger, update_task_trace, resolve_trace_link
from agentscope.delegation import sign_delegation, verify_delegation, read_audit_log
from agentscope.rationale import log_dispatch_rationale, read_rationale_log
from agentscope.cycles import increment_cycle, assert_can_dispatch, get_cycle_count, reset_cycle_count
from agentscope.schemas import (
    SchemaValidationError,
    validate_findings_report,
    validate_test_results,
    load_validated_report,
)
from agentscope.tree import fetch_trace_data, render_trace


class TestJaegerNetworkResilience:
    def test_aggregate_cost_empty_trace_id_raises_value_error(self):
        with pytest.raises(ValueError, match="trace_id must be a non-empty string"):
            aggregate_cost("   ")

    @patch("urllib.request.urlopen")
    def test_aggregate_cost_jaeger_unreachable_raises_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused [Errno 111]")
        with pytest.raises(ConnectionError, match="Failed to connect to Jaeger"):
            aggregate_cost("0123456789abcdef0123456789abcdef", jaeger_url="http://localhost:9999")

    @patch("urllib.request.urlopen")
    def test_aggregate_cost_trace_not_found(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"data": []}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="not found in Jaeger"):
            aggregate_cost("missing_trace_id")

    @patch("urllib.request.urlopen")
    def test_fetch_trace_data_invalid_json(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"<!DOCTYPE html><html>502 Bad Gateway</html>"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with pytest.raises(ValueError, match="Error fetching trace"):
            fetch_trace_data("bad_trace_id")


class TestLedgerResilience:
    def test_load_non_existent_ledger_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_ledger(str(tmp_path / "non_existent.json"))

    def test_load_corrupt_json_ledger_raises_value_error(self, tmp_path):
        corrupt_file = tmp_path / "corrupt.json"
        corrupt_file.write_text("{ unquoted_key: invalid_json }")
        with pytest.raises(ValueError, match="Corrupt JSON"):
            load_ledger(str(corrupt_file))

    def test_save_ledger_invalid_type_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="ledger_data must be a dictionary"):
            save_ledger(str(tmp_path / "out.json"), ["not a dict"])

    def test_update_task_trace_empty_trace_id_raises(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        save_ledger(ledger_path, {"phases": []})
        with pytest.raises(ValueError, match="trace_id must not be empty"):
            update_task_trace(ledger_path, 1, "task-1", "   ")

    def test_update_task_trace_missing_task_returns_false(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        save_ledger(ledger_path, {"phases": [{"phase": 1, "tasks": []}]})
        updated = update_task_trace(ledger_path, 1, "missing-task", "trace-123")
        assert updated is False

    def test_resolve_trace_link_missing_task_returns_none(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        save_ledger(ledger_path, {"phases": [{"phase": 1, "tasks": []}]})
        assert resolve_trace_link(ledger_path, 1, "non_existent") is None


class TestDelegationAndCryptoResilience:
    def test_verify_delegation_empty_or_tampered(self, tmp_path):
        key = str(tmp_path / "key")
        # Empty signature
        assert verify_delegation({}, key_path=key) is False
        assert verify_delegation({"signature": ""}, key_path=key) is False

        # Valid sign then tamper payload
        record = sign_delegation("lead", "dev", "item-1", "scope", ["tool1"], key_path=key)
        record["issuer"] = "imposter"
        assert verify_delegation(record, key_path=key) is False

    def test_sign_delegation_empty_issuer_raises_value_error(self, tmp_path):
        key = str(tmp_path / "key")
        with pytest.raises(ValueError):
            sign_delegation("", "dev", "item-1", "scope", ["t1"], key_path=key)


class TestCyclesAndRationaleResilience:
    def test_reset_cycle_count(self, tmp_path):
        ledger_path = str(tmp_path / "LEDGER.json")
        save_ledger(ledger_path, {"phases": []})
        increment_cycle(ledger_path, "item-alpha")
        increment_cycle(ledger_path, "item-alpha")
        assert get_cycle_count(ledger_path, "item-alpha") == 2

        reset_cycle_count(ledger_path, "item-alpha")
        assert get_cycle_count(ledger_path, "item-alpha") == 0

    def test_read_rationale_missing_file_returns_empty_list(self, tmp_path):
        assert read_rationale_log(str(tmp_path / "missing.jsonl")) == []


class TestRenderTraceResilience:
    def test_render_trace_unsupported_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported render format"):
            render_trace([], output_format="unsupported_3d_format")
