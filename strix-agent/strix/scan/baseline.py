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
import re
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
        if counts.get("extension_points"):
            parts.append(f"{counts['extension_points']} MCP/source defect(s)")
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


_TLS_DISABLED_PATTERNS = (
    "ssl=False",
    "ssl = False",
    "verify=False",
    "verify = False",
    "ssl.CERT_NONE",
    "insecure_skip_verify",
    "NODE_TLS_REJECT_UNAUTHORIZED",
)
_TLS_SCAN_SUFFIXES = frozenset({".py", ".js", ".ts", ".go", ".java", ".rb", ".rs"})
_TLS_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        "tests",
        "test",
        "__tests__",
        "site-packages",
        "dist-packages",
        ".tox",
        ".mypy_cache",
    }
)
_PYTHON_LIB_DIR_RE = re.compile(r"^python3(\.\d+)?$")
_TLS_MAX_FILES = 1200


def _is_vendored_tls_path(path: Path) -> bool:
    """Skip third-party trees (venvs, site-packages, ``lib/python3.x``)."""
    parts = path.parts
    if any(part in _TLS_SKIP_DIR_NAMES for part in parts):
        return True
    for i, part in enumerate(parts[:-1]):
        if part == "lib" and _PYTHON_LIB_DIR_RE.fullmatch(parts[i + 1]):
            return True
    return False


def _iter_first_party_source_files(
    source_paths: list[str], *, max_files: int = _TLS_MAX_FILES
) -> list[tuple[Path, str, list[str]]]:
    """Walk first-party source files once for the grep-style baselines."""
    files: list[tuple[Path, str, list[str]]] = []
    seen = 0
    for raw in source_paths:
        root = Path(raw)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if seen >= max_files:
                return files
            if path.is_dir() or _is_vendored_tls_path(path):
                continue
            if path.suffix.lower() not in _TLS_SCAN_SUFFIXES:
                continue
            seen += 1
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            files.append((path, rel, lines))
    return files


def _is_code_comment(line: str) -> bool:
    return line.strip().startswith(("#", "//"))


def run_insecure_tls_baseline(
    source_paths: list[str], result: BaselineResult, timeout: int = _DEFAULT_TIMEOUT_S
) -> list[BaselineFinding]:
    """Grep for hardcoded TLS verification disablement.

    No extra binary: SaaS backend images do not ship bandit/trivy, and this
    pattern (``ssl=False`` / ``verify=False``) is how several critical
    MCP/HTTP client bugs present in source.
    """
    del timeout  # filesystem walk; kept in the signature to match sibling runners
    findings: list[BaselineFinding] = []
    files = _iter_first_party_source_files(source_paths)
    for _path, rel, lines in files:
        for lineno, line in enumerate(lines, start=1):
            if _is_code_comment(line):
                continue
            if not any(pattern in line for pattern in _TLS_DISABLED_PATTERNS):
                continue
            stripped = line.strip()
            findings.append(
                BaselineFinding(
                    category="infrastructure",
                    title="TLS certificate verification hardcoded disabled",
                    severity="critical",
                    target=f"{rel}:{lineno}",
                    description=(
                        "Outbound HTTP(S) disables TLS verification "
                        f"({stripped[:200]}). Traffic to the configured "
                        "backend can be intercepted or altered."
                    ),
                    evidence=stripped[:500],
                    cwe="CWE-295",
                    remediation_steps=(
                        "Default TLS verification on. Make disablement an "
                        "explicit, documented development-only setting."
                    ),
                )
            )
    result.raw_output["insecure_tls"] = {"files_scanned": len(files), "hits": len(findings)}
    return findings


_BIND_ANY_RE = re.compile(r"0\.0\.0\.0|\[::\]")
_HEADER_LOG_RE = re.compile(
    r"(?:logger|logging|log)\.(?:debug|info|warning|error|exception|critical)\b.*\bheaders\b"
    r"|\bheaders\b.*(?:logger|logging|log)\.(?:debug|info|warning|error|exception|critical)\b",
    re.IGNORECASE,
)
_AUDIT_DEF_RE = re.compile(r"^(?:async\s+)?def\s+audit_tool_execution\s*\(")
_AUDIT_CALL_RE = re.compile(r"(?<!def )\baudit_tool_execution\s*\(")
_DESTRUCTIVE_TOOL_NAME_RE = re.compile(
    r"""name\s*=\s*['"](?:delete_|erase_|block_user|merge_merge_request|"""
    r"""unprotect_|unapprove_|approve_merge_request)""",
    re.IGNORECASE,
)
_APPROVAL_HINT_RE = re.compile(
    r"require_approval|approval_token|human.in.the.loop|\bhitl\b|"
    r"DESTRUCTIVE_TOOLS|destructive.flag",
    re.IGNORECASE,
)
_MCP_TOOL_FILE_RE = re.compile(
    r"input_schema|tools/call|class \w+Tool\b|FunctionTool|\bmcp\b",
    re.IGNORECASE,
)
_MCP_HTTP_HANDLER_RE = re.compile(
    r"handle_mcp_post|Streamable HTTP|handle_jsonrpc_request",
    re.IGNORECASE,
)
_MCP_HTTP_AUTH_RE = re.compile(
    r"http_require_auth|require_api_key|HTTPUnauthorized|mcp\.api_key|Bearer ",
    re.IGNORECASE,
)
_MCP_RATE_LIMIT_RE = re.compile(
    r"rate_limit|HTTPTooManyRequests|TokenBucket|asyncio\.Semaphore",
    re.IGNORECASE,
)
_UNQUOTED_API_PATH_RE = re.compile(
    r"""f['"][^'"]*(?:/projects/|/repository/files/|/api/v[34]/)\{[^}]+\}"""
)
_EXC_LEAK_RE = re.compile(
    r"""(?:['"](?:error|message|detail|data)['"]\s*:\s*|error\s*=\s*)"""
    r"""str\(\s*(?:e|err|exc)\s*\)"""
)


def _extension_finding(
    *,
    title: str,
    severity: str,
    target: str,
    description: str,
    evidence: str,
    cwe: str,
    remediation_steps: str,
) -> BaselineFinding:
    return BaselineFinding(
        category="extension_points",
        title=title,
        severity=severity,
        target=target,
        description=description,
        evidence=evidence,
        cwe=cwe,
        remediation_steps=remediation_steps,
    )


def _mcp_file_findings(rel: str, lines: list[str], file_text: str) -> list[BaselineFinding]:
    findings: list[BaselineFinding] = []
    if (
        _MCP_TOOL_FILE_RE.search(file_text)
        and _DESTRUCTIVE_TOOL_NAME_RE.search(file_text)
        and not _APPROVAL_HINT_RE.search(file_text)
    ):
        lineno, stripped = _first_match_line(lines, _DESTRUCTIVE_TOOL_NAME_RE)
        findings.append(
            _extension_finding(
                title="Destructive MCP tools have no approval gate",
                severity="high",
                target=f"{rel}:{lineno}",
                description=(
                    "This file registers destructive MCP tools "
                    f"({stripped[:200]}) without an approval / HITL check. "
                    "A single tools/call can delete or mutate state."
                ),
                evidence=stripped[:500],
                cwe="CWE-284",
                remediation_steps=(
                    "Mark destructive tools and require an approval token "
                    "or human confirmation before execute()."
                ),
            )
        )
    if _MCP_HTTP_HANDLER_RE.search(file_text) and not _MCP_HTTP_AUTH_RE.search(file_text):
        lineno, stripped = _first_match_line(lines, _MCP_HTTP_HANDLER_RE)
        findings.append(
            _extension_finding(
                title="MCP HTTP transport has no endpoint authentication",
                severity="critical",
                target=f"{rel}:{lineno}",
                description=(
                    "An MCP HTTP/JSON-RPC handler accepts requests without "
                    "an API key, Bearer check, or HTTPUnauthorized gate "
                    f"({stripped[:200]})."
                ),
                evidence=stripped[:500],
                cwe="CWE-306",
                remediation_steps=(
                    "Require a bearer API key (or mTLS) before "
                    "handle_jsonrpc_request, and bind loopback by default."
                ),
            )
        )
    if _MCP_HTTP_HANDLER_RE.search(file_text) and not _MCP_RATE_LIMIT_RE.search(file_text):
        lineno, stripped = _first_match_line(lines, _MCP_HTTP_HANDLER_RE)
        findings.append(
            _extension_finding(
                title="MCP HTTP handler has no rate limiting",
                severity="medium",
                target=f"{rel}:{lineno}",
                description=(
                    "The MCP HTTP handler has no per-client rate limit or "
                    f"concurrency cap ({stripped[:200]}). A caller can "
                    "exhaust CPU, memory, or upstream API quota."
                ),
                evidence=stripped[:500],
                cwe="CWE-770",
                remediation_steps=(
                    "Add token-bucket rate limiting and a concurrency "
                    "semaphore around tool dispatch."
                ),
            )
        )
    return findings


def _first_match_line(lines: list[str], pattern: re.Pattern[str] | str) -> tuple[int, str]:
    for lineno, line in enumerate(lines, start=1):
        if _is_code_comment(line):
            continue
        matched = pattern.search(line) if isinstance(pattern, re.Pattern) else pattern in line
        if matched:
            return lineno, line.strip()
    return 1, (lines[0].strip() if lines else "")


def run_mcp_source_baseline(
    source_paths: list[str], result: BaselineResult, timeout: int = _DEFAULT_TIMEOUT_S
) -> list[BaselineFinding]:
    """Grep first-party source for MCP defects a specialist can still miss.

    Seeded from the GitLab MCP VAPT classes the white-box specialist lost
    when it was killed: bind-any HTTP, missing endpoint auth, destructive
    tools without approval, raw header logging, unbounded ``readexactly``,
    no rate limit, unquoted path segments, exception leakage, and an
    unwired ``audit_tool_execution``. Same class of check as ``ssl=False``.
    """
    del timeout
    findings: list[BaselineFinding] = []
    files = _iter_first_party_source_files(source_paths)
    audit_defs: list[tuple[str, int, str]] = []
    audit_calls = 0
    for _path, rel, lines in files:
        file_text = "\n".join(lines)
        for lineno, line in enumerate(lines, start=1):
            if _is_code_comment(line):
                continue
            stripped = line.strip()
            if _BIND_ANY_RE.search(line):
                findings.append(
                    BaselineFinding(
                        category="extension_points",
                        title="Service binds on all interfaces (0.0.0.0 / ::)",
                        severity="critical",
                        target=f"{rel}:{lineno}",
                        description=(
                            "A listener or host setting binds every interface "
                            f"({stripped[:200]}). Combined with missing endpoint "
                            "auth this exposes the service on the network."
                        ),
                        evidence=stripped[:500],
                        cwe="CWE-1327",
                        remediation_steps=(
                            "Bind 127.0.0.1 unless remote access is required, "
                            "and put TLS plus application authentication in "
                            "front of the listener."
                        ),
                    )
                )
            if _HEADER_LOG_RE.search(line):
                findings.append(
                    BaselineFinding(
                        category="extension_points",
                        title="HTTP request headers logged at runtime",
                        severity="high",
                        target=f"{rel}:{lineno}",
                        description=(
                            "Request headers are written to logs "
                            f"({stripped[:200]}). Authorization, cookies, and "
                            "tokens in those headers become secrets in log sinks."
                        ),
                        evidence=stripped[:500],
                        cwe="CWE-532",
                        remediation_steps=(
                            "Log header names only, or a denylisted allow-list. "
                            "Never serialize raw request.headers at warning/info."
                        ),
                    )
                )
            if "readexactly(" in line:
                findings.append(
                    BaselineFinding(
                        category="extension_points",
                        title="Unbounded TCP readexactly without a max size",
                        severity="medium",
                        target=f"{rel}:{lineno}",
                        description=(
                            "asyncio StreamReader.readexactly (or equivalent) "
                            "has no application max-message bound "
                            f"({stripped[:200]}). A peer can force large "
                            "allocations or stall the server."
                        ),
                        evidence=stripped[:500],
                        cwe="CWE-400",
                        remediation_steps=(
                            "Enforce max_message_size before readexactly, and "
                            "close the connection when the peer exceeds it."
                        ),
                    )
                )
            if _UNQUOTED_API_PATH_RE.search(line) and "quote(" not in line:
                findings.append(
                    _extension_finding(
                        title="URL path segment interpolated without encoding",
                        severity="medium",
                        target=f"{rel}:{lineno}",
                        description=(
                            "A dynamic path segment is interpolated into an API "
                            f"URL without encoding ({stripped[:200]}). Reserved "
                            "characters in the value can change the request path."
                        ),
                        evidence=stripped[:500],
                        cwe="CWE-20",
                        remediation_steps=(
                            "Percent-encode path segments with urllib.parse.quote "
                            "(safe='') before interpolation."
                        ),
                    )
                )
            if _EXC_LEAK_RE.search(line):
                findings.append(
                    _extension_finding(
                        title="Exception text returned to MCP/API clients",
                        severity="low",
                        target=f"{rel}:{lineno}",
                        description=(
                            "Raw exception strings are returned to the caller "
                            f"({stripped[:200]}). This leaks internals and can "
                            "include framework or filesystem details."
                        ),
                        evidence=stripped[:500],
                        cwe="CWE-209",
                        remediation_steps=(
                            "Return a stable error code to clients. Log the "
                            "exception server-side."
                        ),
                    )
                )
            if _AUDIT_DEF_RE.search(stripped):
                audit_defs.append((rel, lineno, stripped))
            elif _AUDIT_CALL_RE.search(line):
                audit_calls += 1
        findings.extend(_mcp_file_findings(rel, lines, file_text))
    if audit_defs and audit_calls == 0:
        rel, lineno, stripped = audit_defs[0]
        findings.append(
            BaselineFinding(
                category="extension_points",
                title="audit_tool_execution is defined but never called",
                severity="low",
                target=f"{rel}:{lineno}",
                description=(
                    "An audit helper exists but no call site invokes it, so "
                    "tool execution is not recorded. Destructive MCP tools "
                    "then have no forensic trail."
                ),
                evidence=stripped[:500],
                cwe="CWE-778",
                remediation_steps=(
                    "Call audit_tool_execution from the tool registry / "
                    "call_tool path on every invocation, including failures."
                ),
            )
        )
    result.raw_output["mcp_source"] = {
        "files_scanned": len(files),
        "hits": len(findings),
        "audit_defs": len(audit_defs),
        "audit_calls": audit_calls,
    }
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
    try:
        result.findings.extend(run_insecure_tls_baseline(source_paths, result, timeout))
    except Exception:
        logger.exception("baseline insecure-TLS scan failed unexpectedly")
    try:
        result.findings.extend(run_mcp_source_baseline(source_paths, result, timeout))
    except Exception:
        logger.exception("baseline MCP-source scan failed unexpectedly")

    logger.info(
        "Baseline scan complete: %s (skipped: %s)",
        result.counts_by_category(),
        list(result.skipped_tools),
    )
    return result
