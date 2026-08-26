"""Deterministic, tool-driven baseline scanning (Tier 3 of the scan-coverage
plan — see docs/scan-coverage-tier3-plan.md).

Runs once per scan, before the agent loop starts, directly against the
already-cloned source tree(s) on the host filesystem. Covers the three
coverage categories that are mechanically checkable rather than judgment
calls: dependency CVEs, secrets (including git history), and IaC/CI
misconfiguration.

Every function here degrades gracefully: a missing binary, a tool crash, a
timeout, or unparseable output logs a warning and contributes no findings
for that category. A baseline-scan problem must never abort or even slow
down the rest of the scan beyond its own bounded timeout.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 180

_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNKNOWN": "low",
}


@dataclass
class BaselineFinding:
    """One normalized finding, shaped to pass straight into
    ``ReportState.add_vulnerability_report``."""

    category: str  # "dependencies" | "secrets" | "infrastructure"
    title: str
    severity: str
    target: str
    description: str = ""
    evidence: str | None = None
    cve: str | None = None
    cwe: str | None = None
    remediation_steps: str | None = None
    dependency_metadata: dict[str, str] | None = None


@dataclass
class BaselineResult:
    findings: list[BaselineFinding] = field(default_factory=list)
    # tool name -> human-readable reason it produced nothing (missing binary,
    # timeout, parse failure, ...). Empty for a tool that ran cleanly with
    # zero findings.
    skipped_tools: dict[str, str] = field(default_factory=dict)
    raw_output: dict[str, Any] = field(default_factory=dict)

    def counts_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.category] = counts.get(f.category, 0) + 1
        return counts

    def summary_text(self) -> str:
        counts = self.counts_by_category()
        parts = [
            f"{counts.get('dependencies', 0)} dependency CVE(s)",
            f"{counts.get('secrets', 0)} secret(s) (working tree + git history)",
            f"{counts.get('infrastructure', 0)} IaC/CI misconfiguration(s)",
        ]
        text = "Baseline scan (deterministic, tool-driven) found: " + ", ".join(parts) + "."
        if self.skipped_tools:
            skipped = "; ".join(f"{tool}: {reason}" for tool, reason in self.skipped_tools.items())
            text += f" Skipped: {skipped}."
        text += (
            " See list_reports (source=baseline_scan) for full detail. These findings are "
            "already filed — do not re-discover or re-report them; a category with a nonzero "
            "count here still needs its own agent to triage/deepen (reachability, "
            "exploitability, chaining), not to rediscover the same list."
        )
        return text


def _run(
    cmd: list[str],
    *,
    timeout: int = _DEFAULT_TIMEOUT_S,
    check_stderr_on_failure: bool = True,
) -> subprocess.CompletedProcess[str] | None:
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        logger.warning("baseline scan: %s timed out after %ds", cmd[0], timeout)
        return None
    except OSError:
        logger.exception("baseline scan: %s failed to start", cmd[0])
        return None
    if check_stderr_on_failure and result.returncode not in (0, 1):
        # Most of these scanners use exit code 1 to mean "findings present",
        # not "tool failure" — only treat other codes as real errors.
        logger.warning(
            "baseline scan: %s exited %d: %s",
            cmd[0],
            result.returncode,
            result.stderr.strip()[:500],
        )
    return result


def run_dependency_baseline(
    source_paths: list[str], result: BaselineResult, timeout: int = _DEFAULT_TIMEOUT_S
) -> list[BaselineFinding]:
    """Wrap ``trivy fs``. Runs once per source root — trivy already walks
    the full tree, so a monorepo's per-workspace lockfiles are all picked up
    without needing to enumerate workspaces manually."""
    if shutil.which("trivy") is None:
        result.skipped_tools["trivy"] = "binary not found"
        return []

    findings: list[BaselineFinding] = []
    for source_path in source_paths:
        proc = _run(
            [
                "trivy",
                "fs",
                "--format",
                "json",
                "--scanners",
                "vuln",
                "--quiet",
                source_path,
            ],
            timeout=timeout,
        )
        if proc is None or not proc.stdout.strip():
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.warning("baseline scan: could not parse trivy output for %s", source_path)
            continue
        result.raw_output.setdefault("trivy", []).append(data)
        for res in data.get("Results") or []:
            manifest = res.get("Target", source_path)
            for vuln in res.get("Vulnerabilities") or []:
                severity = _SEVERITY_MAP.get(str(vuln.get("Severity", "")).upper(), "low")
                pkg = vuln.get("PkgName", "unknown")
                installed = vuln.get("InstalledVersion", "unknown")
                fixed = vuln.get("FixedVersion")
                cve = vuln.get("VulnerabilityID")
                findings.append(
                    BaselineFinding(
                        category="dependencies",
                        title=f"{cve}: {pkg}@{installed}",
                        severity=severity,
                        target=manifest,
                        description=(vuln.get("Title") or vuln.get("Description") or "")[:2000],
                        cve=cve if cve and cve.upper().startswith("CVE-") else None,
                        remediation_steps=(
                            f"Upgrade {pkg} to {fixed}."
                            if fixed
                            else "No fixed version published yet."
                        ),
                        dependency_metadata={
                            "package_name": pkg,
                            "installed_version": installed,
                            "fixed_version": fixed or "",
                            "manifest_path": manifest,
                        },
                    )
                )
    return findings


def run_secret_baseline(
    source_paths: list[str], result: BaselineResult, timeout: int = _DEFAULT_TIMEOUT_S
) -> list[BaselineFinding]:
    """Wrap ``gitleaks detect`` in git-history mode. A secret removed in a
    later commit is still found — gitleaks scans the full log, not just the
    working tree."""
    if shutil.which("gitleaks") is None:
        result.skipped_tools["gitleaks"] = "binary not found"
        return []

    findings: list[BaselineFinding] = []
    for source_path in source_paths:
        if not (Path(source_path) / ".git").exists():
            continue  # gitleaks detect requires a git repo; skip plain source dumps
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "gitleaks-report.json"
            proc = _run(
                [
                    "gitleaks",
                    "detect",
                    "--source",
                    source_path,
                    "--report-format",
                    "json",
                    "--report-path",
                    str(report_path),
                    "--no-banner",
                    "--exit-code",
                    "0",
                ],
                timeout=timeout,
            )
            if proc is None or not report_path.exists():
                continue
            try:
                data = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("baseline scan: could not parse gitleaks output for %s", source_path)
                continue
        result.raw_output.setdefault("gitleaks", []).append(data)
        for leak in data or []:
            rule = leak.get("RuleID", "secret")
            file_path = leak.get("File", source_path)
            commit = leak.get("Commit", "")
            findings.append(
                BaselineFinding(
                    category="secrets",
                    title=f"Secret detected ({rule}) in {file_path}",
                    severity="high",
                    target=file_path,
                    description=(
                        f"gitleaks matched rule '{rule}' at {file_path}"
                        + (f" (commit {commit[:12]})" if commit else " (working tree)")
                    ),
                    evidence=leak.get("Match", "")[:500],
                    remediation_steps=(
                        "Revoke/rotate the credential and remove it from history "
                        "(git-filter-repo / BFG); a later commit removing the file "
                        "is not sufficient — it remains recoverable from history."
                    ),
                )
            )
    return findings


def run_iac_baseline(
    source_paths: list[str], result: BaselineResult, timeout: int = _DEFAULT_TIMEOUT_S
) -> list[BaselineFinding]:
    """Wrap ``kube-linter`` against any Kubernetes manifests found in the tree."""
    if shutil.which("kube-linter") is None:
        result.skipped_tools["kube-linter"] = "binary not found"
        return []

    findings: list[BaselineFinding] = []
    for source_path in source_paths:
        proc = _run(
            ["kube-linter", "lint", "--format", "json", source_path],
            timeout=timeout,
        )
        if proc is None or not proc.stdout.strip():
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.warning("baseline scan: could not parse kube-linter output for %s", source_path)
            continue
        result.raw_output.setdefault("kube-linter", []).append(data)
        for report in data.get("Reports") or []:
            check = report.get("Check", "misconfiguration")
            obj = report.get("Object", {}).get("K8sObject", {}).get("Name", source_path)
            findings.append(
                BaselineFinding(
                    category="infrastructure",
                    title=f"IaC misconfiguration ({check}) in {obj}",
                    severity="medium",
                    target=obj,
                    description=report.get("Diagnostic", {}).get("Message", check),
                    remediation_steps=report.get("Remediation", None),
                )
            )
    return findings


def run_baseline_scan(
    local_sources: list[dict[str, Any]], timeout: int = _DEFAULT_TIMEOUT_S
) -> BaselineResult:
    """Run every baseline category against every resolved local source root.

    ``local_sources`` is the same list ``collect_local_sources`` produces:
    each entry has a ``source_path`` (host filesystem path). Never raises.
    """
    result = BaselineResult()
    source_paths = [s["source_path"] for s in local_sources if s.get("source_path")]
    if not source_paths:
        return result

    try:
        result.findings.extend(run_dependency_baseline(source_paths, result, timeout))
    except Exception:
        logger.exception("baseline dependency scan failed unexpectedly")
    try:
        result.findings.extend(run_secret_baseline(source_paths, result, timeout))
    except Exception:
        logger.exception("baseline secret scan failed unexpectedly")
    try:
        result.findings.extend(run_iac_baseline(source_paths, result, timeout))
    except Exception:
        logger.exception("baseline IaC scan failed unexpectedly")

    logger.info(
        "Baseline scan complete: %s (skipped: %s)",
        result.counts_by_category(),
        list(result.skipped_tools),
    )
    return result
