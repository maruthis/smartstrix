from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .time_utils import utcnow


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return utcnow()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------
# Org / auth
# --------------------------------------------------------------------------


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="organization", uselist=False, cascade="all, delete-orphan")
    pr_review_settings: Mapped["PRReviewSettings | None"] = relationship(back_populates="organization", uselist=False, cascade="all, delete-orphan")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, default="")
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String, default="admin")  # admin | member

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Session_(TimestampMixin, Base):
    """Server-side session token backing the auth cookie."""

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    active_org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    # Absolute server-side expiry, set at creation to match the cookie's own
    # max_age (see auth.py's _set_session_cookie) — without this, the
    # server accepted a session token forever regardless of the cookie's
    # client-side max_age, so a leaked token had unbounded blast radius.
    # Nullable only so a row seeded directly in a test/migration without
    # setting it doesn't crash current_session(); every session created
    # through auth.py always sets it.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OtpCode(TimestampMixin, Base):
    __tablename__ = "otp_codes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String, index=True)
    code: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Invitation(TimestampMixin, Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="member")
    token: Mapped[str] = mapped_column(String, default=lambda: uuid.uuid4().hex)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow() + timedelta(days=7))


# --------------------------------------------------------------------------
# Assets: repositories & domains
# --------------------------------------------------------------------------


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String, default="github")
    full_name: Mapped[str] = mapped_column(String)  # e.g. "maruthis/anything-llm"
    default_branch: Mapped[str] = mapped_column(String, default="main")
    auto_review_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    installation_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Domain(TimestampMixin, Base):
    __tablename__ = "domains"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    hostname: Mapped[str] = mapped_column(String)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_method: Mapped[str] = mapped_column(String, default="dns_txt")  # dns_txt | file
    verification_token: Mapped[str] = mapped_column(String, default=lambda: f"strix-verify={uuid.uuid4().hex}")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------
# Pentests
# --------------------------------------------------------------------------


class PentestSchedule(TimestampMixin, Base):
    __tablename__ = "pentest_schedules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_type: Mapped[str] = mapped_column(String)  # repository | domain
    target_id: Mapped[str] = mapped_column(String)
    scan_mode: Mapped[str] = mapped_column(String, default="deep")
    cron_expr: Mapped[str] = mapped_column(String, default="0 0 * * 0")  # weekly default
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Standards coverage maps to preload on the root agent (names from
    # app/standard_skills.py). Empty/null is treated as ["owasp_top_10"].
    skills: Mapped[list] = mapped_column(JSON, default=list)
    # Set on create/re-enable and after every fire by app/scheduler.py; a
    # schedule with next_run_at in the past and enabled=True is due.
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Pentest(TimestampMixin, Base):
    __tablename__ = "pentests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    target_type: Mapped[str] = mapped_column(String)  # repository | domain
    target_id: Mapped[str] = mapped_column(String)
    target_label: Mapped[str] = mapped_column(String, default="")
    # Only meaningful when target_type == "repository": an optional verified
    # Domain to also test live/dynamically in the same run, alongside the
    # source-only (whitebox) scan of the repository — e.g. auth flows, CORS,
    # cookie flags, and other findings that only exist on a deployed
    # instance and can't be seen from source alone.
    extra_domain_id: Mapped[str | None] = mapped_column(ForeignKey("domains.id"), nullable=True)
    # Only meaningful when target_type == "repository": the branch, tag, or
    # commit SHA the caller asked to scan. Falls back to the repository's
    # default_branch when unset. `ref` is what was requested (often a
    # moving branch name); `resolved_commit_sha` is filled in once cloned
    # with the exact commit that was actually scanned, so re-running "the
    # same" pentest later — or comparing two runs — is reproducible instead
    # of silently depending on whatever HEAD happened to be at trigger time.
    ref: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_commit_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    scan_mode: Mapped[str] = mapped_column(String, default="deep")
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|running|completed|failed|stopped
    schedule_id: Mapped[str | None] = mapped_column(ForeignKey("pentest_schedules.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    severity_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_total_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Standards coverage maps preloaded on the root agent. See
    # app/standard_skills.py. Empty/null is treated as ["owasp_top_10"].
    skills: Mapped[list] = mapped_column(JSON, default=list)
    # Free-text instruction to fold into the scan's root task (e.g. from a
    # Chat-triggered scan) — passed through to strix as scan_config's
    # "user_instructions" (see strix/core/inputs.py's build_root_task).
    # None/empty for a normal New Pentest, which has no such input.
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Historical: set when SAAS_ENABLE_REAL_SCAN=1 and the real engine
    # raised, causing an older _scan() to substitute canned findings.
    # New real-scan failures fail closed instead. Null for a genuine
    # completed real scan and for an intentional mock (real scan off).
    mock_fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Compact coverage / agent-graph summary persisted after a scan so the
    # UI can lead with what was not tested. See app/coverage_summary.py.
    coverage: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# --------------------------------------------------------------------------
# Issues
# --------------------------------------------------------------------------


class Issue(TimestampMixin, Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    pentest_id: Mapped[str | None] = mapped_column(ForeignKey("pentests.id"), nullable=True)
    pr_review_id: Mapped[str | None] = mapped_column(ForeignKey("pr_reviews.id"), nullable=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"), nullable=True)
    domain_id: Mapped[str | None] = mapped_column(ForeignKey("domains.id"), nullable=True)

    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String)  # critical|high|medium|low
    status: Mapped[str] = mapped_column(String, default="open")  # open|in_progress|snoozed|fixed|ignored
    cvss: Mapped[float | None] = mapped_column(Float, nullable=True)
    cvss_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    technical_analysis: Mapped[str] = mapped_column(Text, default="")
    remediation_steps: Mapped[str] = mapped_column(Text, default="")
    poc_description: Mapped[str] = mapped_column(Text, default="")
    poc_script_code: Mapped[str] = mapped_column(Text, default="")
    code_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[str] = mapped_column(String, default="")
    endpoint: Mapped[str] = mapped_column(String, default="")
    fix_effort: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high
    # "baseline_scan" for a Tier 3 deterministic finding; "agent" for an
    # LLM-filed finding; "mock" for the intentional demo scanner;
    # "mock_fallback" only on historical rows from the old fail-open path.
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    # Human triage of the assistant's claim. Independent of workflow
    # status (open/fixed): a finding can be open and still rejected.
    disposition: Mapped[str] = mapped_column(String, default="pending")  # pending|confirmed|rejected|needs_repro|out_of_scope
    disposition_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    specialist_name: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# --------------------------------------------------------------------------
# PR reviews
# --------------------------------------------------------------------------


class PRReview(TimestampMixin, Base):
    __tablename__ = "pr_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    pr_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String, default="")
    author: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="running")
    # running | awaiting_merge | needs_attention | merged_with_open_findings | passed | failed
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    # The PR/MR's base branch, used to diff-scope the real scan against
    # (falls back to the repository's default_branch when not known — e.g.
    # a manually-triggered review with no live PR picker data).
    target_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    # The exact commit that was actually scanned (the PR ref's resolved
    # HEAD at clone time) — same reproducibility rationale as
    # Pentest.resolved_commit_sha.
    resolved_head_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    # Short machine-readable reason when status == "failed" (e.g. a clone
    # or engine failure) — surfaced in the UI instead of a silent stall.
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_total_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PRReviewSettings(Base):
    __tablename__ = "pr_review_settings"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    rereview_on_push: Mapped[bool] = mapped_column(Boolean, default=False)
    target_branches: Mapped[list] = mapped_column(JSON, default=list)
    approve_clean_prs: Mapped[bool] = mapped_column(Boolean, default=False)
    block_prs_on_findings: Mapped[bool] = mapped_column(Boolean, default=True)
    blocking_severities: Mapped[list] = mapped_column(JSON, default=lambda: ["critical", "high"])
    exclude_bot_accounts: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_usernames: Mapped[list] = mapped_column(JSON, default=list)
    allow_overage_reviews: Mapped[bool] = mapped_column(Boolean, default=True)
    review_cap_per_dev: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_cap_period: Mapped[str] = mapped_column(String, default="month")

    organization: Mapped[Organization] = relationship(back_populates="pr_review_settings")


# --------------------------------------------------------------------------
# Knowledge
# --------------------------------------------------------------------------


class KnowledgeEntry(TimestampMixin, Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    type: Mapped[str] = mapped_column(String, default="business_logic")
    description: Mapped[str] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(String, default="global")  # global|repository|domain
    scope_id: Mapped[str | None] = mapped_column(String, nullable=True)


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String, default="New chat")
    category: Mapped[str] = mapped_column(String, default="web")

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # user | assistant
    content: Mapped[str] = mapped_column(Text)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


# --------------------------------------------------------------------------
# API access: tokens & webhooks
# --------------------------------------------------------------------------


class ApiToken(TimestampMixin, Base):
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    token_type: Mapped[str] = mapped_column(String, default="personal")  # personal | service
    scopes: Mapped[list] = mapped_column(JSON, default=lambda: ["read"])
    token_hash: Mapped[str] = mapped_column(String)
    token_prefix: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")  # active | revoked
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Webhook(TimestampMixin, Base):
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    url: Mapped[str] = mapped_column(String)
    events: Mapped[list] = mapped_column(JSON, default=list)
    secret: Mapped[str] = mapped_column(String, default=lambda: uuid.uuid4().hex)
    status: Mapped[str] = mapped_column(String, default="active")


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("org_id", "provider", name="uq_integration_org_provider"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String)  # github | gitlab | bitbucket | slack | jira | linear
    account_label: Mapped[str] = mapped_column(String)
    base_url: Mapped[str | None] = mapped_column(String, nullable=True)  # self-hosted GitLab / GitHub Enterprise
    credential_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)  # app/crypto.py; real API calls decrypt this
    credential_last4: Mapped[str | None] = mapped_column(String, nullable=True)  # display only
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------
# LLM / model provider (per-org)
# --------------------------------------------------------------------------


class OrgLlmSettings(Base):
    """Per-org override for which LLM backs that org's pentests/PR reviews.

    Consumed by jobs.py immediately before invoking the upstream strix
    engine — see the module docstring there for the concurrency caveat:
    strix's LLM config is a process-global singleton, so this only stays
    safe as long as scans run one at a time (see jobs.py's single-worker
    queue), not in parallel across orgs in the same process.
    """

    __tablename__ = "org_llm_settings"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String, default="")  # e.g. "openai/gpt-5.4", litellm-style
    api_base: Mapped[str | None] = mapped_column(String, nullable=True)
    # Fernet-encrypted by app/crypto.py. Legacy plaintext rows are tolerated
    # by readers so existing local databases can migrate on next update.
    api_key: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# --------------------------------------------------------------------------
# Audit & billing
# --------------------------------------------------------------------------


class AuditLogEntry(TimestampMixin, Base):
    __tablename__ = "audit_log_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String)
    target: Mapped[str] = mapped_column(String, default="")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class RequestLogEntry(TimestampMixin, Base):
    """Best-effort HTTP activity log, written by app.middleware.RequestLogMiddleware.

    Only mutating requests (non-GET) and error responses (status >= 400) are
    recorded — logging every routine polling GET would flood this table with
    near-zero audit value (e.g. the pentest list alone polls every 4s per
    open tab).
    """

    __tablename__ = "request_log_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    method: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)


class Subscription(Base):
    __tablename__ = "subscriptions"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    plan: Mapped[str] = mapped_column(String, default="pro_trial")
    status: Mapped[str] = mapped_column(String, default="trialing")  # trialing|active|canceled
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    card_added: Mapped[bool] = mapped_column(Boolean, default=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="subscription")
