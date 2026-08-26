import time

from .conftest import add_repo


def _run_pentest_to_completion(client, repo, timeout: float = 5.0) -> dict:
    pentest = client.post("/api/pentests", json={"target_type": "repository", "target_id": repo["id"]}).json()
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/pentests/{pentest['id']}").json()
        if body["status"] == "completed":
            return pentest
        time.sleep(0.02)
    raise AssertionError("pentest did not complete")


def test_list_issues_empty(auth_client):
    client, _org = auth_client
    res = client.get("/api/issues")
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["severity_counts"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert body["status_counts"]["all"] == 0


def test_issue_lifecycle(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    _run_pentest_to_completion(client, repo)

    listing = client.get("/api/issues").json()
    assert len(listing["items"]) > 0
    issue = listing["items"][0]

    detail = client.get(f"/api/issues/{issue['id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == issue["title"]
    # Mock-scan findings carry no Tier 3 baseline-scan provenance.
    assert issue["source"] is None
    assert detail.json()["source"] is None

    update = client.patch(f"/api/issues/{issue['id']}/status", json={"status": "fixed"})
    assert update.status_code == 200
    assert update.json()["status"] == "fixed"

    fixed = client.get("/api/issues?status_filter=fixed").json()
    assert any(i["id"] == issue["id"] for i in fixed["items"])


def test_update_issue_status_invalid_value(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    _run_pentest_to_completion(client, repo)
    issue = client.get("/api/issues").json()["items"][0]

    res = client.patch(f"/api/issues/{issue['id']}/status", json={"status": "not-a-real-status"})
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_status"


def test_update_issue_status_not_found(auth_client):
    client, _org = auth_client
    res = client.patch("/api/issues/does-not-exist/status", json={"status": "fixed"})
    assert res.status_code == 404


def test_get_issue_not_found(auth_client):
    client, _org = auth_client
    res = client.get("/api/issues/does-not-exist")
    assert res.status_code == 404


def test_list_issues_severity_and_repository_filters(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    _run_pentest_to_completion(client, repo)

    by_repo = client.get(f"/api/issues?repository_id={repo['id']}").json()
    assert len(by_repo["items"]) > 0

    other_repo = add_repo(client, "acme/other")
    by_other_repo = client.get(f"/api/issues?repository_id={other_repo['id']}").json()
    assert by_other_repo["items"] == []

    any_severity = client.get("/api/issues?severity=critical").json()
    for item in any_severity["items"]:
        assert item["severity"] == "critical"


def test_list_issues_domain_id_filter(auth_client):
    from .conftest import add_domain

    client, _org = auth_client
    domain = add_domain(client)
    client.post(f"/api/domains/{domain['id']}/verify")

    pentest = client.post("/api/pentests", json={"target_type": "domain", "target_id": domain["id"]}).json()
    import time

    deadline = time.time() + 5
    while time.time() < deadline:
        if client.get(f"/api/pentests/{pentest['id']}").json()["status"] == "completed":
            break
        time.sleep(0.02)

    by_domain = client.get(f"/api/issues?domain_id={domain['id']}").json()
    assert len(by_domain["items"]) > 0
    for item in by_domain["items"]:
        assert item["domain_id"] == domain["id"]

    other_domain = add_domain(client, "other.example.com")
    by_other = client.get(f"/api/issues?domain_id={other_domain['id']}").json()
    assert by_other["items"] == []


def test_list_issues_pentest_id_filter(auth_client):
    client, _org = auth_client
    repo_a = add_repo(client, "acme/widgets")
    repo_b = add_repo(client, "acme/gadgets")
    pentest_a = _run_pentest_to_completion(client, repo_a)
    pentest_b = _run_pentest_to_completion(client, repo_b)

    by_pentest_a = client.get(f"/api/issues?pentest_id={pentest_a['id']}").json()
    assert len(by_pentest_a["items"]) > 0
    assert all(i["pentest_id"] == pentest_a["id"] for i in by_pentest_a["items"])

    by_pentest_b = client.get(f"/api/issues?pentest_id={pentest_b['id']}").json()
    assert all(i["pentest_id"] == pentest_b["id"] for i in by_pentest_b["items"])
    assert set(i["id"] for i in by_pentest_a["items"]).isdisjoint(i["id"] for i in by_pentest_b["items"])


def test_list_issues_pentest_id_filter_no_match(auth_client):
    client, _org = auth_client
    repo = add_repo(client)
    _run_pentest_to_completion(client, repo)

    res = client.get("/api/issues?pentest_id=does-not-exist").json()
    assert res["items"] == []


def test_severity_and_status_counts_scoped_to_repository_filter(auth_client):
    """The summary strip / status tabs must reflect the filtered repo, not
    the whole org — otherwise picking a repo filter would narrow the list
    while the counts above it stayed at the org-wide totals."""
    client, _org = auth_client
    repo_a = add_repo(client, "acme/widgets")
    repo_b = add_repo(client, "acme/gadgets")
    _run_pentest_to_completion(client, repo_a)
    _run_pentest_to_completion(client, repo_b)

    org_wide = client.get("/api/issues").json()
    scoped = client.get(f"/api/issues?repository_id={repo_a['id']}").json()

    assert sum(scoped["severity_counts"].values()) == len(scoped["items"])
    assert scoped["status_counts"]["all"] == len(scoped["items"])
    assert scoped["status_counts"]["all"] < org_wide["status_counts"]["all"]


def test_severity_and_status_counts_scoped_to_pentest_filter(auth_client):
    client, _org = auth_client
    repo_a = add_repo(client, "acme/widgets")
    repo_b = add_repo(client, "acme/gadgets")
    pentest_a = _run_pentest_to_completion(client, repo_a)
    _run_pentest_to_completion(client, repo_b)

    scoped = client.get(f"/api/issues?pentest_id={pentest_a['id']}").json()
    assert sum(scoped["severity_counts"].values()) == len(scoped["items"])
    assert scoped["status_counts"]["all"] == len(scoped["items"])


def test_severity_and_status_counts_correct_across_multiple_scans(auth_client):
    """Regression check for the 3x-full-scan -> grouped-aggregate refactor:
    counts must stay accurate once issues span several severities and one
    gets moved to a status excluded from severity_counts."""
    client, _org = auth_client
    repo_a = add_repo(client, "acme/widgets")
    repo_b = add_repo(client, "acme/gadgets")
    _run_pentest_to_completion(client, repo_a)
    _run_pentest_to_completion(client, repo_b)

    all_items = client.get("/api/issues").json()
    # Cross-check: severity_counts total (open+in_progress+snoozed, i.e. not
    # fixed/ignored) matches len(items) when no status filter narrows them,
    # since a fresh scan's issues all start "open".
    total_severity = sum(all_items["severity_counts"].values())
    assert total_severity == len(all_items["items"])
    assert total_severity > 0

    # Move one issue to "fixed" and confirm both aggregates update together
    # and stay internally consistent.
    issue_id = all_items["items"][0]["id"]
    client.patch(f"/api/issues/{issue_id}/status", json={"status": "fixed"})

    after = client.get("/api/issues").json()
    assert after["status_counts"]["fixed"] == 1
    assert after["status_counts"]["all"] == len(all_items["items"])
    assert sum(after["severity_counts"].values()) == total_severity - 1
