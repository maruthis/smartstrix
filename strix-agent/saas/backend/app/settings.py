from __future__ import annotations

import sys

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SESSION_SECRET = "dev-insecure-secret-change-me"
_INSECURE_ENCRYPTION_KEY = "dev-insecure-encryption-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAAS_", extra="ignore")

    database_url: str = "sqlite:///./strix_saas.db"
    # Insecure by default on purpose (see the validator below): there's no
    # email provider wired up yet (CONFIG.md), so dev_mode is what makes
    # OTP login and member invitations usable at all locally — it hands
    # the OTP code / invite token straight back in the API response
    # instead of emailing it (auth.py, members.py), and it turns off the
    # session cookie's Secure flag for plain-HTTP local dev (auth.py).
    # Neither is acceptable outside local development.
    dev_mode: bool = True
    session_cookie_name: str = "strix_saas_session"
    session_secret: str = _INSECURE_SESSION_SECRET
    frontend_origin: str = "http://localhost:5173"

    # Encrypts real integration credentials (GitHub/GitLab personal access
    # tokens) at rest — see app/crypto.py. Any string works as input (it's
    # hashed into a valid Fernet key), but change this for any non-local
    # deployment, same as session_secret.
    credentials_encryption_key: str = _INSECURE_ENCRYPTION_KEY

    enable_real_scan: bool = False
    mock_scan_min_seconds: float = 4.0
    mock_scan_max_seconds: float = 8.0
    max_queued_jobs: int = 100

    github_app_id: str | None = None
    github_app_private_key: str | None = None
    github_webhook_secret: str | None = None

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    @property
    def github_configured(self) -> bool:
        return bool(self.github_app_id and self.github_app_private_key)

    @property
    def billing_configured(self) -> bool:
        return bool(self.stripe_secret_key)

    @model_validator(mode="after")
    def _enforce_secrets(self) -> "Settings":
        """Two enforcement levels, since there's no way to tell "still the
        local dev scaffold" apart from "deployed and misconfigured" from
        inside this class alone:

        - `dev_mode=false` with an unchanged secret is unambiguous — the
          operator explicitly said this isn't dev mode, so still shipping
          with a public, hardcoded secret can only be an oversight. This
          refuses to start rather than silently running with a
          decryptable credential store / forgeable session cookies.
        - `dev_mode=true` (the default) can't be refused the same way —
          it's also what makes local dev/CI usable with no email provider
          — so this instead prints a startup banner too loud to miss,
          since nothing else in this codebase currently checks it (see
          the enterprise-architecture review this closes out).
        """
        insecure = []
        if self.session_secret == _INSECURE_SESSION_SECRET:
            insecure.append("SAAS_SESSION_SECRET")
        if self.credentials_encryption_key == _INSECURE_ENCRYPTION_KEY:
            insecure.append("SAAS_CREDENTIALS_ENCRYPTION_KEY")

        if not self.dev_mode:
            if insecure:
                raise ValueError(
                    "Refusing to start with SAAS_DEV_MODE=false and insecure default "
                    f"secret(s) still set: {', '.join(insecure)}. Set real values via "
                    "environment variables before deploying outside local development."
                )
            return self

        if insecure:
            print(  # noqa: T201 - deliberately bypasses logging: must be unmissable regardless of log config
                "\n"
                "!" * 78 + "\n"
                "!! SAAS_DEV_MODE=true (the default) with insecure default secret(s):\n"
                f"!!   {', '.join(insecure)}\n"
                "!! Session cookies are missing the Secure flag, OTP codes and invite\n"
                "!! tokens are returned directly in API responses, and stored\n"
                "!! GitHub/GitLab credentials are trivially decryptable from a DB leak.\n"
                "!! This is fine for local development only. Set SAAS_DEV_MODE=false and\n"
                "!! real SAAS_SESSION_SECRET / SAAS_CREDENTIALS_ENCRYPTION_KEY values for\n"
                "!! any shared, staging, or production deployment.\n" + "!" * 78 + "\n",
                file=sys.stderr,
            )
        return self


settings = Settings()
