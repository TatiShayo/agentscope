# agentscope/schemas.py
"""
Schema validation and sanitization for inter-agent data passing in AgentScope.
Enforces strict enums, structure, and provides sanitized status-summary views to prevent prompt injection.
"""

import json
import os
from typing import Any, Dict, List, Tuple

SEVERITY_ENUM = ["critical", "high", "medium", "low"]
CATEGORY_ENUM = [
    "injection",
    "broken-object-level-auth",
    "race-condition",
    "secrets-exposure",
    "agent-safety",
    "other",
]
TEST_STATUS_ENUM = ["pass", "fail", "flaky"]

FINDING_REQUIRED_FIELDS = ["severity", "category", "file", "description"]
FINDING_ALLOWED_FIELDS = FINDING_REQUIRED_FIELDS + ["line", "recommended_fix", "provenance"]
TEST_RESULT_REQUIRED_FIELDS = ["status"]


class SchemaValidationError(ValueError):
    """A report failed strict schema validation and must not be consumed by another agent."""


def validate_finding(finding: Any) -> List[str]:
    """Validates a single finding dict. Returns a list of violation strings (empty = valid)."""
    errors: List[str] = []
    if not isinstance(finding, dict):
        return [f"finding is not an object: {type(finding).__name__}"]

    for field in FINDING_REQUIRED_FIELDS:
        if field not in finding:
            errors.append(f"missing required field '{field}'")

    if "severity" in finding and finding["severity"] not in SEVERITY_ENUM:
        errors.append(f"severity '{finding['severity']}' not in enum {SEVERITY_ENUM}")
    if "category" in finding and finding["category"] not in CATEGORY_ENUM:
        errors.append(f"category '{finding['category']}' not in enum {CATEGORY_ENUM}")
    if "line" in finding and finding["line"] is not None and not isinstance(finding["line"], int):
        errors.append("line must be an integer")

    for field in ("file", "description", "recommended_fix", "provenance"):
        if field in finding and finding[field] is not None and not isinstance(finding[field], str):
            errors.append(f"{field} must be a string")

    unknown = set(finding.keys()) - set(FINDING_ALLOWED_FIELDS)
    if unknown:
        errors.append(f"unknown fields not permitted by schema: {sorted(unknown)}")

    return errors


def validate_findings_report(report: Any) -> Tuple[bool, List[str]]:
    """
    Validates a full FINDINGS.json payload: {"findings": [...]} or a bare list of findings.
    Returns (is_valid, violations).
    """
    findings = report.get("findings") if isinstance(report, dict) else report
    if not isinstance(findings, list):
        return False, ["report must be a list of findings or {'findings': [...]}"]

    violations: List[str] = []
    for i, finding in enumerate(findings):
        for err in validate_finding(finding):
            violations.append(f"findings[{i}]: {err}")
    return len(violations) == 0, violations


def validate_test_results(report: Any) -> Tuple[bool, List[str]]:
    """
    Validates a TEST_RESULTS.json payload:
    {"status": pass|fail|flaky, "passed": int, "failed": int, "failures": [...]}
    """
    if not isinstance(report, dict):
        return False, ["report must be an object"]

    violations: List[str] = []
    for field in TEST_RESULT_REQUIRED_FIELDS:
        if field not in report:
            violations.append(f"missing required field '{field}'")

    if "status" in report and report["status"] not in TEST_STATUS_ENUM:
        violations.append(f"status '{report['status']}' not in enum {TEST_STATUS_ENUM}")

    for field in ("passed", "failed"):
        if field in report and report[field] is not None and not isinstance(report[field], int):
            violations.append(f"{field} must be an integer")

    failures = report.get("failures", [])
    if not isinstance(failures, list):
        violations.append("failures must be a list")
    else:
        for i, f in enumerate(failures):
            if not isinstance(f, dict):
                violations.append(f"failures[{i}] must be an object")
                continue
            for field in ("test_name", "repro_command", "error_output"):
                if field in f and f[field] is not None and not isinstance(f[field], str):
                    violations.append(f"failures[{i}].{field} must be a string")

    return len(violations) == 0, violations


def load_validated_report(path: str, kind: str) -> Dict[str, Any]:
    """
    Loads and validates a report file before it may be consumed by another agent.
    kind: 'findings' or 'test_results'. Raises SchemaValidationError on violation.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Report not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            report = json.load(f)
        except json.JSONDecodeError as e:
            raise SchemaValidationError(f"Invalid JSON in {path}: {e}")

    if kind == "findings":
        ok, violations = validate_findings_report(report)
    elif kind == "test_results":
        ok, violations = validate_test_results(report)
    else:
        raise ValueError(f"Unknown report kind: '{kind}'. Expected 'findings' or 'test_results'.")

    if not ok:
        raise SchemaValidationError(
            f"{path} failed schema validation; refusing to pass to consuming agent:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
    return report if isinstance(report, dict) else {"findings": report}


def summarize_findings(report: Any) -> Dict[str, Any]:
    """
    The status-summary-only view the Lead reads: counts and a severity histogram.
    Contains no free-text fields to prevent prompt injection.
    """
    findings = report.get("findings") if isinstance(report, dict) else report
    findings = findings or []
    histogram = {sev: 0 for sev in SEVERITY_ENUM}
    for finding in findings:
        if isinstance(finding, dict):
            sev = finding.get("severity")
            if sev in histogram:
                histogram[sev] += 1
    return {
        "total_findings": len(findings),
        "severity_histogram": histogram,
        "clean": len(findings) == 0,
    }


def summarize_test_results(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    The status-summary-only view of TEST_RESULTS.json for the Lead.
    Contains counts and status, free of unparsed test outputs.
    """
    if not isinstance(report, dict):
        return {"status": "fail", "passed": 0, "failed": 0, "failure_count": 0, "clean": False}

    passed_count = int(report.get("passed", 0) or 0)
    failed_count = int(report.get("failed", 0) or 0)
    failures = report.get("failures", [])
    failure_len = len(failures) if isinstance(failures, list) else 0

    return {
        "status": report.get("status", "fail"),
        "passed": passed_count,
        "failed": failed_count,
        "failure_count": failure_len,
        "clean": report.get("status") == "pass" and failed_count == 0,
    }
