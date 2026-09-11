"""In-process async job queue that executes pentests.

No Redis/Celery — a single `asyncio.Queue` plus a background worker task
started from the FastAPI lifespan (see main.py). This is deliberately
simple for a local scaffold; swapping in a real queue later means replacing
this module's `enqueue`/worker loop, not touching callers.

Two scan backends:
- `MockScanner` (default): waits briefly, then returns a handful of
  canned, realistic-looking findings (not derived from the target at
  all — same fixed list regardless of what repo/domain is picked), so the
  full pentest -> issues UI flow works without Docker or LLM credentials.
- Real scan: when `SAAS_ENABLE_REAL_SCAN=1`, invokes the upstream
  `strix.core.runner.run_strix_scan` engine (imported lazily, as a library
  call — see saas/README.md's isolation rule: we never fork engine code)
  for genuine source-aware analysis. A repository target is cloned locally
  first — via the org's connected GitHub/GitLab credential when there is
  one (`_repo_clone_url`, reusing `Integration.credential_encrypted` from
  Settings > Integrations), else a plain unauthenticated clone that only
  works for public repos — and mounted into the sandbox as a whitebox
  target; a domain target is scanned as a live web application URL. Real
  findings are read back from that run's `vulnerabilities.json` and
  translated into the same shape `MOCK_FINDINGS` already uses, so the rest
  of the pipeline (Issue creation, severity counting) doesn't need a
  real-vs-mock branch. If the real engine raises (Docker/LLM missing,
  clone failure, incomplete finish_scan) the pentest is marked failed
  and no canned findings are substituted — a failed real scan must never
  look completed. Uses the target org's `OrgLlmSettings` (model/key/base)
  if configured, applied via process env vars right before the call,
  under `_llm_env_lock` — see `_run_real_scan`'s docstring for why that
  lock exists.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from . import crypto, models
from .audit import record_audit
from .coverage_summary import MOCK_COVERAGE, empty_real_coverage, read_coverage_summary
from .db import SessionLocal
from .public_hosts import live_https_url
from .secret_text import redact_secret_shaped_text
from .settings import settings
from .standard_skills import to_engine_skills
from .time_utils import utcnow
from .webhook_delivery import deliver_event


class ScanIncompleteError(RuntimeError):
    """Real engine finished without finish_scan. ``findings`` may still be real."""

    def __init__(self, message: str, *, findings: list[dict] | None = None) -> None:
        super().__init__(message)
        self.findings = list(findings or [])

logger = logging.getLogger("saas.jobs")

# Created fresh in start_worker() rather than at module import time: this
# module is a long-lived singleton (one import per process), but a queue
# must be bound to the event loop of the lifespan that owns it. Rebuilding
# it per-lifespan keeps repeated app startup/shutdown cycles in the same
# process safe (e.g. multiple TestClient instances in a test session).
#
# One shared queue/worker for both pentests and PR reviews (a
# (job_type, entity_id) tuple, dispatched in _worker_loop) rather than a
# second queue: _run_real_scan's per-org LLM env-var override is only safe
# because exactly one scan runs at a time in this process (see its
# docstring) — a separate PR-review worker would let a pentest and a PR
# review race on that same global state.
_queue: asyncio.Queue[tuple[str, str]] | None = None
_worker_task: asyncio.Task | None = None


async def enqueue_pentest(pentest_id: str) -> None:
    if _queue is None:
        raise RuntimeError("job queue not started — call jobs.start_worker() from the app lifespan first")
    if _queue.qsize() >= settings.max_queued_jobs:
        raise RuntimeError("job queue is full")
    await _queue.put(("pentest", pentest_id))


async def enqueue_pr_review(review_id: str) -> None:
    if _queue is None:
        raise RuntimeError("job queue not started — call jobs.start_worker() from the app lifespan first")
    if _queue.qsize() >= settings.max_queued_jobs:
        raise RuntimeError("job queue is full")
    await _queue.put(("pr_review", review_id))


async def start_worker() -> None:
    global _queue, _worker_task
    if _worker_task is None:
        _queue = asyncio.Queue()
        _worker_task = asyncio.create_task(_worker_loop())


async def stop_worker() -> None:
    global _queue, _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        _worker_task = None
    _queue = None


async def _worker_loop() -> None:
    while True:
        job_type, entity_id = await _queue.get()
        try:
            if job_type == "pentest":
                await _run_pentest(entity_id)
            else:
                await _run_pr_review_job(entity_id)
        except Exception:  # noqa: BLE001 - a broken job must not kill the worker
            logger.exception("%s job %s failed", job_type, entity_id)
        finally:
            _queue.task_done()


async def _run_pentest(pentest_id: str) -> None:
    db = SessionLocal()
    try:
        pentest = db.get(models.Pentest, pentest_id)
        if pentest is None:
            return
        pentest.status = "running"
        pentest.started_at = utcnow()
        db.commit()
        record_audit(db, pentest.org_id, pentest.created_by, "pentest.started", pentest.target_label, {"scan_mode": pentest.scan_mode})

        llm_settings = db.get(models.OrgLlmSettings, pentest.org_id)

        # Everything from here on — running the scan itself, *and* turning
        # its findings into Issue rows — is wrapped in one try/except. It
        # used to only wrap the _scan() call, so a bad finding (e.g. an
        # unexpected `severity` value hitting the dict-indexed counter
        # below) raised past this function uncaught, leaving the pentest
        # stuck in "running" forever with no finished_at — contradicting
        # this module's "the job queue never gets stuck" guarantee. Nothing
        # from a failed run gets committed: db.add() below only stages
        # rows, so a mid-loop exception discards them along with the
        # attempt, which is what we want (no partial finding sets).
        try:
            try:
                findings = await _scan(db, pentest, llm_settings)
                terminal_status = "completed"
                audit_event = "pentest.completed"
                webhook_event = "pentest.completed"
            except ScanIncompleteError as exc:
                logger.warning("scan incomplete for pentest %s: %s", pentest.id, exc)
                findings = exc.findings
                terminal_status = "failed"
                audit_event = "pentest.failed"
                webhook_event = "pentest.failed"

            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            issue_events: list[dict] = []
            for finding in findings:
                severity_counts[finding["severity"]] = severity_counts.get(finding["severity"], 0) + 1
                db.add(
                    models.Issue(
                        org_id=pentest.org_id,
                        pentest_id=pentest.id,
                        repository_id=pentest.target_id if pentest.target_type == "repository" else None,
                        domain_id=pentest.target_id if pentest.target_type == "domain" else None,
                        **_issue_fields_from_finding(finding),
                    )
                )
                issue_events.append(
                    {
                        "pentest_id": pentest.id,
                        "title": finding["title"],
                        "severity": finding["severity"],
                        "target": finding["target"],
                        "endpoint": finding["endpoint"],
                    }
                )

            pentest.status = terminal_status
            pentest.finished_at = utcnow()
            pentest.severity_counts = severity_counts
            pentest.coverage = _coverage_for_pentest(pentest, finish_scan=terminal_status == "completed")

            if terminal_status == "completed":
                if pentest.target_type == "repository":
                    repo = db.get(models.Repository, pentest.target_id)
                    if repo:
                        repo.last_tested_at = pentest.finished_at
                elif pentest.target_type == "domain":
                    domain = db.get(models.Domain, pentest.target_id)
                    if domain:
                        domain.last_tested_at = pentest.finished_at

            db.commit()
            llm_usage = _llm_usage_payload(
                pentest.llm_input_tokens,
                pentest.llm_output_tokens,
                pentest.llm_total_tokens,
            )
            audit_extra = {"severity_counts": severity_counts, "llm_usage": llm_usage}
            if pentest.mock_fallback_reason:
                audit_extra["mock_fallback_reason"] = pentest.mock_fallback_reason
            if terminal_status != "completed":
                audit_extra["incomplete"] = True
            record_audit(db, pentest.org_id, pentest.created_by, audit_event, pentest.target_label, audit_extra)
            for issue_event in issue_events:
                await _deliver_webhook_event(pentest.org_id, "issue.created", issue_event)
            await _deliver_webhook_event(
                pentest.org_id,
                webhook_event,
                {
                    "pentest_id": pentest.id,
                    "target_type": pentest.target_type,
                    "target_id": pentest.target_id,
                    "target_label": pentest.target_label,
                    "status": pentest.status,
                    "severity_counts": severity_counts,
                    "llm_usage": llm_usage,
                },
            )
        except Exception:  # noqa: BLE001 - a scan/processing bug must not strand the pentest in "running" forever
            logger.exception("scan failed for pentest %s", pentest.id)
            db.rollback()
            pentest.status = "failed"
            pentest.finished_at = utcnow()
            db.commit()
            record_audit(db, pentest.org_id, pentest.created_by, "pentest.failed", pentest.target_label)
            await _deliver_webhook_event(
                pentest.org_id,
                "pentest.failed",
                {"pentest_id": pentest.id, "target_label": pentest.target_label, "status": pentest.status},
            )
    finally:
        db.close()


async def _deliver_webhook_event(org_id: str, event: str, payload: dict) -> None:
    try:
        await asyncio.to_thread(deliver_event, org_id, event, payload)
    except Exception:  # noqa: BLE001 - customer webhook delivery must not fail scan completion
        logger.exception("webhook dispatch failed: org=%s event=%s", org_id, event)


async def _scan(db, pentest: models.Pentest, llm_settings: models.OrgLlmSettings | None) -> list[dict]:
    if settings.enable_real_scan:
        return await _run_real_scan(db, pentest, llm_settings)
    findings = await _run_mock_scan(pentest)
    for finding in findings:
        finding["source"] = "mock"
    return findings


_LLM_ENV_KEYS = ("STRIX_LLM", "LLM_API_KEY", "LLM_API_BASE")

# Guards the read-modify-restore of os.environ's LLM_* keys in
# _run_real_scan/_run_real_pr_review_scan below. The single-worker queue
# already serializes these calls today (see this module's docstring), so
# this lock is currently redundant in practice — it exists so that
# invariant is *enforced*, not just documented, the moment anyone adds a
# second worker task to this same process (e.g. to raise throughput)
# without first splitting scan execution into isolated processes.
_llm_env_lock = asyncio.Lock()

# Strips embedded `user:token@` credentials from a URL — `_repo_clone_url`
# below embeds the org's live GitHub/GitLab PAT directly in the clone URL
# passed to `git`, and a failed clone/fetch echoes that URL back verbatim
# in its error message (both from strix's `clone_repository` and from the
# `git` CLI's own stderr in `_clone_and_checkout_pr`). Applied to every
# such error before it can reach a log line or an audit entry.
_CREDENTIAL_URL_RE = re.compile(r"://[^/@\s]+@")


def _redact_credential_url(text: str) -> str:
    return _CREDENTIAL_URL_RE.sub("://***@", text)


def _int_or_zero(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _read_run_record_status(scan_id: str) -> str | None:
    from strix.core.paths import run_dir_for, run_record_path

    path = run_record_path(run_dir_for(scan_id))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/corrupt run.json is treated as unknown
        return None
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    return status if isinstance(status, str) and status else None


def _read_translated_findings(scan_id: str) -> list[dict]:
    from strix.core.paths import run_dir_for

    vulnerabilities_path = run_dir_for(scan_id) / "vulnerabilities.json"
    if not vulnerabilities_path.exists():
        return []
    try:
        raw_findings = json.loads(vulnerabilities_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - unreadable artifacts still fail the pentest honestly
        logger.exception("could not read findings for run %s", scan_id)
        return []
    if not isinstance(raw_findings, list):
        return []
    return [_translate_real_finding(f) for f in raw_findings if isinstance(f, dict)]


def _read_llm_usage_for_run(scan_id: str) -> dict[str, int]:
    from strix.core.paths import run_dir_for, run_record_path

    path = run_record_path(run_dir_for(scan_id))
    if not path.exists():
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - diagnostic usage must not fail a scan
        logger.exception("could not read llm usage for run %s", scan_id)
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    raw = data.get("llm_usage") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    input_tokens = _int_or_zero(raw.get("input_tokens"))
    output_tokens = _int_or_zero(raw.get("output_tokens"))
    total_tokens = _int_or_zero(raw.get("total_tokens")) or input_tokens + output_tokens
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _llm_usage_payload(input_tokens: int | None, output_tokens: int | None, total_tokens: int | None) -> dict[str, int]:
    input_value = _int_or_zero(input_tokens)
    output_value = _int_or_zero(output_tokens)
    total_value = _int_or_zero(total_tokens) or input_value + output_value
    return {"input_tokens": input_value, "output_tokens": output_value, "total_tokens": total_value}


def _store_pentest_llm_usage(pentest: models.Pentest, usage: dict[str, int]) -> None:
    pentest.llm_input_tokens = usage["input_tokens"]
    pentest.llm_output_tokens = usage["output_tokens"]
    pentest.llm_total_tokens = usage["total_tokens"]


def _store_pr_review_llm_usage(review: models.PRReview, usage: dict[str, int]) -> None:
    review.llm_input_tokens = usage["input_tokens"]
    review.llm_output_tokens = usage["output_tokens"]
    review.llm_total_tokens = usage["total_tokens"]


def _repo_clone_url(db, org_id: str, repo: models.Repository) -> str:
    """The URL to `git clone`, authenticated with the org's connected
    GitHub/GitLab credential when there is one (see integrations.py —
    same `Integration.credential_encrypted` used to list real repos).
    Falls back to a plain, unauthenticated HTTPS URL when the repo's
    provider isn't connected (or was connected without a credential, like
    the seeded demo integration) — that only works for public repos, same
    limitation `list_installable`'s mock-catalog fallback already has.
    """
    integration = db.query(models.Integration).filter_by(org_id=org_id, provider=repo.provider).first()
    host = "github.com" if repo.provider == "github" else "gitlab.com"
    if integration and integration.base_url:
        host = integration.base_url.removeprefix("https://").removeprefix("http://").rstrip("/")
    if integration and integration.credential_encrypted:
        token = crypto.decrypt(integration.credential_encrypted)
        auth = f"x-access-token:{token}" if repo.provider == "github" else f"oauth2:{token}"
        return f"https://{auth}@{host}/{repo.full_name}.git"
    return f"https://{host}/{repo.full_name}.git"


async def _build_scan_targets(db, pentest: models.Pentest) -> tuple[list[dict], list[dict]]:
    """Builds `run_strix_scan`'s `targets`/`local_sources` arguments for
    this pentest's target — matching the exact shape
    `strix.interface.utils.collect_local_sources`/`build_root_task` expect
    (see strix/core/inputs.py). A repository target is cloned locally
    first (source-aware/whitebox scanning — the engine reads the actual
    checked-out code, not just a URL); a domain target is a live web
    application URL, no local checkout needed.

    A repository target may also carry `extra_domain_id` (see
    models.Pentest) — a verified live domain to test *in the same run*
    alongside the source checkout. strix's `targets` is always a list, so
    this is just a second entry: the engine gets both a local source tree
    (whitebox skill loads) and a live URL (auth-flow/CORS/cookie/etc.
    findings that only exist on a deployed instance), matching what a
    combined source-review-plus-dynamic-testing engagement covers.

    It may also carry `ref` (branch/tag/commit) — passed through to the
    clone so the scan targets that exact ref instead of whatever the
    remote's default branch's HEAD happens to be right now, and falling
    back to the repository's own `default_branch` when unset. Either way,
    the commit that was *actually* cloned is recorded on the pentest as
    `resolved_commit_sha` — a bare ref name like a branch is a moving
    target, so this is what makes "what did this scan test" reproducible
    and comparable across runs.
    """
    if pentest.target_type == "repository":
        repo = db.get(models.Repository, pentest.target_id)
        if repo is None:
            raise RuntimeError(f"repository {pentest.target_id} not found")

        from strix.interface.utils import clone_repository  # lazy import: optional dependency

        clone_url = _repo_clone_url(db, pentest.org_id, repo)
        requested_ref = pentest.ref or repo.default_branch
        # git clone shells out and blocks; run off the event loop so the
        # single-scan-at-a-time worker doesn't stall other request handling.
        try:
            cloned_path, resolved_sha = await asyncio.to_thread(
                clone_repository, clone_url, pentest.id, None, requested_ref
            )
        except Exception as exc:  # noqa: BLE001 - re-raised with the org's PAT redacted
            # clone_repository embeds clone_url (with the credential) verbatim
            # in its error message on failure — strip it before this can reach
            # a log line (`_scan`'s except Exception: logger.exception(...)).
            raise RuntimeError(_redact_credential_url(str(exc))) from None
        pentest.resolved_commit_sha = resolved_sha
        db.commit()
        targets = [
            {
                "type": "repository",
                "details": {
                    "target_repo": repo.full_name,
                    "cloned_repo_path": cloned_path,
                    "workspace_subdir": repo.full_name.split("/")[-1],
                },
            }
        ]
        local_sources = [
            {"source_path": cloned_path, "workspace_subdir": repo.full_name.split("/")[-1], "protect_metadata": False}
        ]

        if pentest.extra_domain_id:
            extra_domain = db.get(models.Domain, pentest.extra_domain_id)
            if extra_domain is None:
                raise RuntimeError(f"extra domain {pentest.extra_domain_id} not found")
            if not extra_domain.verified:
                raise RuntimeError(f"extra domain {pentest.extra_domain_id} is not verified")
            targets.append(
                {
                    "type": "web_application",
                    "details": {"target_url": live_https_url(extra_domain.hostname)},
                }
            )

        return targets, local_sources

    if pentest.target_type == "domain":
        domain = db.get(models.Domain, pentest.target_id)
        if domain is None:
            raise RuntimeError(f"domain {pentest.target_id} not found")
        if not domain.verified:
            raise RuntimeError(f"domain {pentest.target_id} is not verified")
        targets = [{"type": "web_application", "details": {"target_url": live_https_url(domain.hostname)}}]
        return targets, []

    raise RuntimeError(f"unsupported target_type {pentest.target_type!r}")


def _translate_real_finding(raw: dict) -> dict:
    """Normalizes one of `ReportState`'s vulnerability-report dicts (see
    strix/report/state.py's `add_vulnerability_report` — most fields are
    only added when truthy, so many are simply absent) into the fully
    populated shape `_run_pentest` expects, matching `MOCK_FINDINGS`'
    shape below so the rest of the pipeline needs no real-vs-mock branch."""
    file_path, line_number = _location_from_raw_finding(raw)
    source = raw.get("source")
    if source not in {"baseline_scan", "mock", "mock_fallback"}:
        source = "agent"
    return {
        "title": raw.get("title") or "Untitled finding",
        "description": raw.get("description") or "",
        "severity": (raw.get("severity") or "low").lower(),
        "cvss": raw.get("cvss"),
        "cvss_breakdown": raw.get("cvss_breakdown") or {},
        "technical_analysis": raw.get("technical_analysis") or "",
        "remediation_steps": raw.get("remediation_steps") or "",
        "poc_description": raw.get("poc_description") or "",
        "target": raw.get("target") or "",
        "endpoint": raw.get("endpoint") or "",
        "fix_effort": raw.get("fix_effort") or "medium",
        "source": source,
        "file_path": file_path,
        "line_number": line_number,
        "specialist_name": raw.get("agent_name") or None,
    }


def _location_from_raw_finding(raw: dict) -> tuple[str | None, int | None]:
    locations = raw.get("code_locations")
    if isinstance(locations, list):
        for item in locations:
            if not isinstance(item, dict):
                continue
            path = item.get("file") or item.get("path") or item.get("file_path")
            line = item.get("line") or item.get("start_line") or item.get("line_start")
            if path:
                return str(path), _optional_int(line)
    target = raw.get("target")
    if isinstance(target, str) and _looks_like_file_path(target):
        return target, None
    return None, None


def _looks_like_file_path(value: str) -> bool:
    if "/" in value or "\\" in value:
        return True
    return value.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rb", ".java", ".kt", ".rs"))


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _issue_fields_from_finding(finding: dict) -> dict:
    source = finding.get("source") or "agent"
    return {
        "title": finding["title"],
        "description": finding["description"],
        "severity": finding["severity"],
        "cvss": finding["cvss"],
        "cvss_breakdown": finding["cvss_breakdown"],
        "technical_analysis": finding["technical_analysis"],
        "remediation_steps": finding["remediation_steps"],
        "poc_description": finding["poc_description"],
        "target": finding["target"],
        "endpoint": finding["endpoint"],
        "fix_effort": finding["fix_effort"],
        "source": source,
        "disposition": "pending",
        "file_path": finding.get("file_path"),
        "line_number": finding.get("line_number"),
        "specialist_name": finding.get("specialist_name"),
    }


def _coverage_for_pentest(pentest: models.Pentest, *, finish_scan: bool) -> dict:
    if not settings.enable_real_scan:
        return dict(MOCK_COVERAGE)
    from strix.core.paths import run_dir_for

    summary = read_coverage_summary(run_dir_for(pentest.id), finish_scan=finish_scan)
    if summary is None:
        return empty_real_coverage(finish_scan=finish_scan)
    summary["finish_scan"] = finish_scan
    if not finish_scan:
        summary["complete"] = False
    return summary


async def _run_real_scan(db, pentest: models.Pentest, llm_settings: models.OrgLlmSettings | None) -> list[dict]:
    """Invoke the upstream strix engine as a library. Requires Docker + LLM credentials.

    If `llm_settings` has a model configured, this org's model/key/base
    override the process defaults for the duration of the call, via env
    vars (the only override surface strix's engine exposes — see
    strix/config/loader.py's `load_settings()` memoization and
    strix/config/models.py's `configure_sdk_model_defaults()`; there is no
    per-call api_key/api_base parameter anywhere in `run_strix_scan`,
    `build_strix_agent`, or `RunConfig`). The previous env is restored
    afterward and strix's settings cache is invalidated both times so the
    next scan (this org's or another's) re-reads fresh values.

    `_llm_env_lock` (module-level) serializes this section: two concurrent
    `run_strix_scan()` calls in this process would otherwise race on this
    same global env-var state. Today's single-worker queue already
    guarantees that in practice (`_worker_loop` awaits each job before
    dequeuing the next), but the lock makes it an enforced invariant
    rather than just a documented one — the thing that would otherwise
    silently break the moment a second in-process worker task is added
    for throughput. Don't parallelize scan *execution* itself (e.g. one
    subprocess per scan) without also reconsidering this lock, since
    holding it across a whole scan serializes real scans to one at a time
    regardless of worker count.
    """
    async with _llm_env_lock:
        from strix.config import load_settings
        from strix.config import loader as strix_config_loader
        from strix.core.runner import run_strix_scan  # lazy import: optional dependency

        override_active = bool(llm_settings and llm_settings.model)
        previous_env = {k: os.environ.get(k) for k in _LLM_ENV_KEYS} if override_active else None

        if override_active:
            os.environ["STRIX_LLM"] = llm_settings.model
            if llm_settings.api_key:
                api_key = crypto.decrypt_or_legacy_plaintext(llm_settings.api_key)
                if api_key:
                    os.environ["LLM_API_KEY"] = api_key
            if llm_settings.api_base:
                os.environ["LLM_API_BASE"] = llm_settings.api_base
            elif "LLM_API_BASE" in os.environ:
                del os.environ["LLM_API_BASE"]
            strix_config_loader._cached = None

        try:
            targets, local_sources = await _build_scan_targets(db, pentest)
            scan_config = {
                "scan_id": pentest.id,
                "targets": targets,
                "run_name": pentest.id,
                "scan_mode": pentest.scan_mode,
                "user_instructions": redact_secret_shaped_text(pentest.custom_instructions),
                "skills": to_engine_skills(pentest.skills),
            }
            incomplete_message = None
            engine_incomplete = getattr(sys.modules.get("strix.core.runner"), "ScanIncompleteError", ())
            try:
                await run_strix_scan(
                    scan_config=scan_config,
                    scan_id=pentest.id,
                    image=load_settings().runtime.image,
                    local_sources=local_sources,
                )
            except engine_incomplete as exc:
                incomplete_message = str(exc)
            _store_pentest_llm_usage(pentest, _read_llm_usage_for_run(pentest.id))

            findings = _read_translated_findings(pentest.id)
            run_status = _read_run_record_status(pentest.id)
            if incomplete_message or run_status in {"failed", "stopped", "interrupted"}:
                raise ScanIncompleteError(
                    incomplete_message
                    or f"Scan ended with status {run_status!r} without finish_scan",
                    findings=findings,
                )
            return findings
        finally:
            if override_active and previous_env is not None:
                for key, value in previous_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                strix_config_loader._cached = None


# --------------------------------------------------------------------------
# PR reviews — real scan only, diff-scoped against the PR's base branch.
# --------------------------------------------------------------------------


def _pr_ref_spec(provider: str, pr_number: int) -> str:
    """The provider's synthetic ref for a PR/MR's head commit. Fetching
    this (rather than checking out the PR's plain source-branch name)
    resolves correctly even when the PR is from a fork, where the source
    branch doesn't exist in the base repository's clone at all."""
    if provider == "gitlab":
        return f"refs/merge-requests/{pr_number}/head"
    return f"refs/pull/{pr_number}/head"


def _clone_and_checkout_pr(clone_url: str, run_name: str, provider: str, pr_number: int) -> tuple[str, str]:
    """Clones `clone_url` (full history — diff-scope requires it, same as
    a shallow `--depth 1` clone would break strix's merge-base computation)
    and checks out the PR/MR's head commit. Returns `(clone_path,
    resolved_head_sha)`. Blocking (shells out to git); call via
    `asyncio.to_thread`, matching `strix.interface.utils.clone_repository`'s
    own off-event-loop convention.
    """
    git_executable = shutil.which("git")
    if git_executable is None:
        raise FileNotFoundError("Git executable not found in PATH")

    # See strix.interface.utils.clone_repository's STRIX_REPOS_DIR comment:
    # sibling sandbox containers need this path visible to the host daemon.
    repos_base = Path(os.environ.get("STRIX_REPOS_DIR") or tempfile.gettempdir()) / "strix_pr_reviews"
    temp_dir = repos_base / run_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    clone_path = temp_dir / "repo"
    if clone_path.exists():
        shutil.rmtree(clone_path)

    def _run(args: list[str], error_message: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(args, capture_output=True, text=True, check=True)  # noqa: S603
        except subprocess.CalledProcessError as e:
            # error_message embeds clone_url (with the org's credential) and
            # git's own stderr often echoes the same URL on a failed
            # clone/fetch (e.g. curl-backed HTTPS errors) — redact both
            # before this can reach a log line or bubble up as an audit
            # entry. `from None` also drops the original exception (and its
            # unredacted args) from the traceback chain a logger would print.
            raise ValueError(_redact_credential_url(f"{error_message}: {e.stderr or e}")) from None

    _run([git_executable, "clone", clone_url, str(clone_path)], f"Could not clone repository {clone_url}")
    ref_spec = _pr_ref_spec(provider, pr_number)
    _run(
        [git_executable, "-C", str(clone_path), "fetch", "origin", f"{ref_spec}:pr-ref"],
        f"Could not fetch PR #{pr_number} ({ref_spec}) from {clone_url}",
    )
    _run([git_executable, "-C", str(clone_path), "checkout", "pr-ref"], f"Could not check out PR #{pr_number}")
    resolved = _run([git_executable, "-C", str(clone_path), "rev-parse", "HEAD"], "Could not resolve PR HEAD")
    return str(clone_path.resolve()), resolved.stdout.strip()


def _pr_review_blocking_severities(db, org_id: str) -> tuple[list[str], bool]:
    """(blocking_severities, block_prs_on_findings) for `org_id`, read
    fresh at scan-completion time rather than captured at trigger time —
    settings can change while a review is queued/running. Defaults match
    PRReviewSettings' own column defaults for an org that has never opened
    PR Review Settings (so no row exists yet)."""
    row = db.get(models.PRReviewSettings, org_id)
    if row is None:
        return (["critical", "high"], True)
    return (row.blocking_severities, row.block_prs_on_findings)


async def _run_real_pr_review_scan(
    db, review: models.PRReview, repo: models.Repository, llm_settings: models.OrgLlmSettings | None
) -> list[dict]:
    """Invokes the upstream strix engine, scoped to only the PR's changed
    files (`strix.interface.utils.resolve_diff_scope_context`, the same
    diff-scope mechanism the strix CLI uses in CI) diffed against the PR's
    base branch. See `_run_real_scan`'s docstring for the per-org LLM env
    override mechanics this mirrors — same safety caveat applies (single
    scan at a time in this process).
    """
    async with _llm_env_lock:
        from strix.config import load_settings
        from strix.config import loader as strix_config_loader
        from strix.core.runner import run_strix_scan  # lazy import: optional dependency
        from strix.interface.utils import resolve_diff_scope_context

        override_active = bool(llm_settings and llm_settings.model)
        previous_env = {k: os.environ.get(k) for k in _LLM_ENV_KEYS} if override_active else None

        if override_active:
            os.environ["STRIX_LLM"] = llm_settings.model
            if llm_settings.api_key:
                api_key = crypto.decrypt_or_legacy_plaintext(llm_settings.api_key)
                if api_key:
                    os.environ["LLM_API_KEY"] = api_key
            if llm_settings.api_base:
                os.environ["LLM_API_BASE"] = llm_settings.api_base
            elif "LLM_API_BASE" in os.environ:
                del os.environ["LLM_API_BASE"]
            strix_config_loader._cached = None

        try:
            clone_url = _repo_clone_url(db, review.org_id, repo)
            cloned_path, resolved_sha = await asyncio.to_thread(
                _clone_and_checkout_pr, clone_url, review.id, repo.provider, review.pr_number
            )
            review.resolved_head_sha = resolved_sha
            db.commit()

            workspace_subdir = repo.full_name.split("/")[-1]
            local_sources = [{"source_path": cloned_path, "workspace_subdir": workspace_subdir, "protect_metadata": False}]
            target_branch = review.target_branch or repo.default_branch

            diff_scope = await asyncio.to_thread(
                resolve_diff_scope_context, local_sources, "diff", f"origin/{target_branch}", True
            )

            scan_config = {
                "scan_id": review.id,
                "targets": [
                    {
                        "type": "repository",
                        "details": {
                            "target_repo": repo.full_name,
                            "cloned_repo_path": cloned_path,
                            "workspace_subdir": workspace_subdir,
                        },
                    }
                ],
                "run_name": review.id,
                # "quick" over "deep": diff-scope already narrows the surface to
                # the PR's changed files, and PR checks need fast turnaround.
                "scan_mode": "quick",
                "diff_scope": diff_scope.metadata,
            }
            incomplete_message = None
            engine_incomplete = getattr(sys.modules.get("strix.core.runner"), "ScanIncompleteError", ())
            try:
                await run_strix_scan(
                    scan_config=scan_config,
                    scan_id=review.id,
                    image=load_settings().runtime.image,
                    local_sources=local_sources,
                )
            except engine_incomplete as exc:
                incomplete_message = str(exc)
            _store_pr_review_llm_usage(review, _read_llm_usage_for_run(review.id))

            findings = _read_translated_findings(review.id)
            run_status = _read_run_record_status(review.id)
            if incomplete_message or run_status in {"failed", "stopped", "interrupted"}:
                raise ScanIncompleteError(
                    incomplete_message
                    or f"Scan ended with status {run_status!r} without finish_scan",
                    findings=findings,
                )
            return findings
        finally:
            if override_active and previous_env is not None:
                for key, value in previous_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                strix_config_loader._cached = None


async def _run_pr_review_job(review_id: str) -> None:
    """The PR-review counterpart of `_run_pentest`: runs the real scan,
    files findings as Issues, and finalizes `status`. No mock fallback —
    a scan failure lands the review in `status="failed"` with `error` set,
    rather than silently substituting canned findings, so a real problem
    (bad credentials, unreachable repo, engine crash) is visible instead of
    masked as a legitimate "no issues found" result."""
    db = SessionLocal()
    try:
        review = db.get(models.PRReview, review_id)
        if review is None:
            return
        repo = db.get(models.Repository, review.repository_id)
        if repo is None:
            review.status = "failed"
            review.error = "repository_not_found"
            db.commit()
            return

        llm_settings = db.get(models.OrgLlmSettings, review.org_id)

        scan_incomplete = False
        try:
            findings = await _run_real_pr_review_scan(db, review, repo, llm_settings)
        except ScanIncompleteError as exc:
            logger.warning("PR review %s incomplete: %s", review.id, exc)
            findings = exc.findings
            review.error = "scan_incomplete"
            scan_incomplete = True
        except Exception:  # noqa: BLE001 - a broken PR review must not kill the worker
            logger.exception("real scan failed for PR review %s", review.id)
            db.rollback()
            review.status = "failed"
            review.error = "scan_failed"
            db.commit()
            record_audit(db, review.org_id, None, "pr_review.failed", f"{repo.full_name}#{review.pr_number}")
            await _deliver_webhook_event(
                review.org_id,
                "pr_review.failed",
                {"review_id": review.id, "repository_id": repo.id, "status": review.status},
            )
            return

        issue_events: list[dict] = []
        for finding in findings:
            fields = _issue_fields_from_finding(finding)
            fields["target"] = repo.full_name
            db.add(
                models.Issue(
                    org_id=review.org_id,
                    pr_review_id=review.id,
                    repository_id=repo.id,
                    **fields,
                )
            )
            issue_events.append(
                {
                    "pr_review_id": review.id,
                    "repository_id": repo.id,
                    "title": finding["title"],
                    "severity": finding["severity"],
                    "target": repo.full_name,
                    "endpoint": finding["endpoint"],
                }
            )
        review.findings_count = len(findings)

        blocking_severities, block_prs_on_findings = _pr_review_blocking_severities(db, review.org_id)
        blocking = any(f["severity"] in blocking_severities for f in findings)
        if scan_incomplete:
            review.status = "failed"
        elif not findings:
            review.status = "passed"
        elif block_prs_on_findings and blocking:
            review.status = "needs_attention"
        else:
            review.status = "awaiting_merge"
        db.commit()

        from .providers import get_github_provider

        provider = get_github_provider()
        conclusion = "failure" if review.status == "needs_attention" else "success"
        provider.create_check_run(
            full_name=repo.full_name, pr_number=review.pr_number, conclusion=conclusion, summary=f"{review.findings_count} finding(s)"
        )

        llm_usage = _llm_usage_payload(review.llm_input_tokens, review.llm_output_tokens, review.llm_total_tokens)
        record_audit(
            db,
            review.org_id,
            None,
            "pr_review.completed",
            f"{repo.full_name}#{review.pr_number}",
            {"status": review.status, "findings_count": review.findings_count, "llm_usage": llm_usage},
        )
        for issue_event in issue_events:
            await _deliver_webhook_event(review.org_id, "issue.created", issue_event)
        await _deliver_webhook_event(
            review.org_id,
            "pr_review.completed",
            {
                "review_id": review.id,
                "repository_id": repo.id,
                "repository": repo.full_name,
                "pr_number": review.pr_number,
                "status": review.status,
                "findings_count": review.findings_count,
                "llm_usage": llm_usage,
            },
        )
    finally:
        db.close()


MOCK_FINDINGS = [
    {
        "title": "Missing authorization check on withdrawal endpoint",
        "severity": "critical",
        "cvss": 9.1,
        "endpoint": "/api/v1/wallet/withdraw",
        "description": "The withdrawal endpoint does not verify that the authenticated user owns the target wallet ID, allowing cross-account fund transfers.",
        "technical_analysis": "The handler reads `wallet_id` directly from the request body and passes it to the transfer service without comparing it against `request.user.wallet_id`. Any authenticated user can supply another user's wallet ID.",
        "remediation_steps": "Derive the wallet ID from the authenticated session rather than trusting client input, or explicitly verify ownership before processing the transfer.",
        "poc_description": "Authenticate as user A, then POST to /api/v1/wallet/withdraw with user B's wallet_id and a destination account controlled by the attacker.",
        "fix_effort": "low",
    },
    {
        "title": "Reflected XSS in search query parameter",
        "severity": "high",
        "cvss": 6.8,
        "endpoint": "/search?q=",
        "description": "The `q` query parameter is reflected into the page without HTML-escaping, allowing script injection.",
        "technical_analysis": "The search results template interpolates `request.args['q']` directly into an HTML attribute without escaping.",
        "remediation_steps": "Use the templating engine's auto-escaping (or explicit escaping) for all user-controlled values rendered into HTML.",
        "poc_description": "Visit /search?q=<script>alert(document.domain)</script> while authenticated.",
        "fix_effort": "low",
    },
    {
        "title": "Outdated dependency with known RCE (CVE-2023-XXXX)",
        "severity": "high",
        "cvss": 8.1,
        "endpoint": "package.json",
        "description": "A transitive dependency pinned to a vulnerable version has a published remote code execution advisory.",
        "technical_analysis": "Dependency tree resolution shows the vulnerable version is reachable from a production code path that deserializes untrusted input.",
        "remediation_steps": "Upgrade the dependency to the patched release and re-run the dependency scan to confirm the advisory no longer applies.",
        "poc_description": "N/A - dependency advisory, see linked CVE for a public exploit.",
        "fix_effort": "low",
    },
    {
        "title": "Verbose error messages leak stack traces",
        "severity": "medium",
        "cvss": 4.3,
        "endpoint": "/api/v1/*",
        "description": "Unhandled exceptions return full Python stack traces to the client, revealing internal file paths and framework versions.",
        "technical_analysis": "Debug mode appears enabled in the deployed environment, or a generic exception handler is missing.",
        "remediation_steps": "Disable debug mode in production and add a catch-all exception handler that returns a generic error response.",
        "poc_description": "Send a malformed request body to any JSON endpoint and observe the response body.",
        "fix_effort": "low",
    },
    {
        "title": "Missing rate limiting on login endpoint",
        "severity": "low",
        "cvss": 3.1,
        "endpoint": "/api/v1/auth/login",
        "description": "The login endpoint has no observable rate limiting, permitting credential-stuffing attempts.",
        "technical_analysis": "Repeated failed login attempts from the same IP/account were not throttled or locked out during testing.",
        "remediation_steps": "Add rate limiting (per-IP and per-account) and consider progressive delays or CAPTCHA after repeated failures.",
        "poc_description": "Script repeated POSTs to /api/v1/auth/login with varying passwords for a known username.",
        "fix_effort": "medium",
    },
]


async def _run_mock_scan(pentest: models.Pentest) -> list[dict]:
    low, high = settings.mock_scan_min_seconds, settings.mock_scan_max_seconds
    await asyncio.sleep(low + random.random() * max(0.0, high - low))
    sample_size = random.randint(2, len(MOCK_FINDINGS))
    chosen = random.sample(MOCK_FINDINGS, k=sample_size)
    findings = []
    for f in chosen:
        findings.append(
            {
                **f,
                "id": uuid.uuid4().hex,
                "target": pentest.target_label,
                "cvss_breakdown": {"base_score": f["cvss"], "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N"},
            }
        )
    return findings
