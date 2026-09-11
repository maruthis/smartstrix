"""Tests for the Tier 3 deterministic baseline scan
(strix/scan/baseline.py) — see docs/scan-coverage-tier3-plan.md."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from strix.scan import baseline


if TYPE_CHECKING:
    import pytest


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["x"], returncode=returncode, stdout=stdout, stderr="")


# --------------------------------------------------------------------------
# Dependency baseline (trivy)
# --------------------------------------------------------------------------


def test_dependency_baseline_parses_trivy_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(baseline.shutil, "which", lambda _name: "/usr/bin/trivy")
    trivy_json = {
        "Results": [
            {
                "Target": "package-lock.json",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2024-1234",
                        "PkgName": "left-pad",
                        "InstalledVersion": "1.0.0",
                        "FixedVersion": "1.0.1",
                        "Severity": "HIGH",
                        "Title": "Prototype pollution",
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(
        baseline.subprocess, "run", lambda *_a, **_k: _completed(json.dumps(trivy_json))
    )

    result = baseline.BaselineResult()
    findings = baseline.run_dependency_baseline([str(tmp_path)], result)

    assert len(findings) == 1
    f = findings[0]
    assert f.category == "dependencies"
    assert f.cve == "CVE-2024-1234"
    assert f.severity == "high"
    assert f.dependency_metadata is not None
    assert f.dependency_metadata["package_name"] == "left-pad"
    assert f.dependency_metadata["fixed_version"] == "1.0.1"
    assert "trivy" in result.raw_output


def test_dependency_baseline_skips_gracefully_when_trivy_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(baseline.shutil, "which", lambda _name: None)
    result = baseline.BaselineResult()
    findings = baseline.run_dependency_baseline([str(tmp_path)], result)

    assert findings == []
    assert result.skipped_tools["trivy"] == "binary not found"


def test_dependency_baseline_handles_unparseable_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(baseline.shutil, "which", lambda _name: "/usr/bin/trivy")
    monkeypatch.setattr(baseline.subprocess, "run", lambda *_a, **_k: _completed("not json"))

    result = baseline.BaselineResult()
    findings = baseline.run_dependency_baseline([str(tmp_path)], result)

    assert findings == []


# --------------------------------------------------------------------------
# Secret baseline (gitleaks)
# --------------------------------------------------------------------------


def test_secret_baseline_skips_non_git_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(baseline.shutil, "which", lambda _name: "/usr/bin/gitleaks")
    result = baseline.BaselineResult()

    findings = baseline.run_secret_baseline([str(tmp_path)], result)

    assert findings == []


def test_secret_baseline_parses_gitleaks_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(baseline.shutil, "which", lambda _name: "/usr/bin/gitleaks")

    leaks = [
        {
            "RuleID": "aws-access-key",
            "File": "config/settings.py",
            "Commit": "abc123def456",
            "Match": "AKIA...",
        }
    ]

    def _fake_run(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        report_path = Path(cmd[cmd.index("--report-path") + 1])
        report_path.write_text(json.dumps(leaks), encoding="utf-8")
        return _completed()

    monkeypatch.setattr(baseline.subprocess, "run", _fake_run)

    result = baseline.BaselineResult()
    findings = baseline.run_secret_baseline([str(repo)], result)

    assert len(findings) == 1
    f = findings[0]
    assert f.category == "secrets"
    assert f.severity == "high"
    assert "config/settings.py" in f.title
    assert "abc123def456" in (f.description or "")


def test_secret_baseline_skips_gracefully_when_gitleaks_missing(tmp_path: Path) -> None:
    result = baseline.BaselineResult()
    findings = baseline.run_secret_baseline([str(tmp_path)], result)

    assert findings == []
    assert result.skipped_tools["gitleaks"] == "binary not found"


# --------------------------------------------------------------------------
# IaC baseline (kube-linter)
# --------------------------------------------------------------------------


def test_iac_baseline_parses_kube_linter_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(baseline.shutil, "which", lambda _name: "/usr/bin/kube-linter")
    kube_json = {
        "Reports": [
            {
                "Check": "privileged-container",
                "Diagnostic": {"Message": "container allows privilege escalation"},
                "Object": {"K8sObject": {"Name": "web-deployment"}},
            }
        ]
    }
    monkeypatch.setattr(
        baseline.subprocess, "run", lambda *_a, **_k: _completed(json.dumps(kube_json))
    )

    result = baseline.BaselineResult()
    findings = baseline.run_iac_baseline([str(tmp_path)], result)

    assert len(findings) == 1
    f = findings[0]
    assert f.category == "infrastructure"
    assert "privileged-container" in f.title
    assert "web-deployment" in f.title


def test_iac_baseline_skips_gracefully_when_kube_linter_missing(tmp_path: Path) -> None:
    result = baseline.BaselineResult()
    findings = baseline.run_iac_baseline([str(tmp_path)], result)

    assert findings == []
    assert result.skipped_tools["kube-linter"] == "binary not found"


# --------------------------------------------------------------------------
# run_baseline_scan orchestration
# --------------------------------------------------------------------------


def test_run_baseline_scan_with_no_local_sources_is_a_noop() -> None:
    result = baseline.run_baseline_scan([])

    assert result.findings == []
    assert result.counts_by_category() == {}


def test_run_baseline_scan_never_raises_when_a_category_crashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> list[baseline.BaselineFinding]:
        raise RuntimeError("tool exploded")

    monkeypatch.setattr(baseline, "run_dependency_baseline", _boom)
    monkeypatch.setattr(baseline, "run_secret_baseline", lambda *_a, **_k: [])
    monkeypatch.setattr(baseline, "run_iac_baseline", lambda *_a, **_k: [])
    monkeypatch.setattr(baseline, "run_insecure_tls_baseline", lambda *_a, **_k: [])
    monkeypatch.setattr(baseline, "run_mcp_source_baseline", lambda *_a, **_k: [])

    result = baseline.run_baseline_scan([{"source_path": str(tmp_path)}])

    assert result.findings == []


def test_run_baseline_scan_aggregates_across_categories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dep_finding = baseline.BaselineFinding(
        category="dependencies", title="dep", severity="high", target="x"
    )
    secret_finding = baseline.BaselineFinding(
        category="secrets", title="secret", severity="high", target="y"
    )
    monkeypatch.setattr(baseline, "run_dependency_baseline", lambda *_a, **_k: [dep_finding])
    monkeypatch.setattr(baseline, "run_secret_baseline", lambda *_a, **_k: [secret_finding])
    monkeypatch.setattr(baseline, "run_iac_baseline", lambda *_a, **_k: [])
    monkeypatch.setattr(baseline, "run_insecure_tls_baseline", lambda *_a, **_k: [])
    monkeypatch.setattr(baseline, "run_mcp_source_baseline", lambda *_a, **_k: [])

    result = baseline.run_baseline_scan([{"source_path": str(tmp_path)}])

    assert result.counts_by_category() == {"dependencies": 1, "secrets": 1}
    assert "1 dependency CVE" in result.summary_text()
    assert "1 secret" in result.summary_text()


def test_insecure_tls_baseline_flags_hardcoded_ssl_false(tmp_path: Path) -> None:
    client = tmp_path / "app" / "client.py"
    client.parent.mkdir()
    client.write_text("self._connector = aiohttp.TCPConnector(ssl=False)\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_client.py").write_text("ssl=False\n")

    result = baseline.BaselineResult()
    findings = baseline.run_insecure_tls_baseline([str(tmp_path)], result)

    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert "client.py:1" in findings[0].target
    assert findings[0].cwe == "CWE-295"


def test_insecure_tls_baseline_ignores_comments(tmp_path: Path) -> None:
    (tmp_path / "client.py").write_text("# ssl=False is bad, do not copy\n")
    result = baseline.BaselineResult()
    assert baseline.run_insecure_tls_baseline([str(tmp_path)], result) == []


def test_insecure_tls_baseline_skips_vendored_site_packages(tmp_path: Path) -> None:
    client = tmp_path / "app" / "integrations" / "gitlab" / "client.py"
    client.parent.mkdir(parents=True)
    client.write_text("session = requests.Session(); session.verify = False\n")

    vendored = (
        tmp_path
        / "Gitlab-mcpserver"
        / "lib"
        / "python3.11"
        / "site-packages"
        / "urllib3"
        / "connection.py"
    )
    vendored.parent.mkdir(parents=True)
    vendored.write_text("context.verify_mode = ssl.CERT_NONE\nssl=False\n")

    result = baseline.BaselineResult()
    findings = baseline.run_insecure_tls_baseline([str(tmp_path)], result)

    assert len(findings) == 1
    assert "client.py" in findings[0].target
    assert "site-packages" not in findings[0].target


def test_mcp_source_baseline_flags_bind_headers_readexactly_and_unwired_audit(
    tmp_path: Path,
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "run.py").write_text('uvicorn.run(app, host="0.0.0.0", port=8001)\n')
    (app / "stateless_handler.py").write_text(
        'logger.warning("incoming headers %s", request.headers)\n'
    )
    (app / "tcp.py").write_text("payload = await reader.readexactly(n)\n")
    (app / "registry.py").write_text(
        "def audit_tool_execution(name, args):\n    return None\n\n"
        "def call_tool(name, args):\n    return tools[name](args)\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_run.py").write_text('host="0.0.0.0"\n')

    result = baseline.BaselineResult()
    findings = baseline.run_mcp_source_baseline([str(tmp_path)], result)
    titles = {f.title for f in findings}

    assert "Service binds on all interfaces (0.0.0.0 / ::)" in titles
    assert "HTTP request headers logged at runtime" in titles
    assert "Unbounded TCP readexactly without a max size" in titles
    assert "audit_tool_execution is defined but never called" in titles
    assert all("tests/" not in f.target for f in findings)


def test_mcp_source_baseline_flags_remaining_vapt_classes(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "server.py").write_text(
        "async def handle_mcp_post(request):\n"
        "    result = await self.handle_jsonrpc_request(payload)\n"
        "    return {'error': str(exc)}\n"
    )
    (app / "register.py").write_text(
        "class DeleteProjectTool:\n"
        "    def __init__(self):\n"
        "        self.name = 'delete_project'\n"
        "        self.input_schema = {}\n"
    )
    (app / "client.py").write_text(
        'url = f"{base}/projects/{project_id}/repository/files/{path}"\n'
    )

    result = baseline.BaselineResult()
    findings = baseline.run_mcp_source_baseline([str(tmp_path)], result)
    titles = {f.title for f in findings}

    assert "MCP HTTP transport has no endpoint authentication" in titles
    assert "MCP HTTP handler has no rate limiting" in titles
    assert "Destructive MCP tools have no approval gate" in titles
    assert "URL path segment interpolated without encoding" in titles
    assert "Exception text returned to MCP/API clients" in titles


def test_mcp_source_baseline_skips_wired_audit(tmp_path: Path) -> None:
    (tmp_path / "registry.py").write_text(
        "def audit_tool_execution(name, args):\n    return None\n\n"
        "def call_tool(name, args):\n    audit_tool_execution(name, args)\n"
    )
    result = baseline.BaselineResult()
    findings = baseline.run_mcp_source_baseline([str(tmp_path)], result)
    assert all("audit_tool_execution" not in f.title for f in findings)
