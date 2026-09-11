"""Harness-driven scan phases that run outside agent discretion."""

from strix.scan.baseline import BaselineFinding, BaselineResult, run_baseline_scan
from strix.scan.playbooks import RequiredPlaybook, required_playbooks_for
from strix.scan.surface_detect import detect_surfaces


__all__ = [
    "BaselineFinding",
    "BaselineResult",
    "RequiredPlaybook",
    "detect_surfaces",
    "required_playbooks_for",
    "run_baseline_scan",
]
