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

    result = baseline.run_baseline_scan([{"source_path": str(tmp_path)}])

    assert result.counts_by_category() == {"dependencies": 1, "secrets": 1}
    assert "1 dependency CVE" in result.summary_text()
    assert "1 secret" in result.summary_text()
