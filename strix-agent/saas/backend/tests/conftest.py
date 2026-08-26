from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

# Environment must be set before any `app.*` module is imported, since
# Settings() (app/settings.py) reads env vars once at import time and
# app/db.py builds its engine from settings.database_url at import time.
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SAAS_DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ["SAAS_DEV_MODE"] = "1"
os.environ["SAAS_SESSION_SECRET"] = "test-secret"
os.environ["SAAS_CREDENTIALS_ENCRYPTION_KEY"] = "test-encryption-key"
os.environ["SAAS_FRONTEND_ORIGIN"] = "http://testserver"
os.environ["SAAS_MOCK_SCAN_MIN_SECONDS"] = "0.01"
os.environ["SAAS_MOCK_SCAN_MAX_SECONDS"] = "0.02"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    # `with` triggers the app's lifespan (init_db + starts the pentest job
    # worker), which subsequent requests in the same block rely on.
    with TestClient(app) as c:
        yield c


def otp_login(client: TestClient, email: str = "user@example.com") -> str:
    start = client.post("/api/auth/otp/start", json={"email": email})
    code = start.json()["dev_code"]
    verify = client.post("/api/auth/otp/verify", json={"email": email, "code": code})
    assert verify.status_code == 200, verify.text
    csrf = client.cookies.get("csrf_token")
    if csrf:
        client.headers.update({"x-csrf-token": csrf})
    return code


def create_org(client: TestClient, name: str = "Acme") -> dict:
    res = client.post("/api/orgs", json={"name": name})
    assert res.status_code == 200, res.text
    org = res.json()
    switch = client.post("/api/auth/switch-org", json={"org_id": org["id"]})
    assert switch.status_code == 200, switch.text
    return org


@pytest.fixture
def auth_client(client: TestClient) -> tuple[TestClient, dict]:
    """A TestClient logged in as a fresh user with a fresh org as admin."""
    otp_login(client)
    org = create_org(client)
    return client, org


def add_repo(client: TestClient, full_name: str = "acme/widgets") -> dict:
    res = client.post("/api/repositories", json={"full_name": full_name})
    assert res.status_code == 200, res.text
    return res.json()


def add_domain(client: TestClient, hostname: str = "app.example.com") -> dict:
    res = client.post("/api/domains", json={"hostname": hostname})
    assert res.status_code == 200, res.text
    return res.json()


def add_member(client: TestClient, org: dict, email: str = "member@example.com") -> None:
    """Invites `email` into `org` as a plain member, logs in as them, and
    switches to that org — leaving `client` authenticated as a non-admin
    member of `org` (the caller must already be an admin of `org`)."""
    invite = client.post("/api/members/invitations", json={"email": email, "role": "member"})
    assert invite.status_code == 200, invite.text
    token = invite.json()["dev_accept_token"]

    otp_login(client, email)
    accept = client.post("/api/members/invitations/accept", json={"token": token})
    assert accept.status_code == 200, accept.text
    switch = client.post("/api/auth/switch-org", json={"org_id": org["id"]})
    assert switch.status_code == 200, switch.text
