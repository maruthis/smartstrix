from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..deps import current_org, current_user, db_dep, optional_current_user, require_admin
from ..public_hosts import hostname_resolves_public, normalize_public_hostname
from ..settings import settings
from ..audit import record_audit as _record_audit
from .pentests import create_and_enqueue_pentest

router = APIRouter(prefix="/api/domains", tags=["domains"])


def _serialize(d: models.Domain) -> dict:
    return {
        "id": d.id,
        "hostname": d.hostname,
        "verified": d.verified,
        "verification_method": d.verification_method,
        "verification_token": d.verification_token,
        "last_tested_at": d.last_tested_at.isoformat() if d.last_tested_at else None,
    }


def _txt_values(hostname: str) -> list[str]:
    try:
        import dns.resolver  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="dns_verification_unavailable") from exc

    values: list[str] = []
    for name in (f"_strix.{hostname}", hostname):
        try:
            answers = dns.resolver.resolve(name, "TXT")
        except Exception:  # noqa: BLE001 - DNS negative answers just mean "not verified"
            continue
        for answer in answers:
            strings = getattr(answer, "strings", None)
            if strings:
                values.append("".join(part.decode() if isinstance(part, bytes) else str(part) for part in strings))
            else:
                values.append(str(answer).strip('"'))
    return values


def _well_known_body(hostname: str) -> str:
    host = normalize_public_hostname(hostname)
    if not hostname_resolves_public(host):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="domain_verification_failed")
    url = f"https://{host}/.well-known/strix-verification.txt"
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text[:4096]
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="domain_verification_failed") from exc


def _domain_token_present(domain: models.Domain) -> bool:
    if settings.dev_mode:
        return True
    token = domain.verification_token
    if domain.verification_method == "dns_txt":
        return token in _txt_values(domain.hostname)
    if domain.verification_method in {"file", "http_file"}:
        return token in _well_known_body(domain.hostname).splitlines()
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unsupported_verification_method")


@router.get("")
def list_domains(org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> list[dict]:
    domains = db.query(models.Domain).filter_by(org_id=org.id).order_by(models.Domain.created_at.desc()).all()
    return [_serialize(d) for d in domains]


@router.get("/{domain_id}")
def get_domain(domain_id: str, org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> dict:
    domain = db.get(models.Domain, domain_id)
    if not domain or domain.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return _serialize(domain)


class AddDomainIn(BaseModel):
    hostname: str
    verification_method: str = "dns_txt"


@router.post("")
def add_domain(
    body: AddDomainIn,
    org: models.Organization = Depends(current_org),
    user: models.User | None = Depends(optional_current_user),
    db: Session = Depends(db_dep),
) -> dict:
    hostname = normalize_public_hostname(body.hostname)
    existing = db.query(models.Domain).filter_by(org_id=org.id, hostname=hostname).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="already_added")
    domain = models.Domain(org_id=org.id, hostname=hostname, verification_method=body.verification_method)
    db.add(domain)
    db.commit()
    _record_audit(db, org.id, user.id if user else None, "domain.added", domain.hostname)
    return _serialize(domain)


@router.post("/{domain_id}/verify")
def verify_domain(domain_id: str, org: models.Organization = Depends(current_org), db: Session = Depends(db_dep)) -> dict:
    domain = db.get(models.Domain, domain_id)
    if not domain or domain.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if not _domain_token_present(domain):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="domain_verification_failed")
    domain.verified = True
    db.commit()
    return _serialize(domain)


@router.delete("/{domain_id}")
def remove_domain(
    domain_id: str,
    org: models.Organization = Depends(current_org),
    _admin=Depends(require_admin),
    db: Session = Depends(db_dep),
) -> dict:
    domain = db.get(models.Domain, domain_id)
    if not domain or domain.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    db.delete(domain)
    db.commit()
    return {"ok": True}


@router.post("/{domain_id}/scan")
async def trigger_scan(
    domain_id: str,
    org: models.Organization = Depends(current_org),
    user: models.User | None = Depends(optional_current_user),
    db: Session = Depends(db_dep),
) -> dict:
    domain = db.get(models.Domain, domain_id)
    if not domain or domain.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if not domain.verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="domain_not_verified")
    pentest = await create_and_enqueue_pentest(db, org, user, "domain", domain_id)
    return {"pentest_id": pentest.id}
