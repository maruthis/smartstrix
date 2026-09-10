from app.standard_skills import normalize_standard_skills, to_engine_skills


def test_normalize_skips_blank_names_and_defaults_when_none_remain() -> None:
    assert normalize_standard_skills(["  ", ""]) == ["owasp_top_10"]


def test_to_engine_skills_drops_unknown_and_defaults() -> None:
    assert to_engine_skills(["not-a-skill"]) == ["standards/owasp_top_10"]
    assert to_engine_skills(["owasp_mcp_top_10"]) == ["standards/owasp_mcp_top_10"]
