from app.routers import pr_reviews

from .conftest import add_member, add_repo


def _enable_real_scan(monkeypatch):
    """PR reviews require real scanning — see app/jobs.py's PR-review
    section docstring, there is no mock fallback. Router-level tests here
    only exercise "was a running review created and enqueued correctly";
    the actual scan execution (_run_real_pr_review_scan/_run_pr_review_job)
    is covered separately in test_jobs.py, mirroring how pentest tests
    split router-level and job-level coverage."""
    monkeypatch.setattr(pr_reviews.settings, "enable_real_scan", True)


def _stub_enqueue(monkeypatch):
    """Replaces enqueue_pr_review with a recorder so triggering a review in
    these tests never touches the real job queue/worker — that queue is
    live during these tests (TestClient's lifespan starts it), and would
    otherwise attempt a real clone+scan."""
    calls: list[str] = []

    async def _fake_enqueue(review_id: str) -> None:
        calls.append(review_id)

    monkeypatch.setattr(pr_reviews, "enqueue_pr_review", _fake_enqueue)
    return calls


def test_settings_defaults_and_update(auth_client):
    client, _org = auth_client
    res = client.get("/api/pr-reviews/settings")
    assert res.status_code == 200
    body = res.json()
    assert body["block_prs_on_findings"] is True
    assert body["blocking_severities"] == ["critical", "high"]

    update = client.patch(
        "/api/pr-reviews/settings",
        json={
            "rereview_on_push": True,
            "target_branches": ["main", "release/*"],
            "blocking_severities": ["critical"],
            "excluded_usernames": ["dependabot"],
            "review_cap_per_dev": 10,
        },
    )
    assert update.status_code == 200
    body = update.json()
    assert body["rereview_on_push"] is True
    assert body["target_branches"] == ["main", "release/*"]
    assert body["blocking_severities"] == ["critical"]
    assert body["excluded_usernames"] == ["dependabot"]
    assert body["review_cap_per_dev"] == 10
    # Unset fields are unaffected by a partial update.
    assert body["allow_overage_reviews"] is True


def test_update_settings_requires_admin(auth_client):
    client, org = auth_client
    add_member(client, org)
    res = client.patch("/api/pr-reviews/settings", json={"block_prs_on_findings": False})
    assert res.status_code == 403
    assert res.json()["detail"] == "admin_required"
    # A member can still read settings.
    assert client.get("/api/pr-reviews/settings").status_code == 200


def test_list_pr_reviews_repository_names_correct_with_multiple_repos(auth_client, monkeypatch):
    """Regression check for the N+1 -> batched-lookup refactor: repository
    names must still resolve correctly when reviews span several repos."""
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo_a = add_repo(client, "acme/widgets")
    repo_b = add_repo(client, "acme/gadgets")

    client.post("/api/pr-reviews", json={"repository_id": repo_a["id"], "pr_number": 1, "title": "A", "author": "x"})
    client.post("/api/pr-reviews", json={"repository_id": repo_b["id"], "pr_number": 2, "title": "B", "author": "x"})

    items = client.get("/api/pr-reviews").json()["items"]
    names_by_repo = {i["repository_id"]: i["repository_full_name"] for i in items}
    assert names_by_repo[repo_a["id"]] == "acme/widgets"
    assert names_by_repo[repo_b["id"]] == "acme/gadgets"


def test_trigger_review_repository_not_found(auth_client):
    client, _org = auth_client
    res = client.post("/api/pr-reviews", json={"repository_id": "nope", "pr_number": 1, "title": "x"})
    assert res.status_code == 404


def test_trigger_review_requires_real_scan_enabled(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    res = client.post("/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 1, "title": "x"})
    assert res.status_code == 400
    assert res.json()["detail"] == "real_scan_not_enabled"


def test_trigger_review_creates_a_running_review_and_enqueues_it(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    calls = _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)

    res = client.post(
        "/api/pr-reviews",
        json={"repository_id": repo["id"], "pr_number": 7, "title": "Add feature", "author": "octocat", "target_branch": "main"},
    )
    assert res.status_code == 200
    review = res.json()
    assert review["status"] == "running"
    assert review["findings_count"] == 0
    assert review["repository_full_name"] == repo["full_name"]
    assert review["target_branch"] == "main"
    assert review["resolved_head_sha"] is None
    assert review["error"] is None
    assert calls == [review["id"]]

    listing = client.get("/api/pr-reviews").json()
    assert listing["counts"]["all"] == 1
    assert len(listing["items"]) == 1

    filtered = client.get("/api/pr-reviews?status_filter=running").json()
    assert len(filtered["items"]) == 1

    by_repo = client.get(f"/api/pr-reviews?repository_id={repo['id']}").json()
    assert len(by_repo["items"]) == 1

    by_search = client.get("/api/pr-reviews?search=Add feature").json()
    assert len(by_search["items"]) == 1

    by_search_miss = client.get("/api/pr-reviews?search=nonexistent-title").json()
    assert by_search_miss["items"] == []


def test_trigger_review_without_a_picked_pr_leaves_target_branch_null(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)

    review = client.post("/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 7, "title": "x"}).json()
    assert review["target_branch"] is None


# --------------------------------------------------------------------------
# Single review: detail, findings, run log, report
# --------------------------------------------------------------------------


def _finish_review(review_id: str, *, status: str = "passed", findings: list[dict] | None = None) -> None:
    """Directly drives a PRReview to a "done" state, bypassing the job
    queue — mirrors _run_pr_review_job's own DB writes (status,
    findings_count, resolved_head_sha, Issue rows) without needing a real
    scan, so report/log tests don't depend on queue timing."""
    from app import models
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        review = db.get(models.PRReview, review_id)
        review.status = status
        review.resolved_head_sha = "abc1234def5678"
        for f in findings or []:
            db.add(
                models.Issue(
                    org_id=review.org_id,
                    pr_review_id=review.id,
                    repository_id=review.repository_id,
                    title=f["title"],
                    severity=f["severity"],
                    cvss=f.get("cvss"),
                    target=f.get("target", ""),
                )
            )
        review.findings_count = len(findings or [])
        db.commit()
    finally:
        db.close()


def test_get_pr_review_not_found(auth_client):
    client, _org = auth_client
    res = client.get("/api/pr-reviews/does-not-exist")
    assert res.status_code == 404


def test_get_pr_review_returns_the_review(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    created = client.post("/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 9, "title": "Add feature"}).json()

    res = client.get(f"/api/pr-reviews/{created['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]
    assert res.json()["status"] == "running"


def test_settings_route_is_not_shadowed_by_the_review_id_route(auth_client):
    """Regression test: /{review_id} is registered after /settings
    specifically so a request for the literal "settings" path isn't
    captured as review_id="settings" — see the route-ordering comment in
    app/routers/pr_reviews.py."""
    client, _org = auth_client
    res = client.get("/api/pr-reviews/settings")
    assert res.status_code == 200
    assert "block_prs_on_findings" in res.json()


def test_get_pr_review_issues_not_found(auth_client):
    client, _org = auth_client
    res = client.get("/api/pr-reviews/does-not-exist/issues")
    assert res.status_code == 404


def test_get_pr_review_issues_returns_filed_findings(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    review = client.post("/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 9, "title": "Add feature"}).json()
    _finish_review(review["id"], status="needs_attention", findings=[{"title": "SQLi in search", "severity": "high", "cvss": 8.1}])

    res = client.get(f"/api/pr-reviews/{review['id']}/issues")
    assert res.status_code == 200
    issues = res.json()
    assert len(issues) == 1
    assert issues[0]["title"] == "SQLi in search"
    assert issues[0]["pr_review_id"] == review["id"]


def test_get_pr_review_logs_unavailable_when_no_run_log_exists(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    review = client.post("/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 9, "title": "Add feature"}).json()

    res = client.get(f"/api/pr-reviews/{review['id']}/logs")
    assert res.status_code == 200
    assert res.json()["available"] is False


def test_get_pr_review_logs_not_found(auth_client):
    client, _org = auth_client
    res = client.get("/api/pr-reviews/does-not-exist/logs")
    assert res.status_code == 404


def test_pr_review_report_not_ready_while_running(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    review = client.post("/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 9, "title": "Add feature"}).json()

    res = client.get(f"/api/pr-reviews/{review['id']}/report")
    assert res.status_code == 409
    assert res.json()["detail"] == "report_not_ready"

    download = client.get(f"/api/pr-reviews/{review['id']}/report/download")
    assert download.status_code == 409


def test_pr_review_report_not_ready_when_failed(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    review = client.post("/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 9, "title": "Add feature"}).json()
    _finish_review(review["id"], status="failed")

    res = client.get(f"/api/pr-reviews/{review['id']}/report")
    assert res.status_code == 409


def test_pr_review_report_not_found(auth_client):
    client, _org = auth_client
    res = client.get("/api/pr-reviews/does-not-exist/report")
    assert res.status_code == 404


def test_view_and_download_pr_review_report(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    review = client.post(
        "/api/pr-reviews", json={"repository_id": repo["id"], "pr_number": 9, "title": "Add wallet withdraw endpoint", "target_branch": "main"}
    ).json()
    _finish_review(review["id"], status="needs_attention", findings=[{"title": "SQLi in search", "severity": "high", "cvss": 8.1}])

    view = client.get(f"/api/pr-reviews/{review['id']}/report")
    assert view.status_code == 200
    assert "text/html" in view.headers["content-type"]
    assert "PR Security Review" in view.text
    assert "SQLi in search" in view.text
    assert repo["full_name"] in view.text
    assert "#9" in view.text

    download = client.get(f"/api/pr-reviews/{review['id']}/report/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"] == f'attachment; filename="pr-review-report-{review["id"]}.pdf"'
    assert download.content.startswith(b"%PDF")


# --------------------------------------------------------------------------
# GitHub webhook
# --------------------------------------------------------------------------


def _webhook(client, event: str, payload: dict):
    return client.post("/api/webhooks/github", headers={"X-GitHub-Event": event}, json=payload)


def test_webhook_unregistered_repository_skipped(auth_client):
    client, _org = auth_client
    res = _webhook(
        client,
        "pull_request",
        {"action": "opened", "repository": {"full_name": "nobody/nothing"}, "pull_request": {"number": 1, "title": "x", "user": {"login": "a"}, "base": {"ref": "main"}}},
    )
    assert res.status_code == 200
    assert res.json()["skipped"] == "repository_not_registered"


def test_webhook_skipped_when_real_scan_not_enabled(auth_client):
    client, _org = auth_client
    repo = add_repo(client)

    res = _webhook(
        client,
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": repo["full_name"]},
            "pull_request": {"number": 5, "title": "Add endpoint", "user": {"login": "octocat"}, "base": {"ref": "main"}},
        },
    )
    assert res.status_code == 200
    assert res.json()["skipped"] == "real_scan_not_enabled"
    assert client.get("/api/pr-reviews").json()["counts"]["all"] == 0


def test_webhook_pull_request_opened_runs_review(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    calls = _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)

    res = _webhook(
        client,
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": repo["full_name"]},
            "pull_request": {"number": 5, "title": "Add endpoint", "user": {"login": "octocat"}, "base": {"ref": "main"}},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["status"] == "running"
    assert "review_id" in body
    assert calls == [body["review_id"]]

    reviews = client.get("/api/pr-reviews").json()
    assert reviews["counts"]["all"] == 1
    assert reviews["items"][0]["target_branch"] == "main"


def test_webhook_auto_review_disabled_skips(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    client.patch(f"/api/repositories/{repo['id']}", json={"auto_review_enabled": False})

    res = _webhook(
        client,
        "pull_request",
        {"action": "opened", "repository": {"full_name": repo["full_name"]}, "pull_request": {"number": 1, "title": "x", "user": {"login": "a"}, "base": {"ref": "main"}}},
    )
    assert res.json()["skipped"] == "auto_review_disabled"


def test_webhook_synchronize_skipped_unless_rereview_on_push(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    calls = _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)

    payload = {
        "action": "synchronize",
        "repository": {"full_name": repo["full_name"]},
        "pull_request": {"number": 1, "title": "x", "user": {"login": "a"}, "base": {"ref": "main"}},
    }
    res = _webhook(client, "pull_request", payload)
    assert res.json()["skipped"] == "rereview_on_push_disabled"

    client.patch("/api/pr-reviews/settings", json={"rereview_on_push": True})
    res = _webhook(client, "pull_request", payload)
    assert "review_id" in res.json()
    assert len(calls) == 1


def test_webhook_target_branch_filter(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    client.patch("/api/pr-reviews/settings", json={"target_branches": ["release"]})

    payload = {
        "action": "opened",
        "repository": {"full_name": repo["full_name"]},
        "pull_request": {"number": 1, "title": "x", "user": {"login": "a"}, "base": {"ref": "main"}},
    }
    res = _webhook(client, "pull_request", payload)
    assert res.json()["skipped"] == "branch_not_targeted"

    payload["pull_request"]["base"]["ref"] = "release"
    res = _webhook(client, "pull_request", payload)
    assert "review_id" in res.json()


def test_webhook_excluded_username_and_bot_filters(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)
    client.patch("/api/pr-reviews/settings", json={"excluded_usernames": ["blockeduser"], "exclude_bot_accounts": True})

    blocked = _webhook(
        client,
        "pull_request",
        {"action": "opened", "repository": {"full_name": repo["full_name"]}, "pull_request": {"number": 1, "title": "x", "user": {"login": "blockeduser"}, "base": {"ref": "main"}}},
    )
    assert blocked.json()["skipped"] == "excluded_username"

    bot = _webhook(
        client,
        "pull_request",
        {"action": "opened", "repository": {"full_name": repo["full_name"]}, "pull_request": {"number": 2, "title": "x", "user": {"login": "renovate[bot]"}, "base": {"ref": "main"}}},
    )
    assert bot.json()["skipped"] == "excluded_bot_account"


def test_webhook_issue_comment_requires_strix_mention(auth_client, monkeypatch):
    _enable_real_scan(monkeypatch)
    _stub_enqueue(monkeypatch)
    client, _org = auth_client
    repo = add_repo(client)

    no_mention = _webhook(
        client,
        "issue_comment",
        {"action": "created", "repository": {"full_name": repo["full_name"]}, "issue": {"number": 3, "title": "x", "user": {"login": "a"}, "pull_request": {}}, "comment": {"body": "looks good"}},
    )
    assert no_mention.json()["skipped"] == "no_strix_mention"

    with_mention = _webhook(
        client,
        "issue_comment",
        {"action": "created", "repository": {"full_name": repo["full_name"]}, "issue": {"number": 3, "title": "x", "user": {"login": "a"}, "pull_request": {}}, "comment": {"body": "@strix please review"}},
    )
    assert "review_id" in with_mention.json()


def test_webhook_unhandled_event_skipped(auth_client):
    client, _org = auth_client
    res = _webhook(client, "push", {})
    assert res.status_code == 200
    assert res.json()["skipped"].startswith("unhandled_event")


def test_webhook_missing_repository_or_pr_number_skipped(auth_client):
    client, _org = auth_client
    res = _webhook(client, "pull_request", {"action": "opened", "repository": {}, "pull_request": {"user": {}, "base": {}}})
    assert res.json()["skipped"] == "missing_repository_or_pr_number"


def test_webhook_invalid_json_skipped(client):
    res = client.post("/api/webhooks/github", headers={"X-GitHub-Event": "pull_request", "content-type": "application/json"}, content=b"not json")
    assert res.status_code == 200
    assert res.json()["skipped"] == "invalid_json"


def test_webhook_bad_signature_rejected(auth_client, monkeypatch):
    client, _org = auth_client
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "github_app_id", "fake-app-id")
    monkeypatch.setattr(settings_module.settings, "github_app_private_key", "fake-key")
    monkeypatch.setattr(settings_module.settings, "github_webhook_secret", "shh")

    res = _webhook(client, "pull_request", {})
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid_signature"


def test_webhook_org_without_repo_org_not_found_branch(auth_client, monkeypatch):
    """Covers the (currently unreachable in practice) org-not-found branch:
    a repository row whose org_id doesn't resolve to an Organization."""
    client, _org = auth_client
    repo = add_repo(client)

    from app import models
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        row = db.get(models.Repository, repo["id"])
        row.org_id = "orphaned-org-id"
        db.commit()
    finally:
        db.close()

    res = _webhook(
        client,
        "pull_request",
        {"action": "opened", "repository": {"full_name": repo["full_name"]}, "pull_request": {"number": 1, "title": "x", "user": {"login": "a"}, "base": {"ref": "main"}}},
    )
    assert res.json()["skipped"] == "org_not_found"
