"""Tests for the PR-review real-scan pipeline in app/jobs.py: cloning and
checking out the PR's head commit, diff-scoping the engine run against its
base branch, and finalizing the PRReview row. There is deliberately no
mock-scanner fallback here (see jobs.py's PR-review section docstring) —
a scan failure must land the review in status="failed", not silently
substitute canned findings."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from app import jobs, models
from app.db import SessionLocal


def _make_org_and_repo(db, name: str = "ReviewCo"):
    org = models.Organization(name=name)
    db.add(org)
    db.flush()
    repo = models.Repository(org_id=org.id, full_name=f"{name.lower()}/widgets", provider="github", default_branch="main")
    db.add(repo)
    db.commit()
    return org, repo


def _make_pr_review(db, org, repo, *, pr_number: int = 42, target_branch: str | None = "main"):
    review = models.PRReview(
        org_id=org.id, repository_id=repo.id, pr_number=pr_number, title="Add feature", author="octocat", target_branch=target_branch
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def _install_fake_strix_module(
    monkeypatch,
    run_strix_scan,
    *,
    run_dir=None,
    resolve_diff_scope_context=None,
):
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

    def _default_diff_scope(local_sources, scope_mode, diff_base, non_interactive, env=None):
        return types.SimpleNamespace(active=True, mode=scope_mode, metadata={"active": True, "mode": scope_mode, "diff_base": diff_base})

    fake_utils = types.ModuleType("strix.interface.utils")
    fake_utils.resolve_diff_scope_context = resolve_diff_scope_context or _default_diff_scope
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


# --------------------------------------------------------------------------
# _pr_ref_spec
# --------------------------------------------------------------------------


def test_pr_ref_spec_github():
    assert jobs._pr_ref_spec("github", 42) == "refs/pull/42/head"


def test_pr_ref_spec_gitlab():
    assert jobs._pr_ref_spec("gitlab", 7) == "refs/merge-requests/7/head"


# --------------------------------------------------------------------------
# _clone_and_checkout_pr
# --------------------------------------------------------------------------


def test_clone_and_checkout_pr_runs_clone_fetch_checkout_in_order(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, capture_output, text, check):  # noqa: ANN001
        calls.append(args)
        if "rev-parse" in args:
            return subprocess.CompletedProcess(args, 0, stdout="deadbeef\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(jobs.subprocess, "run", fake_run)
    monkeypatch.setattr(jobs.tempfile, "gettempdir", lambda: str(tmp_path))

    clone_path, resolved_sha = jobs._clone_and_checkout_pr("https://github.com/acme/widgets.git", "run-1", "github", 42)

    assert resolved_sha == "deadbeef"
    assert calls[0][1] == "clone"
    assert calls[1][3:6] == ["fetch", "origin", "refs/pull/42/head:pr-ref"]
    assert calls[2][3:5] == ["checkout", "pr-ref"]
    assert calls[3][3:5] == ["rev-parse", "HEAD"]
    assert clone_path.endswith("repo")


def test_clone_and_checkout_pr_uses_gitlab_merge_request_ref(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, capture_output, text, check):  # noqa: ANN001
        calls.append(args)
        if "rev-parse" in args:
            return subprocess.CompletedProcess(args, 0, stdout="cafefeed\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(jobs.subprocess, "run", fake_run)
    monkeypatch.setattr(jobs.tempfile, "gettempdir", lambda: str(tmp_path))

    jobs._clone_and_checkout_pr("https://gitlab.com/acme/widgets.git", "run-2", "gitlab", 7)
    assert calls[1][3:6] == ["fetch", "origin", "refs/merge-requests/7/head:pr-ref"]


def test_clone_and_checkout_pr_raises_a_clear_error_on_git_failure(monkeypatch, tmp_path):
    def fake_run(args, capture_output, text, check):  # noqa: ANN001
        raise subprocess.CalledProcessError(1, args, stderr="fatal: repository not found")

    monkeypatch.setattr(jobs.subprocess, "run", fake_run)
    monkeypatch.setattr(jobs.tempfile, "gettempdir", lambda: str(tmp_path))

    with pytest.raises(ValueError, match="repository not found"):
        jobs._clone_and_checkout_pr("https://github.com/acme/widgets.git", "run-3", "github", 42)


def test_clone_and_checkout_pr_raises_when_git_is_missing(monkeypatch):
    monkeypatch.setattr(jobs.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        jobs._clone_and_checkout_pr("https://github.com/acme/widgets.git", "run-4", "github", 42)


# --------------------------------------------------------------------------
# _pr_review_blocking_severities
# --------------------------------------------------------------------------


async def test_pr_review_blocking_severities_defaults_without_a_settings_row():
    db = SessionLocal()
    try:
        org, _repo = _make_org_and_repo(db)
        severities, blocking = jobs._pr_review_blocking_severities(db, org.id)
        assert severities == ["critical", "high"]
        assert blocking is True
    finally:
        db.close()


async def test_pr_review_blocking_severities_reads_the_configured_row():
    db = SessionLocal()
    try:
        org, _repo = _make_org_and_repo(db)
        db.add(models.PRReviewSettings(org_id=org.id, blocking_severities=["critical"], block_prs_on_findings=False))
        db.commit()
        severities, blocking = jobs._pr_review_blocking_severities(db, org.id)
        assert severities == ["critical"]
        assert blocking is False
    finally:
        db.close()


# --------------------------------------------------------------------------
# _run_real_pr_review_scan
# --------------------------------------------------------------------------


async def test_run_real_pr_review_scan_success_path(monkeypatch):
    calls: dict[str, Any] = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        calls["scan_config"] = scan_config
        calls["local_sources"] = local_sources

    diff_scope_calls: dict[str, Any] = {}

    def fake_resolve_diff_scope(local_sources, scope_mode, diff_base, non_interactive, env=None):
        diff_scope_calls["local_sources"] = local_sources
        diff_scope_calls["scope_mode"] = scope_mode
        diff_scope_calls["diff_base"] = diff_base
        return types.SimpleNamespace(active=True, mode=scope_mode, metadata={"active": True, "changed_files": 3})

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, resolve_diff_scope_context=fake_resolve_diff_scope)
    monkeypatch.setattr(jobs, "_clone_and_checkout_pr", lambda url, run_name, provider, pr_number: (f"/tmp/pr-clone/{run_name}", "resolved-sha"))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        review = _make_pr_review(db, org, repo, target_branch="main")

        result = await jobs._run_real_pr_review_scan(db, review, repo, None)

        assert result == []
        assert review.resolved_head_sha == "resolved-sha"
        assert diff_scope_calls["scope_mode"] == "diff"
        assert diff_scope_calls["diff_base"] == "origin/main"
        assert calls["scan_config"]["diff_scope"] == {"active": True, "changed_files": 3}
        assert calls["scan_config"]["scan_mode"] == "quick"
        assert calls["scan_config"]["targets"] == [
            {
                "type": "repository",
                "details": {"target_repo": repo.full_name, "cloned_repo_path": f"/tmp/pr-clone/{review.id}", "workspace_subdir": "widgets"},
            }
        ]
        assert calls["local_sources"] == [
            {"source_path": f"/tmp/pr-clone/{review.id}", "workspace_subdir": "widgets", "protect_metadata": False}
        ]
    finally:
        db.close()


async def test_run_real_pr_review_scan_falls_back_to_repo_default_branch(monkeypatch):
    diff_scope_calls: dict[str, Any] = {}

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    def fake_resolve_diff_scope(local_sources, scope_mode, diff_base, non_interactive, env=None):
        diff_scope_calls["diff_base"] = diff_base
        return types.SimpleNamespace(active=True, mode=scope_mode, metadata={"active": True})

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, resolve_diff_scope_context=fake_resolve_diff_scope)
    monkeypatch.setattr(jobs, "_clone_and_checkout_pr", lambda url, run_name, provider, pr_number: (f"/tmp/{run_name}", "sha"))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        review = _make_pr_review(db, org, repo, target_branch=None)  # no picker data
        await jobs._run_real_pr_review_scan(db, review, repo, None)
    finally:
        db.close()

    assert diff_scope_calls["diff_base"] == "origin/main"  # repo.default_branch


async def test_run_real_pr_review_scan_reads_and_translates_findings(monkeypatch, tmp_path):
    (tmp_path / "vulnerabilities.json").write_text('[{"title": "SQLi in search", "severity": "high", "cvss": 8.1}]', encoding="utf-8")

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, run_dir=tmp_path)
    monkeypatch.setattr(jobs, "_clone_and_checkout_pr", lambda url, run_name, provider, pr_number: (f"/tmp/{run_name}", "sha"))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        review = _make_pr_review(db, org, repo)
        result = await jobs._run_real_pr_review_scan(db, review, repo, None)
    finally:
        db.close()

    assert result == [
        {
            "title": "SQLi in search",
            "description": "",
            "severity": "high",
            "cvss": 8.1,
            "cvss_breakdown": {},
            "technical_analysis": "",
            "remediation_steps": "",
            "poc_description": "",
            "target": "",
            "endpoint": "",
            "fix_effort": "medium",
            "source": None,
        }
    ]


# --------------------------------------------------------------------------
# _run_pr_review_job
# --------------------------------------------------------------------------


async def test_run_pr_review_job_missing_review_is_a_noop():
    await jobs._run_pr_review_job("does-not-exist")  # must not raise


async def test_run_pr_review_job_missing_repository_marks_failed():
    db = SessionLocal()
    try:
        org = models.Organization(name="OrphanCo")
        db.add(org)
        db.flush()
        review = models.PRReview(org_id=org.id, repository_id="missing-repo-id", pr_number=1, title="x", author="a")
        db.add(review)
        db.commit()
        review_id = review.id
    finally:
        db.close()

    await jobs._run_pr_review_job(review_id)

    db = SessionLocal()
    try:
        refreshed = db.get(models.PRReview, review_id)
        assert refreshed.status == "failed"
        assert refreshed.error == "repository_not_found"
    finally:
        db.close()


async def test_run_pr_review_job_success_path_files_issues_and_sets_status(monkeypatch, tmp_path):
    (tmp_path / "vulnerabilities.json").write_text(
        '[{"title": "Critical bug", "severity": "critical", "cvss": 9.5}]', encoding="utf-8"
    )

    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, run_dir=tmp_path)
    monkeypatch.setattr(jobs, "_clone_and_checkout_pr", lambda url, run_name, provider, pr_number: (f"/tmp/{run_name}", "sha123"))

    calls = {}
    fake_provider = types.SimpleNamespace(create_check_run=lambda **kwargs: calls.setdefault("check_run", kwargs))
    # get_github_provider is imported inline inside _run_pr_review_job, at
    # call time — patch the module it's imported from.
    import app.providers as providers_module

    monkeypatch.setattr(providers_module, "get_github_provider", lambda: fake_provider)

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        db.add(models.PRReviewSettings(org_id=org.id, blocking_severities=["critical", "high"], block_prs_on_findings=True))
        db.commit()
        review = _make_pr_review(db, org, repo)
        review_id, org_id, repo_id = review.id, org.id, repo.id
    finally:
        db.close()

    await jobs._run_pr_review_job(review_id)

    db = SessionLocal()
    try:
        refreshed = db.get(models.PRReview, review_id)
        assert refreshed.status == "needs_attention"
        assert refreshed.findings_count == 1
        assert refreshed.resolved_head_sha == "sha123"

        issues = db.query(models.Issue).filter_by(pr_review_id=review_id).all()
        assert len(issues) == 1
        assert issues[0].title == "Critical bug"
        assert issues[0].repository_id == repo_id

        audit = db.query(models.AuditLogEntry).filter_by(org_id=org_id, action="pr_review.completed").one_or_none()
        assert audit is not None
    finally:
        db.close()

    assert calls["check_run"]["conclusion"] == "failure"


async def test_run_pr_review_job_scan_failure_marks_review_failed(monkeypatch):
    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        raise RuntimeError("engine exploded")

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan)
    monkeypatch.setattr(jobs, "_clone_and_checkout_pr", lambda url, run_name, provider, pr_number: (f"/tmp/{run_name}", "sha"))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        review = _make_pr_review(db, org, repo)
        review_id, org_id = review.id, org.id
    finally:
        db.close()

    await jobs._run_pr_review_job(review_id)

    db = SessionLocal()
    try:
        refreshed = db.get(models.PRReview, review_id)
        assert refreshed.status == "failed"
        assert refreshed.error == "scan_failed"
        assert db.query(models.Issue).filter_by(pr_review_id=review_id).count() == 0

        audit = db.query(models.AuditLogEntry).filter_by(org_id=org_id, action="pr_review.failed").one_or_none()
        assert audit is not None
    finally:
        db.close()


async def test_run_pr_review_job_no_findings_passes(monkeypatch, tmp_path):
    async def fake_run_strix_scan(*, scan_config, scan_id, image, local_sources):
        return None

    _install_fake_strix_module(monkeypatch, fake_run_strix_scan, run_dir=tmp_path)
    monkeypatch.setattr(jobs, "_clone_and_checkout_pr", lambda url, run_name, provider, pr_number: (f"/tmp/{run_name}", "sha"))

    import app.providers as providers_module

    monkeypatch.setattr(providers_module, "get_github_provider", lambda: types.SimpleNamespace(create_check_run=lambda **k: None))

    db = SessionLocal()
    try:
        org, repo = _make_org_and_repo(db)
        review = _make_pr_review(db, org, repo)
        review_id = review.id
    finally:
        db.close()

    await jobs._run_pr_review_job(review_id)

    db = SessionLocal()
    try:
        refreshed = db.get(models.PRReview, review_id)
        assert refreshed.status == "passed"
        assert refreshed.findings_count == 0
    finally:
        db.close()


# --------------------------------------------------------------------------
# Queue integration: pentest and PR-review jobs share one worker.
# --------------------------------------------------------------------------


async def test_worker_dispatches_pr_review_jobs(monkeypatch):
    await jobs.start_worker()
    try:
        seen = []

        async def _fake_job(review_id):
            seen.append(review_id)

        monkeypatch.setattr(jobs, "_run_pr_review_job", _fake_job)
        await jobs.enqueue_pr_review("review-123")

        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.01)
        assert seen == ["review-123"]
    finally:
        await jobs.stop_worker()


async def test_enqueue_pr_review_without_worker_raises():
    assert jobs._queue is None
    with pytest.raises(RuntimeError, match="job queue not started"):
        await jobs.enqueue_pr_review("some-id")
