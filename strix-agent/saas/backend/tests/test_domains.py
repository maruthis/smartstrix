import pytest

from .conftest import add_domain, add_member


def test_list_domains_empty(auth_client):
    client, _org = auth_client
    assert client.get("/api/domains").json() == []


def test_add_domain_conflict(auth_client):
    client, _org = auth_client
    add_domain(client, "app.example.com")
    res = client.post("/api/domains", json={"hostname": "app.example.com"})
    assert res.status_code == 409
    assert res.json()["detail"] == "already_added"


def test_get_domain(auth_client):
    client, _org = auth_client
    domain = add_domain(client)
    res = client.get(f"/api/domains/{domain['id']}")
    assert res.status_code == 200
    assert res.json()["hostname"] == domain["hostname"]


def test_get_domain_not_found(auth_client):
    client, _org = auth_client
    res = client.get("/api/domains/does-not-exist")
    assert res.status_code == 404


def test_scan_blocked_until_verified(auth_client):
    client, _org = auth_client
    domain = add_domain(client)

    res = client.post(f"/api/domains/{domain['id']}/scan")
    assert res.status_code == 400
    assert res.json()["detail"] == "domain_not_verified"

    verify = client.post(f"/api/domains/{domain['id']}/verify")
    assert verify.status_code == 200
    assert verify.json()["verified"] is True

    res = client.post(f"/api/domains/{domain['id']}/scan")
    assert res.status_code == 200
    assert "pentest_id" in res.json()


def test_scan_domain_not_found(auth_client):
    client, _org = auth_client
    res = client.post("/api/domains/does-not-exist/scan")
    assert res.status_code == 404


def test_remove_domain(auth_client):
    client, _org = auth_client
    domain = add_domain(client)
    res = client.request("DELETE", f"/api/domains/{domain['id']}")
    assert res.status_code == 200
    assert client.get("/api/domains").json() == []


def test_remove_domain_not_found(auth_client):
    client, _org = auth_client
    res = client.request("DELETE", "/api/domains/does-not-exist")
    assert res.status_code == 404


def test_verify_domain_not_found(auth_client):
    client, _org = auth_client
    res = client.post("/api/domains/does-not-exist/verify")
    assert res.status_code == 404


def test_verify_domain_checks_txt_records_outside_dev_mode(auth_client, monkeypatch):
    import app.routers.domains as domains

    client, _org = auth_client
    domain = add_domain(client)
    monkeypatch.setattr(domains.settings, "dev_mode", False)
    monkeypatch.setattr(domains, "_txt_values", lambda hostname: [])

    failed = client.post(f"/api/domains/{domain['id']}/verify")
    assert failed.status_code == 400
    assert failed.json()["detail"] == "domain_verification_failed"

    monkeypatch.setattr(domains, "_txt_values", lambda hostname: [domain["verification_token"]])
    verified = client.post(f"/api/domains/{domain['id']}/verify")
    assert verified.status_code == 200
    assert verified.json()["verified"] is True


def test_remove_domain_requires_admin_but_add_verify_scan_dont(auth_client):
    client, org = auth_client
    domain = add_domain(client)
    add_member(client, org)

    remove = client.request("DELETE", f"/api/domains/{domain['id']}")
    assert remove.status_code == 403
    assert remove.json()["detail"] == "admin_required"

    # Everyday usage actions stay member-accessible.
    assert client.post("/api/domains", json={"hostname": "member-added.example.com"}).status_code == 200
    assert client.post(f"/api/domains/{domain['id']}/verify").status_code == 200
    assert client.post(f"/api/domains/{domain['id']}/scan").status_code == 200


@pytest.mark.parametrize(
    "hostname",
    [
        "127.0.0.1",
        "169.254.169.254",
        "10.0.0.1",
        "localhost",
        "metadata.google.internal",
        "evil.example.com@169.254.169.254",
        "https://evil.example.com@169.254.169.254",
    ],
)
def test_add_domain_rejects_internal_or_malformed_hostnames(auth_client, hostname):
    client, _org = auth_client
    res = client.post("/api/domains", json={"hostname": hostname})
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid_hostname"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://dev-stag-agui.techsophy.com/", "dev-stag-agui.techsophy.com"),
        ("https://APP.Example.COM/path?q=1", "app.example.com"),
        ("http://app.example.com:443/", "app.example.com"),
        ("app.example.com/", "app.example.com"),
        ("app.example.com/redirect", "app.example.com"),
    ],
)
def test_add_domain_accepts_a_pasted_url_and_stores_the_hostname(auth_client, raw, expected):
    client, _org = auth_client
    res = client.post("/api/domains", json={"hostname": raw})
    assert res.status_code == 200
    assert res.json()["hostname"] == expected


def test_file_verification_rejects_hosts_that_resolve_privately(auth_client, monkeypatch):
    import app.routers.domains as domains

    client, _org = auth_client
    domain = client.post("/api/domains", json={"hostname": "app.example.com", "verification_method": "file"}).json()
    monkeypatch.setattr(domains.settings, "dev_mode", False)
    monkeypatch.setattr(domains, "hostname_resolves_public", lambda _hostname: False)
    res = client.post(f"/api/domains/{domain['id']}/verify")
    assert res.status_code == 400
    assert res.json()["detail"] == "domain_verification_failed"
