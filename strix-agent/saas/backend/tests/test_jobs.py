import asyncio
import json
import os
import sys
import types
import uuid
from pathlib import Path

import pytest

from app import crypto, jobs, models
from app.db import SessionLocal


def _make_org_and_repo(db):
    org = models.Organization(name="JobsCo")
    db.add(org)
    db.flush()
    repo = models.Repository(org_id=org.id, full_name="jobsco/widgets")
    db.add(repo)
    db.commit()
    return org, repo


def _make_pentest(db, org, repo):
    pentest = models.Pentest(org_id=org.id, target_type="repository", target_id=repo.id, target_label=repo.full_name)
    db.add(pentest)
    db.commit()
    db.refresh(pentest)
    return pentest


async def test_enqueue_without_worker_raises():
    # Module-level _queue is reset to None on every lifespan shutdown (see
    # jobs.stop_worker) and starts as None on import, so as long as no
    # TestClient fixture is active in this test, it should still be unset.
    assert jobs._queue is None
    with pytest.raises(RuntimeError, match="job queue not started"):
        await jobs.enqueue_pentest("some-id")


async def test_run_pentest_missing_row_is_a_noop():
    # Covers `_run_pentest`'s early-return branch when the pentest row
    # doesn't exist (e.g. deleted between enqueue and dequeue).
    await jobs._run_pentest("does-not-exist")  # must not raise


async def test_run_pentest_marks_failed_on_scan_exception(monkeypatch):
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest_id = pentest.id
    finally:
        db.close()

    async def _boom(_db, _pentest, _llm_settings):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(jobs, "_scan", _boom)
    await jobs._run_pentest(pentest_id)

    db = SessionLocal()
    try:
        reloaded = db.get(models.Pentest, pentest_id)
        assert reloaded.status == "failed"
        assert reloaded.finished_at is not None
    finally:
        db.close()


async def test_run_pentest_marks_failed_when_finding_processing_raises(monkeypatch):
    """Regression test: the try/except used to only wrap the _scan() call,
    not the loop that turns findings into Issue rows. A successful scan
    that returns a malformed finding (missing an expected key) would then
    raise past _run_pentest uncaught, leaving the pentest stuck in
    "running" forever — see saas/TASKS.md and jobs.py's comment on this."""
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest_id = pentest.id
    finally:
        db.close()

    async def _scan_returns_malformed_finding(_db, _pentest, _llm_settings):
        return [{"severity": "critical"}]  # missing title/description/etc.

    monkeypatch.setattr(jobs, "_scan", _scan_returns_malformed_finding)
    await jobs._run_pentest(pentest_id)

    db = SessionLocal()
    try:
        reloaded = db.get(models.Pentest, pentest_id)
        assert reloaded.status == "failed"
        assert reloaded.finished_at is not None
        # No partial Issue rows from the failed attempt were committed.
        assert db.query(models.Issue).filter_by(pentest_id=pentest_id).count() == 0
    finally:
        db.close()


async def test_run_pentest_tolerates_unexpected_severity_value(monkeypatch):
    """A finding with a severity outside the usual 4 buckets should not
    crash the whole pentest — it's counted under its own key instead."""
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest_id = pentest.id
    finally:
        db.close()

    finding = {
        "title": "Weird finding",
        "description": "",
        "severity": "informational",
        "cvss": None,
        "cvss_breakdown": {},
        "technical_analysis": "",
        "remediation_steps": "",
        "poc_description": "",
        "target": "x",
        "endpoint": "",
        "fix_effort": "low",
    }

    async def _scan_returns_odd_severity(_db, _pentest, _llm_settings):
        return [finding]

    monkeypatch.setattr(jobs, "_scan", _scan_returns_odd_severity)
    await jobs._run_pentest(pentest_id)

    db = SessionLocal()
    try:
        reloaded = db.get(models.Pentest, pentest_id)
        assert reloaded.status == "completed"
        assert reloaded.severity_counts["informational"] == 1
    finally:
        db.close()


async def test_run_pentest_success_updates_repo_last_tested():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest_id, repo_id = pentest.id, repo.id
    finally:
        db.close()

    await jobs._run_pentest(pentest_id)

    db = SessionLocal()
    try:
        reloaded = db.get(models.Pentest, pentest_id)
        assert reloaded.status == "completed"
        reloaded_repo = db.get(models.Repository, repo_id)
        assert reloaded_repo.last_tested_at is not None
    finally:
        db.close()


async def test_scan_falls_back_to_mock_when_real_scan_unavailable():
    db = SessionLocal()
    try:
        jobs.settings.enable_real_scan = True
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)

        # No GitHub/GitLab credential is connected and the repo doesn't
        # exist, so _run_real_scan's clone step raises and _scan should
        # fall back to the mock scanner rather than propagating that.
        findings = await jobs._scan(db, pentest, None)
        assert isinstance(findings, list)

        # The fallback must be visible, not indistinguishable from a
        # genuine result: the pentest records why, and every finding it
        # filed is tagged.
        assert pentest.mock_fallback_reason
        assert all(f["source"] == "mock_fallback" for f in findings)
    finally:
        jobs.settings.enable_real_scan = False
        db.close()


async def test_scan_does_not_tag_findings_when_real_scan_disabled():
    """The *intended* mock scanner (SAAS_ENABLE_REAL_SCAN unset/false) is
    not a fallback and must not be tagged as one."""
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)

        findings = await jobs._scan(db, pentest, None)

        assert pentest.mock_fallback_reason is None
        assert all(f.get("source") is None for f in findings)
    finally:
        db.close()


async def test_run_real_scan_redacts_credential_from_clone_failure(monkeypatch):
    """A failed clone must never leak the org's live PAT into the
    exception message that _scan()'s except-block logs."""

    def _boom_clone_repository(url, run_name, dest_name, ref):
        raise ValueError("Could not clone repository https://x-access-token:sekrit-token@github.com/acme/widgets.git: fatal error")

    async def _unreachable_run_strix_scan(**kwargs):
        raise AssertionError("run_strix_scan must not be reached when the clone step fails")

    _install_fake_strix_module(monkeypatch, _unreachable_run_strix_scan, clone_repository=_boom_clone_repository)

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)

        with pytest.raises(RuntimeError) as excinfo:
            await jobs._run_real_scan(db, pentest, None)

        assert "sekrit-token" not in str(excinfo.value)
        assert "***" in str(excinfo.value)
    finally:
        db.close()


def _install_fake_strix_module(monkeypatch, run_strix_scan, *, run_dir=None, clone_repository=None):
    fake_strix = types.ModuleType("strix")

    fake_runner = types.ModuleType("strix.core.runner")
    fake_runner.run_strix_scan = run_strix_scan
    fake_paths = types.ModuleType("strix.core.paths")
    fake_paths.run_dir_for = (lambda name: run_dir) if run_dir is not None else (lambda name: Path("/nonexistent-run-dir-for-tests"))
    fake_paths.run_record_path = lambda path: path / "run.json"
    fake_core = types.ModuleType("strix.core")
    fake_core.runner = fake_runner
    fake_core.paths = fake_paths
    fake_strix.core = fake_core

    fake_loader = types.ModuleType("strix.config.loader")
    fake_loader._cached = "some-cached-settings-object"
    fake_settings_obj = types.SimpleNamespace(runtime=types.SimpleNamespace(image="ghcr.io/usestrix/strix-sandbox:1.3.0"))
    fake_config = types.ModuleType("strix.config")
    fake_config.loader = fake_loader
    fake_config.load_settings = lambda: fake_settings_obj
    fake_strix.config = fake_config

    fake_utils = types.ModuleType("strix.interface.utils")
    fake_utils.clone_repository = clone_repository or (
        lambda url, run_name, dest_name, ref: (f"/tmp/fake-clone/{run_name}", "fake-resolved-sha")
    )
    fake_interface = types.ModuleType("strix.interface")
    fake_interface.utils = fake_utils
    fake_strix.interface = fake_interface

    monkeypatch.setitem(sys.modules, "strix", fake_strix)
    monkeypatch.setitem(sys.modules, "strix.core", fake_core)
    monkeypatch.setitem(sys.modules, "strix.core.runner", fake_runner)
    monkeypatch.setitem(sys.modules, "strix.core.paths", fake_paths)
    monkeypatch.setitem(sys.modules, "strix.config", fake_config)
    monkeypatch.setitem(sys.modules, "strix.config.loader", fake_loader)
    monkeypatch.setitem(sys.modules, "strix.interface", fake_interface)
    monkeypatch.setitem(sys.modules, "strix.interface.utils", fake_utils)
    return fake_loader


async def test_run_real_scan_success_path(monkeypatch):
    """Injects a fake `strix` package so _run_real_scan's imports succeed,
    covering the path that isn't reachable without the optional real-scan
    dependency actually installed. No vulnerabilities.json is written, so
    the result is an empty finding list — a legitimate "scan ran, found
    nothing" outcome, not a failure."""
    calls = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        calls["scan_config"] = scan_config
        calls["scan_id"] = scan_id
        calls["image"] = image
        calls["local_sources"] = local_sources

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, clone_repository=lambda url, run_name, dest_name, ref: (f"/tmp/cloned/{run_name}", "fake-sha"))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
    finally:
        db.close()

    result = await jobs._run_real_scan(db, pentest, None)
    assert result == []
    assert calls["scan_id"] == pentest.id
    assert calls["scan_config"]["run_name"] == pentest.id
    assert calls["image"] == "ghcr.io/usestrix/strix-sandbox:1.3.0"
    assert calls["scan_config"]["targets"] == [
        {
            "type": "repository",
            "details": {"target_repo": "jobsco/widgets", "cloned_repo_path": f"/tmp/cloned/{pentest.id}", "workspace_subdir": "widgets"},
        }
    ]
    assert calls["local_sources"] == [{"source_path": f"/tmp/cloned/{pentest.id}", "workspace_subdir": "widgets", "protect_metadata": False}]
    assert calls["scan_config"]["skills"] == ["standards/owasp_top_10"]


async def test_run_real_scan_domain_target_has_no_local_sources(monkeypatch):
    calls = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        calls["scan_config"] = scan_config
        calls["local_sources"] = local_sources

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan)

    db = SessionLocal()
    try:
        org = models.Organization(name="DomainCo")
        db.add(org)
        db.flush()
        domain = models.Domain(org_id=org.id, hostname="app.example.com")
        db.add(domain)
        db.commit()
        pentest = models.Pentest(org_id=org.id, target_type="domain", target_id=domain.id, target_label=domain.hostname)
        db.add(pentest)
        db.commit()
        db.refresh(pentest)
    finally:
        db.close()

    result = await jobs._run_real_scan(db, pentest, None)
    assert result == []
    assert calls["local_sources"] == []
    assert calls["scan_config"]["targets"] == [{"type": "web_application", "details": {"target_url": "https://app.example.com"}}]


async def test_run_real_scan_legacy_full_url_hostname_is_a_single_https_target(monkeypatch):
    """A Domain.hostname that already includes a scheme and path must not be
    prefixed into ``https://https://...`` — that made live extra-domain
    scans miss the real site."""
    calls = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        calls["scan_config"] = scan_config

    _install_fake_strix_module(
        monkeypatch,
        fake_run_strix_scan,
        clone_repository=lambda url, run_name, dest_name, ref: (f"/tmp/cloned/{run_name}", "fake-sha"),
    )

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        domain = models.Domain(
            org_id=org.id,
            hostname="https://https://api-dev.example.com/api/openproject",
            verified=True,
        )
        db.add(domain)
        db.commit()
        pentest = models.Pentest(
            org_id=org.id,
            target_type="repository",
            target_id=repo.id,
            target_label=repo.full_name,
            extra_domain_id=domain.id,
        )
        db.add(pentest)
        db.commit()
        db.refresh(pentest)
    finally:
        db.close()

    result = await jobs._run_real_scan(db, pentest, None)
    assert result == []
    assert calls["scan_config"]["targets"][1] == {
        "type": "web_application",
        "details": {"target_url": "https://api-dev.example.com/api/openproject"},
    }


async def test_run_real_scan_qualifies_persisted_standard_skills(monkeypatch):
    calls = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        calls["scan_config"] = scan_config

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, clone_repository=lambda url, run_name, dest_name, ref: (f"/tmp/cloned/{run_name}", "fake-sha"))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest.skills = ["owasp_top_10", "pci_dss"]
        db.commit()
        db.refresh(pentest)
    finally:
        db.close()

    await jobs._run_real_scan(db, pentest, None)
    assert calls["scan_config"]["skills"] == ["standards/owasp_top_10", "standards/pci_dss"]


async def test_run_real_scan_falls_back_to_owasp_when_skills_are_unknown(monkeypatch):
    calls = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        calls["scan_config"] = scan_config

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, clone_repository=lambda url, run_name, dest_name, ref: (f"/tmp/cloned/{run_name}", "fake-sha"))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest.skills = ["not_a_standard"]
        db.commit()
        db.refresh(pentest)
    finally:
        db.close()

    await jobs._run_real_scan(db, pentest, None)
    assert calls["scan_config"]["skills"] == ["standards/owasp_top_10"]


async def test_run_real_scan_reads_and_translates_real_findings(monkeypatch, tmp_path):
    """The real end-to-end shape: run_strix_scan writes vulnerabilities.json
    (as ReportState does — many fields only present when truthy, see
    strix/report/state.py), and _run_real_scan must read it back and fill
    in the same defaults MOCK_FINDINGS always has, so _run_pentest's
    Issue-creation loop doesn't need a real-vs-mock branch."""
    raw_findings = [
        {"title": "SQL injection in login", "severity": "Critical", "cvss": 9.8},
        {"title": "Missing field defaults", "severity": "low", "description": "d", "endpoint": "/e", "fix_effort": "high"},
    ]
    (tmp_path / "vulnerabilities.json").write_text(json.dumps(raw_findings), encoding="utf-8")

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, run_dir=tmp_path)

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest_id = pentest.id
    finally:
        db.close()

    result = await jobs._run_real_scan(db, pentest, None)
    assert result == [
        {
            "title": "SQL injection in login",
            "description": "",
            "severity": "critical",
            "cvss": 9.8,
            "cvss_breakdown": {},
            "technical_analysis": "",
            "remediation_steps": "",
            "poc_description": "",
            "target": "",
            "endpoint": "",
            "fix_effort": "medium",
            "source": None,
        },
        {
            "title": "Missing field defaults",
            "description": "d",
            "severity": "low",
            "cvss": None,
            "cvss_breakdown": {},
            "technical_analysis": "",
            "remediation_steps": "",
            "poc_description": "",
            "target": "",
            "endpoint": "/e",
            "fix_effort": "high",
            "source": None,
        },
    ]


async def test_run_real_scan_applies_and_restores_org_llm_env(monkeypatch):
    """With an OrgLlmSettings row configured, the org's model/key/base
    should be visible as env vars *during* the call, strix's settings
    cache should be invalidated, and everything should be restored
    afterward so the next scan doesn't inherit stale values."""
    seen_env = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        seen_env["STRIX_LLM"] = os.environ.get("STRIX_LLM")
        seen_env["LLM_API_KEY"] = os.environ.get("LLM_API_KEY")
        seen_env["LLM_API_BASE"] = os.environ.get("LLM_API_BASE")

    fake_loader = _install_fake_strix_module(monkeypatch, fake_run_strix_scan)

    monkeypatch.setenv("STRIX_LLM", "openai/previous-model")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        llm_settings = models.OrgLlmSettings(org_id=org.id, model="openai/gpt-5.4", api_key="sk-test-123", api_base="https://gateway.example.com/v1")
        db.add(llm_settings)
        db.commit()
        db.refresh(llm_settings)
        db.refresh(pentest)
    finally:
        db.close()

    result = await jobs._run_real_scan(db, pentest, llm_settings)

    assert result == []
    assert seen_env == {
        "STRIX_LLM": "openai/gpt-5.4",
        "LLM_API_KEY": "sk-test-123",
        "LLM_API_BASE": "https://gateway.example.com/v1",
    }
    # Cache was invalidated at least once during the override.
    assert fake_loader._cached is None
    # Previous process env is restored afterward.
    assert os.environ.get("STRIX_LLM") == "openai/previous-model"
    assert os.environ.get("LLM_API_KEY") is None
    assert os.environ.get("LLM_API_BASE") is None


async def test_run_real_scan_without_org_api_base_clears_inherited_process_value(monkeypatch):
    """If the org configures a model but no api_base, and the process
    happens to have LLM_API_BASE set (e.g. a previous org's scan, or a
    global default), it must not leak into this org's scan."""
    seen_env = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        seen_env["LLM_API_BASE"] = os.environ.get("LLM_API_BASE")

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan)
    monkeypatch.setenv("LLM_API_BASE", "http://leftover-from-someone-else:1234/v1")

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        llm_settings = models.OrgLlmSettings(org_id=org.id, model="openai/gpt-5.4")
        db.add(llm_settings)
        db.commit()
        db.refresh(llm_settings)
        db.refresh(pentest)
    finally:
        db.close()

    await jobs._run_real_scan(db, pentest, llm_settings)
    assert seen_env["LLM_API_BASE"] is None
    # Restored afterward (it existed before, so it comes back).
    assert os.environ.get("LLM_API_BASE") == "http://leftover-from-someone-else:1234/v1"


async def test_run_real_scan_without_org_settings_leaves_env_untouched(monkeypatch):
    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan)
    monkeypatch.setenv("STRIX_LLM", "openai/process-default")

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
    finally:
        db.close()

    await jobs._run_real_scan(db, pentest, None)
    assert os.environ.get("STRIX_LLM") == "openai/process-default"


async def test_repo_clone_url_uses_connected_credential(monkeypatch):
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        db.add(models.Integration(org_id=org.id, provider="github", account_label="octocat", credential_encrypted=crypto.encrypt("ghp_secret")))
        db.commit()
        url = jobs._repo_clone_url(db, org.id, repo)
        assert url == "https://x-access-token:ghp_secret@github.com/jobsco/widgets.git"
    finally:
        db.close()


async def test_repo_clone_url_falls_back_to_unauthenticated_when_not_connected():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        url = jobs._repo_clone_url(db, org.id, repo)
        assert url == "https://github.com/jobsco/widgets.git"
    finally:
        db.close()


async def test_repo_clone_url_uses_gitlab_self_hosted_base_url():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        repo.provider = "gitlab"
        db.add(models.Integration(org_id=org.id, provider="gitlab", account_label="acme", base_url="https://gitlab.acme.internal", credential_encrypted=crypto.encrypt("glpat-secret")))
        db.commit()
        url = jobs._repo_clone_url(db, org.id, repo)
        assert url == "https://oauth2:glpat-secret@gitlab.acme.internal/jobsco/widgets.git"
    finally:
        db.close()


async def test_build_scan_targets_raises_for_missing_repository():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = models.Pentest(org_id=org.id, target_type="repository", target_id="does-not-exist", target_label="x")
        db.add(pentest)
        db.commit()
        db.refresh(pentest)
        with pytest.raises(RuntimeError, match="not found"):
            await jobs._build_scan_targets(db, pentest)
    finally:
        db.close()


async def test_build_scan_targets_raises_for_missing_domain():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = models.Pentest(org_id=org.id, target_type="domain", target_id="does-not-exist", target_label="x")
        db.add(pentest)
        db.commit()
        db.refresh(pentest)
        with pytest.raises(RuntimeError, match="not found"):
            await jobs._build_scan_targets(db, pentest)
    finally:
        db.close()


async def test_build_scan_targets_raises_for_unsupported_target_type():
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = models.Pentest(org_id=org.id, target_type="something-else", target_id="x", target_label="x")
        db.add(pentest)
        db.commit()
        db.refresh(pentest)
        with pytest.raises(RuntimeError, match="unsupported"):
            await jobs._build_scan_targets(db, pentest)
    finally:
        db.close()


async def test_run_real_scan_treats_non_list_vulnerabilities_json_as_no_findings(monkeypatch, tmp_path):
    (tmp_path / "vulnerabilities.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, run_dir=tmp_path)

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
    finally:
        db.close()

    assert await jobs._run_real_scan(db, pentest, None) == []


async def test_run_pentest_end_to_end_with_real_scan_creates_issues_from_translated_findings(monkeypatch, tmp_path):
    """Proves the full pipeline: a real (faked) engine run's
    vulnerabilities.json becomes real Issue rows tied to the selected
    repository, exactly like the mock path already does."""
    (tmp_path / "vulnerabilities.json").write_text(
        json.dumps(
            [
                {
                    "title": "Real finding from the engine",
                    "severity": "high",
                    "cvss": 7.5,
                    "source": "baseline_scan",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "run.json").write_text(
        json.dumps({"llm_usage": {"input_tokens": 1200, "output_tokens": 345, "total_tokens": 1545}}),
        encoding="utf-8",
    )

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    _install_fake_strix_module(
        monkeypatch,
        fake_run_strix_scan,
        run_dir=tmp_path,
        clone_repository=lambda url, run_name, dest_name, ref: (str(tmp_path), "fake-sha"),
    )
    monkeypatch.setattr(jobs.settings, "enable_real_scan", True)

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest_id, repo_id = pentest.id, repo.id
    finally:
        db.close()

    await jobs._run_pentest(pentest_id)

    db = SessionLocal()
    try:
        reloaded = db.get(models.Pentest, pentest_id)
        assert reloaded.status == "completed"
        issues = db.query(models.Issue).filter_by(pentest_id=pentest_id).all()
        assert len(issues) == 1
        assert issues[0].title == "Real finding from the engine"
        assert issues[0].repository_id == repo_id
        assert issues[0].severity == "high"
        assert issues[0].source == "baseline_scan"
        assert reloaded.llm_input_tokens == 1200
        assert reloaded.llm_output_tokens == 345
        assert reloaded.llm_total_tokens == 1545
        audit = db.query(models.AuditLogEntry).filter_by(org_id=reloaded.org_id, action="pentest.completed").one()
        assert audit.extra["llm_usage"] == {"input_tokens": 1200, "output_tokens": 345, "total_tokens": 1545}
    finally:
        db.close()


async def test_run_pentest_mock_findings_have_no_source(monkeypatch):
    """MOCK_FINDINGS entries carry no "source" key at all — the Issue-creation
    loop must default that to None rather than KeyError."""
    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        pentest = _make_pentest(db, org, repo)
        pentest_id = pentest.id
    finally:
        db.close()

    await jobs._run_pentest(pentest_id)

    db = SessionLocal()
    try:
        issues = db.query(models.Issue).filter_by(pentest_id=pentest_id).all()
        assert issues
        assert all(issue.source is None for issue in issues)
    finally:
        db.close()


async def test_worker_loop_logs_and_continues_after_a_bad_job(monkeypatch):
    """Covers the outer try/except in _worker_loop: a job that raises must
    not kill the worker task, and subsequent jobs still get processed."""
    await jobs.start_worker()
    try:
        seen = []

        async def _flaky(pentest_id):
            if not seen:
                seen.append(pentest_id)
                raise RuntimeError("boom")
            seen.append(pentest_id)

        monkeypatch.setattr(jobs, "_run_pentest", _flaky)

        await jobs.enqueue_pentest(str(uuid.uuid4()))
        await jobs.enqueue_pentest(str(uuid.uuid4()))

        for _ in range(50):
            if len(seen) == 2:
                break
            await asyncio.sleep(0.01)
        assert len(seen) == 2
    finally:
        await jobs.stop_worker()
