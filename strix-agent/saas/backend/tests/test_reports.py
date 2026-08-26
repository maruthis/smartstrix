from datetime import datetime, timezone

from app import models, reports


def _org(name: str = "Acme Corp") -> models.Organization:
    return models.Organization(id="org1", name=name)


def _pentest(**overrides) -> models.Pentest:
    defaults = dict(
        id="pt-12345",
        org_id="org1",
        target_type="repository",
        target_id="r1",
        target_label="acme/widgets",
        scan_mode="deep",
        status="completed",
        started_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 6, tzinfo=timezone.utc),
        severity_counts={},
        created_by="u1",
        created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return models.Pentest(**defaults)


def _issue(**overrides) -> models.Issue:
    defaults = dict(
        id="i1",
        org_id="org1",
        pentest_id="pt-12345",
        title="SQL Injection in /search",
        description="User input concatenated into SQL query.",
        severity="critical",
        status="open",
        cvss=9.1,
        technical_analysis="Full DB compromise possible.",
        remediation_steps="Use parameterized queries.",
        poc_description="curl with payload.",
        target="app/search.py",
    )
    defaults.update(overrides)
    return models.Issue(**defaults)


def test_vid_formats_with_leading_zero():
    assert reports._vid(1) == "V-01"
    assert reports._vid(12) == "V-12"


def test_fmt_month_handles_none():
    assert reports._fmt_month(None) == "N/A"
    assert reports._fmt_month(datetime(2026, 3, 1)) == "March 2026"


def test_counts_ignores_unrecognized_severity():
    issues = [_issue(severity="critical"), _issue(severity="low"), _issue(severity="unknown")]
    counts = reports._counts(issues)
    assert counts == {"critical": 1, "high": 0, "medium": 0, "low": 1}


def test_posture_branches():
    assert reports._posture({"critical": 1, "high": 0, "medium": 0, "low": 0}) == "Weak"
    assert reports._posture({"critical": 0, "high": 1, "medium": 0, "low": 0}) == "Weak"
    assert reports._posture({"critical": 0, "high": 0, "medium": 1, "low": 0}) == "Moderate"
    assert reports._posture({"critical": 0, "high": 0, "medium": 0, "low": 1}) == "Good"
    assert reports._posture({"critical": 0, "high": 0, "medium": 0, "low": 0}) == "Strong"


def test_esc_handles_none_and_newlines():
    assert reports._esc(None) == ""
    assert reports._esc("line1\nline2") == "line1<br/>line2"
    assert reports._esc("<script>") == "&lt;script&gt;"


def test_summary_bar_renders_all_severities():
    out = reports._summary_bar({"critical": 2, "high": 1, "medium": 0, "low": 0})
    assert "Critical" in out
    assert "Low" in out


def test_finding_row_unknown_severity_falls_back_to_default_color():
    row = reports._finding_row(1, _issue(severity="informational"))
    assert "#888" in row
    assert "V-01" in row


def test_finding_detail_uses_fallback_text_when_fields_are_empty():
    issue = _issue(
        description="",
        technical_analysis="",
        remediation_steps="",
        poc_description="",
        poc_script_code="",
        target="",
        endpoint="",
        cvss=None,
        severity="unrecognized",
        status="weird_status",
    )
    detail = reports._finding_detail(1, issue)
    assert "No further detail was recorded" in detail
    assert "Exploitation may lead to unauthorized access" in detail
    assert "Review and remediate per the applicable" in detail
    assert "See Observation for affected component" in detail
    assert "Not applicable / not captured" in detail
    assert "N/A" in detail  # cvss
    assert "Weird_status" in detail  # STATUS_LABELS fallback via .capitalize()


def test_finding_detail_prefers_technical_analysis_when_description_missing():
    issue = _issue(description="", technical_analysis="Deep technical root cause.")
    detail = reports._finding_detail(1, issue)
    assert "Deep technical root cause." in detail


def test_finding_detail_falls_back_to_endpoint_when_target_missing():
    issue = _issue(target="", endpoint="/api/search")
    detail = reports._finding_detail(1, issue)
    assert "/api/search" in detail


def test_render_report_html_with_no_findings():
    html = reports.render_report_html(_pentest(), [], _org())
    assert "No vulnerabilities were identified" in html
    assert "acme/widgets" in html
    assert "Strong" in html  # posture with zero findings


def test_render_report_html_with_findings_sorted_by_severity():
    issues = [_issue(id="i1", title="Low one", severity="low"), _issue(id="i2", title="Crit one", severity="critical")]
    html = reports.render_report_html(_pentest(), issues, _org())
    assert html.index("Crit one") < html.index("Low one")
    assert "Vulnerability Details" in html
    assert "V-01" in html and "V-02" in html


def test_render_report_html_domain_target():
    pentest = _pentest(target_type="domain", target_label="example.com")
    html = reports.render_report_html(pentest, [], _org())
    assert "Domain / Web Application" in html
    assert "Dynamic Application Analysis (DAST)" in html


def test_render_report_html_falls_back_to_created_at_when_dates_missing():
    pentest = _pentest(started_at=None, finished_at=None)
    html = reports.render_report_html(pentest, [], _org())
    assert "January 2026" in html  # created_at fallback


def test_render_report_pdf_produces_pdf_bytes():
    html = reports.render_report_html(_pentest(), [_issue()], _org())
    pdf_bytes = reports.render_report_pdf(html)
    assert pdf_bytes[:4] == b"%PDF"
