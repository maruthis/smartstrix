"""VAPT-style HTML/PDF report generation for a completed Pentest."""

from __future__ import annotations

from html import escape
from io import BytesIO

from . import models

SEVERITY_ORDER = ["critical", "high", "medium", "low"]

SEVERITY_COLORS = {
    "critical": "#c0392b",
    "high": "#c2540c",
    "medium": "#c98a1f",
    "low": "#b7a500",
}

# Likelihood/Impact heuristic used when the underlying Issue has no explicit
# CVSS vector to derive them from — mirrors how the severity was assigned.
SEVERITY_RISK_IMPACT = {
    "critical": ("Critical", "High", "Critical"),
    "high": ("High", "Medium", "High"),
    "medium": ("Medium", "Medium", "Medium"),
    "low": ("Low", "Low", "Low"),
}

STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In Progress",
    "snoozed": "Snoozed",
    "fixed": "Fixed",
    "ignored": "Ignored / Accepted Risk",
}


def _vid(index: int) -> str:
    return f"V-{index:02d}"


def _fmt_month(dt) -> str:
    return dt.strftime("%B %Y") if dt else "N/A"


def _counts(issues: list[models.Issue]) -> dict[str, int]:
    counts = {s: 0 for s in SEVERITY_ORDER}
    for issue in issues:
        if issue.severity in counts:
            counts[issue.severity] += 1
    return counts


def _posture(counts: dict[str, int]) -> str:
    if counts.get("critical"):
        return "Weak"
    if counts.get("high"):
        return "Weak"
    if counts.get("medium"):
        return "Moderate"
    if counts.get("low"):
        return "Good"
    return "Strong"


def _esc(value: str | None) -> str:
    return escape(value or "").replace("\n", "<br/>")


def _summary_bar(counts: dict[str, int]) -> str:
    total = max(sum(counts.values()), 1)
    rows = []
    for sev in SEVERITY_ORDER:
        count = counts.get(sev, 0)
        width = round((count / total) * 100)
        rows.append(
            f"""
            <div class="bar-row">
              <span class="bar-label">{sev.capitalize()}</span>
              <div class="bar-track">
                <div class="bar-fill" style="width:{width}%;background:{SEVERITY_COLORS[sev]}"></div>
              </div>
              <span class="bar-count">{count}</span>
            </div>
            """
        )
    return "\n".join(rows)


def _finding_row(index: int, issue: models.Issue) -> str:
    color = SEVERITY_COLORS.get(issue.severity, "#888")
    return f"""
    <tr>
      <td>{_vid(index)}</td>
      <td>{_esc(issue.title)}</td>
      <td style="color:{color};font-weight:600">{issue.severity.capitalize()}</td>
      <td>{STATUS_LABELS.get(issue.status, issue.status.capitalize())}</td>
    </tr>
    """


def _finding_detail(index: int, issue: models.Issue) -> str:
    likelihood, impact_label, impact = SEVERITY_RISK_IMPACT.get(
        issue.severity, ("Medium", "Medium", "Medium")
    )
    observation = issue.description or issue.technical_analysis or "No further detail was recorded for this finding."
    business_impact = issue.technical_analysis or "Exploitation may lead to unauthorized access, data exposure, or service disruption depending on deployment context."
    recommendation = issue.remediation_steps or "Review and remediate per the applicable secure-coding guidance for this class of issue."
    impacted_assets = issue.target or issue.endpoint or "See Observation for affected component."
    poc = issue.poc_description or issue.poc_script_code or "Not applicable / not captured for this finding."
    cvss = f"{issue.cvss:.1f}" if issue.cvss is not None else "N/A"

    return f"""
    <div class="finding-block">
      <h3>{_vid(index)} - {_esc(issue.title)}</h3>
      <table class="detail-table">
        <tr><th>V-ID</th><td>{_vid(index)}</td></tr>
        <tr><th>Name of the Vulnerability</th><td>{_esc(issue.title)}</td></tr>
        <tr><th>Risk</th><td style="color:{SEVERITY_COLORS.get(issue.severity, '#888')};font-weight:600">{issue.severity.capitalize()}</td></tr>
        <tr><th>Likelihood</th><td>{likelihood}</td></tr>
        <tr><th>Impact</th><td>{impact}</td></tr>
        <tr><th>CVSS Score</th><td>{cvss}</td></tr>
        <tr><th>Current Status</th><td>{STATUS_LABELS.get(issue.status, issue.status.capitalize())}</td></tr>
        <tr><th>Observation</th><td>{_esc(observation)}</td></tr>
        <tr><th>Risk / Business Impact</th><td>{_esc(business_impact)}</td></tr>
        <tr><th>Recommendation</th><td>{_esc(recommendation)}</td></tr>
        <tr><th>Impacted Assets</th><td>{_esc(impacted_assets)}</td></tr>
        <tr><th>Proof Of Concept</th><td>{_esc(poc)}</td></tr>
      </table>
    </div>
    """


_BEST_PRACTICES = [
    (
        "Secrets and Credential Management",
        "Store secrets in a dedicated vault (e.g. AWS Secrets Manager, HashiCorp Vault). Never commit API keys, "
        "tokens, or passwords to source control, and rotate immediately anything that ever reached a repository.",
    ),
    (
        "Dependency and Supply Chain Security",
        "Run automated dependency audits on every pull request and fail the build on High/Critical advisories. "
        "Track upstream security releases and avoid abandoned or unmaintained packages.",
    ),
    (
        "Injection Prevention",
        "Use parameterized queries exclusively, encode output for its rendering context, and never pass "
        "untrusted input to a shell, deserializer, or template engine without sanitization.",
    ),
    (
        "Authentication and Session Management",
        "Enforce short-lived tokens with rotation, strong password hashing (Argon2id/bcrypt), account lockout "
        "after repeated failures, and secure cookie flags (HttpOnly, Secure, SameSite).",
    ),
    (
        "Access Control",
        "Verify authorization server-side on every request using an explicit allow-list of fields and actions; "
        "never trust client-supplied roles, IDs, or ownership claims.",
    ),
    (
        "Secure Configuration and Headers",
        "Enforce HTTPS with HSTS, deploy a Content-Security-Policy, and remove development artifacts "
        "(debug endpoints, source maps, default credentials) from production builds.",
    ),
    (
        "Logging and Monitoring",
        "Log authentication events, authorization failures, and administrative actions with enough context "
        "to support incident response, while redacting credentials and PII before they are written.",
    ),
]


def render_report_html(pentest: models.Pentest, issues: list[models.Issue], org: models.Organization) -> str:
    counts = _counts(issues)
    total = sum(counts.values())
    posture = _posture(counts)
    posture_color = {"Weak": "#c0392b", "Moderate": "#c98a1f", "Good": "#2e7d32", "Strong": "#2e7d32"}[posture]
    sorted_issues = sorted(
        issues,
        key=lambda i: (SEVERITY_ORDER.index(i.severity) if i.severity in SEVERITY_ORDER else 99, i.title),
    )

    snapshot_rows = "\n".join(_finding_row(i, issue) for i, issue in enumerate(sorted_issues, start=1))
    detail_blocks = "\n".join(_finding_detail(i, issue) for i, issue in enumerate(sorted_issues, start=1))
    target_kind = "Repository" if pentest.target_type == "repository" else "Domain / Web Application"
    scope_desc = (
        "Source Code Analysis (SAST, SCA)" if pentest.target_type == "repository" else "Dynamic Application Analysis (DAST)"
    )

    findings_or_none = (
        f"""
        <div class="chart">{_summary_bar(counts)}</div>
        <table class="std-table">
          <tr><th>VID</th><th>Name of the Vulnerability</th><th>Severity</th><th>Current Status</th></tr>
          {snapshot_rows}
        </table>
        """
        if issues
        else '<p class="muted">No vulnerabilities were identified during this engagement.</p>'
    )

    details_or_none = detail_blocks if issues else ""

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>{_esc(pentest.target_label)} - Pentest Report</title>
<style>
  @page {{ size: A4; margin: 2.2cm 1.8cm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Helvetica, Arial, sans-serif; color: #1a1a1a; font-size: 12px; line-height: 1.5; }}
  h1 {{ font-size: 26px; color: #1d4ed8; margin-bottom: 4px; }}
  h2 {{ font-size: 18px; color: #1d4ed8; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin-top: 32px; }}
  h3 {{ font-size: 14px; color: #1d4ed8; margin-top: 20px; margin-bottom: 6px; }}
  .cover {{ text-align: center; padding-top: 120px; }}
  .cover .brand {{ font-size: 13px; letter-spacing: 2px; color: #888; text-transform: uppercase; }}
  .cover h1 {{ font-size: 30px; margin-top: 24px; }}
  .cover .meta {{ margin-top: 60px; font-size: 13px; color: #444; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 18px; }}
  .std-table th, .std-table td, .exec-table th, .exec-table td, .detail-table th, .detail-table td {{
    border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; font-size: 11px;
  }}
  .std-table th {{ background: #f2f4f8; }}
  .exec-table th {{ width: 26%; background: #f2f4f8; }}
  .detail-table th {{ width: 24%; background: #f7f7f7; font-weight: 600; }}
  .finding-block {{ page-break-inside: avoid; margin-bottom: 10px; }}
  .chart {{ margin: 14px 0 20px; }}
  .bar-row {{ display: flex; align-items: center; margin-bottom: 6px; }}
  .bar-label {{ width: 70px; font-size: 11px; }}
  .bar-track {{ flex: 1; background: #eee; height: 14px; border-radius: 3px; overflow: hidden; }}
  .bar-fill {{ height: 100%; }}
  .bar-count {{ width: 30px; text-align: right; font-size: 11px; }}
  .muted {{ color: #666; }}
  .posture {{ font-weight: 700; }}
  .footer-note {{ margin-top: 40px; font-size: 10px; color: #999; }}
</style>
</head>
<body>

<div class="cover">
  <div class="brand">Vulnerability Assessment &amp; Penetration Testing Report</div>
  <h1>{_esc(pentest.target_label)}</h1>
  <div class="meta">
    Prepared for: {_esc(org.name)}<br/>
    Prepared by: Strix Security<br/>
    Report Date: {_fmt_month(pentest.finished_at or pentest.created_at)}<br/>
    Pentest ID: {pentest.id}
  </div>
</div>

<div style="page-break-before: always;"></div>

<h2>Executive Summary</h2>
<p>This section summarizes the VAPT engagement against {_esc(pentest.target_label)}, highlighting its principal findings and overall security posture.</p>
<table class="exec-table">
  <tr><th>Engagement Date</th><td>{_fmt_month(pentest.started_at or pentest.created_at)}</td></tr>
  <tr><th>Target Systems</th><td>{_esc(pentest.target_label)} ({target_kind})</td></tr>
  <tr><th>Scope</th><td>{scope_desc}</td></tr>
  <tr><th>Scan Mode</th><td>{_esc(pentest.scan_mode.capitalize())}</td></tr>
  <tr><th>Methodology</th><td>This VAPT is conducted following the NIST framework, OWASP Top 10, and industry best practices.</td></tr>
  <tr><th>Overall Security Posture</th><td class="posture" style="color:{posture_color}">{posture}</td></tr>
  <tr><th>Total Findings</th><td>{total} ({counts['critical']} Critical, {counts['high']} High, {counts['medium']} Medium, {counts['low']} Low)</td></tr>
  <tr><th>Recommendations</th><td>Plan to fix the Critical/High/Medium severity vulnerabilities reported at the earliest.</td></tr>
</table>

<h2>Summary of All Findings</h2>
{findings_or_none}

<h2>Vulnerability Details</h2>
{details_or_none}

<h2>Limitations and Exclusions</h2>
<p>This assessment was performed using automated scanning augmented by AI-driven manual analysis, within the scope described above.
Findings reflect the security posture of the target at the time of testing and are not a guarantee against future vulnerabilities.
Business logic testing requiring live operator context, physical security, and social engineering were outside the scope of this engagement.</p>

<h2>Best Practices</h2>
<table class="std-table">
  <tr><th style="width:28%">Area</th><th>Guidance</th></tr>
  {"".join(f"<tr><td><b>{_esc(name)}</b></td><td>{_esc(desc)}</td></tr>" for name, desc in _BEST_PRACTICES)}
</table>

<h2>Conclusion</h2>
<p>{_esc(pentest.target_label)} currently has {counts['critical']} Critical, {counts['high']} High, {counts['medium']} Medium and {counts['low']} Low
severity findings, totalling {total}. It is advisable to prioritize remediation of Critical and High severity findings first, and to
conduct a re-test once remediation is complete.</p>

<h2>Disclaimer</h2>
<p class="muted">This report and its contents are confidential and should be shared only with authorized personnel. Findings are based on the
agreed-upon scope and methodology described above. This report reflects the security posture of the target at the time of testing and is not
a guarantee against all future attacks; new vulnerabilities may emerge and configurations may change.</p>

<div class="footer-note">Generated by Strix &middot; Pentest ID {pentest.id} &middot; {total} finding(s)</div>

</body>
</html>
"""


def render_pr_review_report_html(
    review: models.PRReview, repo: models.Repository, issues: list[models.Issue], org: models.Organization
) -> str:
    """Same report shape as `render_report_html`, adapted for a PR review's
    fields instead of a Pentest's — reuses every finding-rendering helper
    above so the two report types stay visually and structurally
    consistent."""
    counts = _counts(issues)
    total = sum(counts.values())
    posture = _posture(counts)
    posture_color = {"Weak": "#c0392b", "Moderate": "#c98a1f", "Good": "#2e7d32", "Strong": "#2e7d32"}[posture]
    sorted_issues = sorted(
        issues,
        key=lambda i: (SEVERITY_ORDER.index(i.severity) if i.severity in SEVERITY_ORDER else 99, i.title),
    )

    snapshot_rows = "\n".join(_finding_row(i, issue) for i, issue in enumerate(sorted_issues, start=1))
    detail_blocks = "\n".join(_finding_detail(i, issue) for i, issue in enumerate(sorted_issues, start=1))

    pr_label = f"{repo.full_name} #{review.pr_number}"
    base_branch = review.target_branch or repo.default_branch

    findings_or_none = (
        f"""
        <div class="chart">{_summary_bar(counts)}</div>
        <table class="std-table">
          <tr><th>VID</th><th>Name of the Vulnerability</th><th>Severity</th><th>Current Status</th></tr>
          {snapshot_rows}
        </table>
        """
        if issues
        else '<p class="muted">No vulnerabilities were identified in this pull request\'s changes.</p>'
    )

    details_or_none = detail_blocks if issues else ""

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>{_esc(pr_label)} - PR Security Review</title>
<style>
  @page {{ size: A4; margin: 2.2cm 1.8cm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Helvetica, Arial, sans-serif; color: #1a1a1a; font-size: 12px; line-height: 1.5; }}
  h1 {{ font-size: 26px; color: #1d4ed8; margin-bottom: 4px; }}
  h2 {{ font-size: 18px; color: #1d4ed8; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin-top: 32px; }}
  h3 {{ font-size: 14px; color: #1d4ed8; margin-top: 20px; margin-bottom: 6px; }}
  .cover {{ text-align: center; padding-top: 120px; }}
  .cover .brand {{ font-size: 13px; letter-spacing: 2px; color: #888; text-transform: uppercase; }}
  .cover h1 {{ font-size: 30px; margin-top: 24px; }}
  .cover .meta {{ margin-top: 60px; font-size: 13px; color: #444; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 18px; }}
  .std-table th, .std-table td, .exec-table th, .exec-table td, .detail-table th, .detail-table td {{
    border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; font-size: 11px;
  }}
  .std-table th {{ background: #f2f4f8; }}
  .exec-table th {{ width: 26%; background: #f2f4f8; }}
  .detail-table th {{ width: 24%; background: #f7f7f7; font-weight: 600; }}
  .finding-block {{ page-break-inside: avoid; margin-bottom: 10px; }}
  .chart {{ margin: 14px 0 20px; }}
  .bar-row {{ display: flex; align-items: center; margin-bottom: 6px; }}
  .bar-label {{ width: 70px; font-size: 11px; }}
  .bar-track {{ flex: 1; background: #eee; height: 14px; border-radius: 3px; overflow: hidden; }}
  .bar-fill {{ height: 100%; }}
  .bar-count {{ width: 30px; text-align: right; font-size: 11px; }}
  .muted {{ color: #666; }}
  .posture {{ font-weight: 700; }}
  .footer-note {{ margin-top: 40px; font-size: 10px; color: #999; }}
</style>
</head>
<body>

<div class="cover">
  <div class="brand">Pull Request Security Review</div>
  <h1>{_esc(pr_label)}</h1>
  <div class="meta">
    Prepared for: {_esc(org.name)}<br/>
    Prepared by: Strix Security<br/>
    Report Date: {_fmt_month(review.updated_at or review.created_at)}<br/>
    PR Review ID: {review.id}
  </div>
</div>

<div style="page-break-before: always;"></div>

<h2>Executive Summary</h2>
<p>This section summarizes the automated security review of pull request {_esc(pr_label)}, highlighting its principal findings and overall security posture.</p>
<table class="exec-table">
  <tr><th>Review Date</th><td>{_fmt_month(review.created_at)}</td></tr>
  <tr><th>Repository</th><td>{_esc(repo.full_name)}</td></tr>
  <tr><th>Pull Request</th><td>#{review.pr_number} &mdash; {_esc(review.title)}</td></tr>
  <tr><th>Author</th><td>{_esc(review.author)}</td></tr>
  <tr><th>Base Branch</th><td>{_esc(base_branch)}</td></tr>
  <tr><th>Reviewed Commit</th><td>{_esc(review.resolved_head_sha) or "N/A"}</td></tr>
  <tr><th>Scope</th><td>Diff-Scoped Source Code Analysis (SAST, SCA) &mdash; this PR's changed files</td></tr>
  <tr><th>Methodology</th><td>This review is conducted following the NIST framework, OWASP Top 10, and industry best practices.</td></tr>
  <tr><th>Overall Security Posture</th><td class="posture" style="color:{posture_color}">{posture}</td></tr>
  <tr><th>Total Findings</th><td>{total} ({counts['critical']} Critical, {counts['high']} High, {counts['medium']} Medium, {counts['low']} Low)</td></tr>
  <tr><th>Recommendations</th><td>Plan to fix the Critical/High/Medium severity vulnerabilities reported before merging.</td></tr>
</table>

<h2>Summary of All Findings</h2>
{findings_or_none}

<h2>Vulnerability Details</h2>
{details_or_none}

<h2>Limitations and Exclusions</h2>
<p>This review was performed using automated scanning augmented by AI-driven manual analysis, scoped to this pull
request's changed files diffed against {_esc(base_branch)}. Findings reflect the security posture of the PR's
changes at the time of review and are not a guarantee against future vulnerabilities. Issues pre-existing outside
the diff, business logic requiring live operator context, and social engineering were outside the scope of this
review.</p>

<h2>Best Practices</h2>
<table class="std-table">
  <tr><th style="width:28%">Area</th><th>Guidance</th></tr>
  {"".join(f"<tr><td><b>{_esc(name)}</b></td><td>{_esc(desc)}</td></tr>" for name, desc in _BEST_PRACTICES)}
</table>

<h2>Conclusion</h2>
<p>{_esc(pr_label)} currently has {counts['critical']} Critical, {counts['high']} High, {counts['medium']} Medium and {counts['low']} Low
severity findings, totalling {total}. It is advisable to remediate Critical and High severity findings before merging.</p>

<h2>Disclaimer</h2>
<p class="muted">This report and its contents are confidential and should be shared only with authorized personnel. Findings are based on the
agreed-upon scope and methodology described above. This report reflects the security posture of the target at the time of testing and is not
a guarantee against all future attacks; new vulnerabilities may emerge and configurations may change.</p>

<div class="footer-note">Generated by Strix &middot; PR Review ID {review.id} &middot; {total} finding(s)</div>

</body>
</html>
"""


def render_report_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa

    buffer = BytesIO()
    pisa.CreatePDF(src=html, dest=buffer)
    return buffer.getvalue()
