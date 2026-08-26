"""Tests for the CLI ``--skill`` flag."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from typing import Any

import pytest


cli_main: Any = importlib.import_module("strix.interface.main")


def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_main,
        "load_settings",
        lambda: SimpleNamespace(runtime=SimpleNamespace(max_local_copy_mb=1024)),
    )


def test_parse_arguments_accepts_repeatable_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_settings(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "strix",
            "-n",
            "-t",
            "https://example.com",
            "--skill",
            "owasp_top_10",
            "--skill",
            "pci_dss",
        ],
    )

    args = cli_main.parse_arguments()

    assert args.skills == ["owasp_top_10", "pci_dss"]


def test_parse_arguments_defaults_skills_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_settings(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["strix", "-n", "-t", "https://example.com"])

    args = cli_main.parse_arguments()

    assert args.skills == []


def test_parse_arguments_rejects_unknown_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_settings(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["strix", "-n", "-t", "https://example.com", "--skill", "not_a_real_skill"],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_main.parse_arguments()

    assert exc_info.value.code == 2


def test_parse_arguments_rejects_more_than_five_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_settings(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "strix",
            "-n",
            "-t",
            "https://example.com",
            "--skill",
            "owasp_top_10",
            "--skill",
            "owasp_asvs",
            "--skill",
            "owasp_api_top_10",
            "--skill",
            "pci_dss",
            "--skill",
            "nist_ssdf",
            "--skill",
            "xss",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_main.parse_arguments()

    assert exc_info.value.code == 2
