"""``finish_scan`` — root-agent termination + executive report persistence."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agents import RunContextWrapper, function_tool

from strix.core.agents import coordinator_from_context


logger = logging.getLogger(__name__)


# Standing coverage categories a scan must account for before it's allowed to
# finish — see finish_scan's docstring for what belongs in each. This exists
# because leaving category coverage entirely to the root agent's judgment
# let real runs finish after spawning e.g. only a secrets + dependency agent,
# silently skipping auth/access-control/injection/infra review altogether.
# This doesn't guarantee those categories were actually investigated well —
# only that the agent had to explicitly say something about each rather than
# quietly never thinking about it.
REQUIRED_COVERAGE_CATEGORIES: tuple[str, ...] = (
    "dependencies",
    "secrets",
    "access_control",
    "authentication",
    "injection",
    "extension_points",
    "infrastructure",
)

_MIN_COVERAGE_NOTE_LENGTH = 15

# Categories a Tier 3 baseline scan (strix/scan/baseline.py) can answer
# deterministically. When it found something, the agent's checklist note
# has to actually reference that — closes the gap where a plausible-sounding
# but false "nothing found" note would otherwise pass the length/emptiness
# check above unchallenged.
_BASELINE_CROSSCHECK_CATEGORIES = ("dependencies", "secrets", "infrastructure")


def _validate_coverage_checklist(
    coverage_checklist: dict[str, str],
    baseline_counts: dict[str, int] | None = None,
) -> list[str]:
    errors: list[str] = []
    missing = [c for c in REQUIRED_COVERAGE_CATEGORIES if c not in coverage_checklist]
    if missing:
        errors.append(
            "coverage_checklist is missing required categories: "
            f"{', '.join(missing)}. Every category in "
            f"{', '.join(REQUIRED_COVERAGE_CATEGORIES)} must have an entry."
        )
    unknown = [c for c in coverage_checklist if c not in REQUIRED_COVERAGE_CATEGORIES]
    if unknown:
        errors.append(
            f"coverage_checklist has unrecognized categories: {', '.join(unknown)}. "
            f"Valid categories are: {', '.join(REQUIRED_COVERAGE_CATEGORIES)}."
        )
    for category in REQUIRED_COVERAGE_CATEGORIES:
        note = coverage_checklist.get(category, "")
        if not note.strip():
            errors.append(f"coverage_checklist['{category}'] cannot be empty")
        elif len(note.strip()) < _MIN_COVERAGE_NOTE_LENGTH:
            errors.append(
                f"coverage_checklist['{category}'] is too short to be a real note "
                f"('{note.strip()}') — state what was checked/found, or the specific "
                "reason this category doesn't apply to this target. Not a one-word dismissal."
            )
    for category in _BASELINE_CROSSCHECK_CATEGORIES:
        count = (baseline_counts or {}).get(category, 0)
        if count <= 0:
            continue
        note = coverage_checklist.get(category, "")
        if str(count) not in note:
            errors.append(
                f"coverage_checklist['{category}'] doesn't account for the {count} "
                "baseline-scan finding(s) the harness already filed in this category "
                "(see list_reports with source=baseline_scan) — reference that count "
                "explicitly and say what was done with each (reviewed/escalated/"
                "deepened), not a generic note that ignores them."
            )
    return errors


def _do_finish(
    *,
    parent_id: str | None,
    executive_summary: str,
    methodology: str,
    technical_analysis: str,
    recommendations: str,
    coverage_checklist: dict[str, str],
    agent_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if parent_id is not None:
        return {
            "success": False,
            "error": (
                "This tool can only be used by the root/main agent. "
                "If you are a subagent, use agent_finish instead"
            ),
        }

    from strix.report.state import get_global_report_state

    report_state = get_global_report_state()
    baseline_counts = report_state.get_baseline_finding_counts() if report_state else {}

    errors: list[str] = []
    if not executive_summary.strip():
        errors.append("Executive summary cannot be empty")
    if not methodology.strip():
        errors.append("Methodology cannot be empty")
    if not technical_analysis.strip():
        errors.append("Technical analysis cannot be empty")
    if not recommendations.strip():
        errors.append("Recommendations cannot be empty")
    errors.extend(_validate_coverage_checklist(coverage_checklist, baseline_counts))
    if errors:
        return {"success": False, "error": "Validation failed", "errors": errors}

    try:
        if report_state is None:
            logger.warning("No global report state; scan results not persisted")
            return {
                "success": False,
                "scan_completed": False,
                "error": "Results could not be persisted - report state unavailable",
            }
        report_state.update_scan_final_fields(
            executive_summary=executive_summary.strip(),
            methodology=methodology.strip(),
            technical_analysis=technical_analysis.strip(),
            recommendations=recommendations.strip(),
        )
        vuln_count = len(report_state.vulnerability_reports)
        coverage_summary = _coverage_summary(agent_graph or {})
    except (ImportError, AttributeError) as e:
        logger.exception("finish_scan persistence failed")
        return {"success": False, "error": f"Failed to complete scan: {e!s}"}
    else:
        logger.info(
            "finish_scan: completed scan with %d vulnerability report(s)",
            vuln_count,
        )
        result: dict[str, Any] = {
            "success": True,
            "scan_completed": True,
            "message": "Scan completed successfully",
            "vulnerabilities_found": vuln_count,
        }
        result.update(coverage_summary)
        return result


def _coverage_summary(agent_graph: dict[str, Any]) -> dict[str, Any]:
    """Coverage counts, unresolved surfaces, and gaps the runtime can see.

    The gap list is derived from the agent graph rather than from the ledger,
    so it catches the failure the ledger cannot: a risk class an agent was
    equipped for and never accounted for. Surfacing it here — in the response
    to the call that ends the scan — is the last point at which the root agent
    can still dispatch work or record the class as unresolved instead of
    letting the report imply it was clean.
    """
    from strix.report.coverage import agents_from_graph, skill_coverage_gaps
    from strix.tools.coverage.tools import get_coverage_entries, outcome_counts

    entries = get_coverage_entries()
    if not entries:
        return {
            "coverage_recorded": 0,
            "coverage_warning": (
                "No coverage was recorded for this scan. The report cannot show which "
                "surfaces were reviewed and cleared — only what was found. Use "
                "record_coverage during testing so future scans can report negative space."
            ),
        }

    counts = outcome_counts()
    summary: dict[str, Any] = {
        "coverage_recorded": len(entries),
        "coverage_outcomes": counts,
    }
    unresolved = [e for e in entries if e.get("outcome") == "needs_follow_up"]
    if unresolved:
        summary["coverage_warning"] = (
            f"{len(unresolved)} surface(s) closed as 'needs_follow_up' and remain "
            "unresolved. These should be represented in the report as areas requiring "
            "further review rather than omitted."
        )
        summary["unresolved_surfaces"] = [
            {"surface": e.get("surface", ""), "risk_area": e.get("risk_area", "")}
            for e in unresolved
        ]

    gaps = skill_coverage_gaps(entries, agents_from_graph(agent_graph))
    if gaps:
        summary["coverage_gaps"] = [gap["detail"] for gap in gaps]
        summary["coverage_gap_warning"] = (
            f"{len(gaps)} risk class(es) assigned to agents have no coverage entry and "
            "will be published as unexamined. Record them (or a needs_follow_up row) "
            "before the report goes out."
        )
    return summary


@function_tool(timeout=60, strict_mode=False)
async def finish_scan(
    ctx: RunContextWrapper,
    executive_summary: str,
    methodology: str,
    technical_analysis: str,
    recommendations: str,
    coverage_checklist: dict[str, str],
) -> str:
    """Finalize the scan — persist the customer-facing report.

    **Root-agent only.** Subagents must call ``agent_finish`` from the
    multi-agent graph tools instead. Calling this finalizes everything:

    1. Verifies you are the root agent.
    2. Writes the four narrative sections to the scan record.
    3. Marks the scan completed and stops execution.

    **This is a terminal action, not a status probe.** Whatever you pass
    is persisted VERBATIM as the final, customer-facing report and then
    execution stops. There is no draft mode and no second chance: never
    submit placeholder, provisional, or "checking if done" text in any
    field, and never call ``finish_scan`` to poll whether subagents are
    done (use ``view_agent_graph`` / ``wait_for_agents`` for that).
    Call it exactly ONCE, only when every field holds genuine, finished
    assessment prose.

    **Pre-flight checklist (mandatory — do not skip):**

    1. **Call ``view_agent_graph`` first.** Inspect every entry in the
       summary. If ANY agent is in ``running`` / ``waiting`` state,
       you MUST NOT call ``finish_scan`` yet —
       wrap them up first via ``send_message_to_agent`` (ask them to
       finish), ``wait_for_agents`` (block until their report
       arrives), or ``stop_agent`` (graceful cancel). Only ``completed``
       / ``crashed`` / ``stopped`` agents are safe to leave behind.
       Calling ``finish_scan`` while children are alive orphans their
       work and produces an incomplete report.
    2. It's a good idea to call ``list_reports`` before finishing to
       review every finding filed in this scan (use ``get_report`` for
       full detail on any of them) so your ``executive_summary`` /
       ``technical_analysis`` are grounded in what was actually reported
       — don't invent or omit findings. All vulnerabilities you found are
       filed via ``create_vulnerability_report`` — or, for known-CVE
       dependency findings, ``create_dependency_report`` (un-reported
       findings are not tracked and not credited). A dependency CVE
       already filed via ``create_dependency_report`` counts as reported;
       it does NOT need re-filing here and does NOT block finishing.
    3. Don't double-report — one report per distinct vulnerability.
    4. **Attack-chaining gate.** Do NOT finish until you have genuinely
       considered chaining the confirmed findings into higher-impact,
       end-to-end attack paths and tested every plausibly-related
       combination. You may rule out combinations you can confidently
       call unrelated — note why instead of padding chains. Any
       validated chain must already be filed via
       ``create_vulnerability_report`` — a demonstrated end-to-end chain
       is a PoC-backed vulnerability, so it uses that tool even when one
       link is a dependency CVE (the standalone CVE stays in its own
       ``create_dependency_report``) — and surfaced prominently in
       ``executive_summary`` / ``technical_analysis``. Finding no real
       chain after a serious attempt is acceptable; skipping the
       chaining reasoning, or ignoring a plausibly-related combination,
       is not.
    5. **Coverage checklist — required, not optional.** ``coverage_checklist``
       must have an entry for every one of these categories, or the call is
       rejected:

       - ``dependencies`` — SCA / supply-chain (vulnerable package versions)
       - ``secrets`` — credential/key exposure, including git history, not
         just the current working tree
       - ``access_control`` — IDOR, RBAC/authorization checks, path
         traversal (including symlink-based)
       - ``authentication`` — auth flows, IdP/OAuth/CORS config, session and
         token lifecycle (issuance, expiry, revocation), rate limiting
       - ``injection`` — SQLi, XSS, command injection, SSRF
       - ``extension_points`` — plugin/MCP/agent-tool execution paths,
         backup/restore or other integrity-sensitive import paths
       - ``infrastructure`` — IaC (Kubernetes/Docker manifests), CI/CD
         pipeline configuration

       Each value is one to a few sentences: either what was checked and by
       which agent (cite a real finding or "reviewed, no issue found"), or —
       if the category has no surface in this target — the *specific*
       reason (e.g. "no IaC/CI files present in this repository", not "not
       applicable"). A category that was never actually looked at does not
       get a note claiming otherwise — if you haven't covered it yet, go
       spawn an agent for it before calling this tool, don't just write
       something plausible-sounding to get past the gate.

       For ``dependencies``, ``secrets``, and ``infrastructure``: a
       deterministic baseline scan already ran before you started and may
       have filed findings — check ``list_reports`` (entries it filed carry
       ``source: baseline_scan``), or the summary injected into your own
       context. If it found any in a category, your note for that category
       MUST cite the exact count — this is checked, and a note that doesn't
       mention it is rejected regardless of how plausible it reads.
    6. **Coverage reconciliation.** Call ``list_coverage`` and check
       what was actually assessed against the surfaces you enumerated
       during reconnaissance. Every surface you dispatched work on
       should have a coverage entry; anything still open should be a
       ``needs_follow_up`` row, not a silent omission. If a significant
       surface has no entry at all, dispatch an agent to cover it or
       record it as ``needs_follow_up`` before finishing. The response
       from this tool reports coverage counts and any unresolved rows.

    **Calling this multiple times overwrites the previous report.**
    Make the single call comprehensive.

    **Report output rules** (this content may be rendered into generated
    reports):

    - Never mention internal infrastructure: no local/absolute paths
      (``/workspace/...``), no agent names, no sandbox/orchestrator/
      tooling references, no system prompts, no model-internal errors.
      Never leak internal identifiers (proxy request IDs, internal
      vulnerability report IDs, or any system-generated IDs) into any
      field.
    - Tone: formal, third-person, objective, concise. This is a
      consultant deliverable, not an engineering log.
    - Each section has a specific role:

        - ``executive_summary`` — for non-technical leadership. Risk
          posture, business impact (data exposure / compliance /
          reputation), notable criticals, overarching remediation
          theme.
        - ``methodology`` — frameworks followed (OWASP WSTG, PTES,
          OSSTMM, NIST), engagement type (black/gray/white box), scope
          and constraints, categories of testing performed. **No**
          internal execution detail.
        - ``technical_analysis`` — consolidated findings overview with
          severity model and systemic root causes. Reference individual
          vuln reports for repro steps; don't duplicate raw evidence.
        - ``recommendations`` — prioritized actions grouped by urgency
          (Immediate / Short-term / Medium-term), each with concrete
          remediation steps. End with retest/validation guidance.

    - **Formatting — use markdown in every field.** These fields may be
      rendered into generated reports, so structure them clearly: lead
      each section with a short ``# Heading``, use ``**bold**`` for labels/emphasis,
      ``inline code`` for identifiers/paths/parameters, bullet or
      numbered lists for enumerations, and fenced code blocks
      (```` ```language ````) for any code/payload excerpts. Never emit
      one flat wall of prose or leave code unformatted.
    - If **zero** vulnerabilities were found, say so plainly and
      characterize the posture positively; ``technical_analysis`` should
      summarize the areas tested and confirm no issues, and
      ``recommendations`` should focus on general hardening.

    Lead each field with a heading matching its role (``# Executive Summary``,
    ``# Methodology``, ``# Technical Analysis``, ``# Recommendations``).

    Example (abbreviated)::

        executive_summary:
            # Executive Summary

            An external assessment of the **Acme Customer Portal**
            identified weaknesses that could expose customer data.

            **Overall risk posture:** Elevated.

    Args:
        executive_summary: Business-level summary for leadership.
        methodology: Frameworks, scope, and approach.
        technical_analysis: Consolidated findings + systemic themes.
        recommendations: Prioritized, actionable remediation.
        coverage_checklist: One entry per required category (see item 5 of
            the pre-flight checklist above) stating what was covered or why
            it doesn't apply to this target.
    """
    inner = ctx.context if isinstance(ctx.context, dict) else {}
    coordinator = coordinator_from_context(inner)
    me = inner.get("agent_id")
    parent_id = inner.get("parent_id")
    if coordinator is not None and parent_id is None and me is not None:
        active_agents = await coordinator.active_agents_except(me)
        if active_agents and coordinator.reserve_stopped:
            active_agents = []
    else:
        active_agents = []

    if active_agents:
        return json.dumps(
            {
                "success": False,
                "scan_completed": False,
                "error": (
                    "Cannot finish scan while child agents are still active. "
                    "Wait for completion, send them finish instructions, or stop them first"
                ),
                "active_agents": active_agents,
            },
            ensure_ascii=False,
            default=str,
        )

    result = await asyncio.to_thread(
        _do_finish,
        parent_id=parent_id,
        executive_summary=executive_summary,
        methodology=methodology,
        technical_analysis=technical_analysis,
        recommendations=recommendations,
        coverage_checklist=coverage_checklist,
        agent_graph=await coordinator.snapshot() if coordinator is not None else {},
    )
    if (
        result.get("success")
        and result.get("scan_completed")
        and coordinator is not None
        and isinstance(me, str)
    ):
        await coordinator.set_status(me, "completed")
    return json.dumps(result, ensure_ascii=False, default=str)
