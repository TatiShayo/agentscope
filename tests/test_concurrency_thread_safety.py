# tests/test_concurrency_thread_safety.py
"""
Concurrency and thread-safety tests for AgentScope.
Tests high-volume multithreaded tracing, concurrent ledger updates,
and parallel cryptographic delegation signing.
"""

import concurrent.futures
import json
import os
import sys
import threading
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentscope.instrumentation import (
    init_in_memory_tracer,
    init_tracer,
    get_tracer,
    reset_tracer,
    instrument_llm_call,
    instrument_tool_call,
    dispatch_subagent,
)
from agentscope.ledger import save_ledger, load_ledger, update_task_trace
from agentscope.delegation import sign_delegation, verify_delegation, read_audit_log
from agentscope.rationale import log_dispatch_rationale, read_rationale_log


class TestTracerThreadSafety:
    def test_concurrent_tracer_initialization(self):
        """Ensures multiple concurrent threads initializing tracer do not corrupt global state."""
        reset_tracer()
        tracers = []

        def init_worker(thread_idx: int):
            t = init_in_memory_tracer(f"service-{thread_idx}")[0]
            tracers.append(t)

        threads = [threading.Thread(target=init_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(tracers) == 20
        assert get_tracer() is not None
        reset_tracer()

    def test_high_volume_concurrent_span_emission(self):
        """Emits spans from 50 concurrent worker threads without losing data or crashing."""
        reset_tracer()
        tracer, exporter = init_in_memory_tracer("high-volume-test")
        num_workers = 30
        calls_per_worker = 10

        def worker_task(worker_id: int):
            with tracer.start_as_current_span(f"worker_{worker_id}") as span:
                for i in range(calls_per_worker):
                    with instrument_llm_call("gpt-4o-mini", parent_span=span) as ctx:
                        ctx.input_tokens = 10 + i
                        ctx.output_tokens = 20 + i
                    instrument_tool_call("calc", {"i": i}, i * 2, parent_span=span)

        threads = [threading.Thread(target=worker_task, args=(w,)) for w in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        spans = exporter.get_finished_spans()
        # Each worker creates: 1 parent span + (10 LLM spans + 10 tool spans) = 21 spans
        # Total = 30 * 21 = 630 spans
        expected_total = num_workers * (1 + (calls_per_worker * 2))
        assert len(spans) == expected_total
        reset_tracer()


class TestLedgerAndAuditThreadSafety:
    def test_concurrent_ledger_updates(self, tmp_path):
        ledger_path = str(tmp_path / "CONCURRENT_LEDGER.json")
        initial_data = {
            "project": "stress_test",
            "phases": [
                {
                    "phase": 1,
                    "tasks": [{"id": f"task_{i}", "status": "PENDING"} for i in range(25)]
                }
            ]
        }
        save_ledger(ledger_path, initial_data)

        def update_worker(task_idx: int):
            update_task_trace(
                ledger_path=ledger_path,
                phase_num=1,
                task_id=f"task_{task_idx}",
                trace_id=f"trace_hex_{task_idx:04d}",
                metadata={"worker": task_idx}
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(update_worker, i) for i in range(25)]
            concurrent.futures.wait(futures)

        final_ledger = load_ledger(ledger_path)
        tasks = final_ledger["phases"][0]["tasks"]
        assert len(tasks) == 25
        for i, task in enumerate(tasks):
            assert task["status"] == "COMPLETED"
            assert task["trace_id"] == f"trace_hex_{i:04d}"
            assert task["metadata"]["worker"] == i

    def test_concurrent_hmac_delegation_signing(self, tmp_path):
        audit_path = str(tmp_path / "CONCURRENT_AUDIT.jsonl")
        key_path = str(tmp_path / "keyfile")

        def sign_worker(idx: int):
            sign_delegation(
                issuer=f"lead-{idx}",
                subject=f"dev-{idx}",
                backlog_item_id=f"item-{idx}",
                scope="subagent_task",
                tools_granted=["read_file", "write_file"],
                audit_log_path=audit_path,
                key_path=key_path,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(sign_worker, i) for i in range(30)]
            concurrent.futures.wait(futures)

        records = read_audit_log(audit_path, verify=True, key_path=key_path)
        assert len(records) == 30
        assert all(r["signature_valid"] is True for r in records)

    def test_concurrent_rationale_logging(self, tmp_path):
        log_path = str(tmp_path / "CONCURRENT_RATIONALE.jsonl")

        def log_worker(idx: int):
            log_dispatch_rationale(
                rationale=f"Rationale statement #{idx}",
                action="dispatch",
                target_agent="SecurityAgent",
                backlog_item_id=f"item-{idx}",
                cycle=1,
                log_path=log_path,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(log_worker, i) for i in range(40)]
            concurrent.futures.wait(futures)

        entries = read_rationale_log(log_path)
        assert len(entries) == 40
