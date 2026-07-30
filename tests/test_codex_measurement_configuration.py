from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SKILLS = (
    "thickness-analysis",
    "relative-density-analysis",
    "measurement-reporting",
    "measurement-lineage-validation",
)

AGENTS = (
    "measurement_orchestrator.toml",
    "thickness_analysis_agent.toml",
    "relative_density_agent.toml",
    "measurement_workflow_reviewer.toml",
)


def test_measurement_skills_are_in_codex_discovery_location() -> None:
    for skill_name in SKILLS:
        skill_dir = REPO_ROOT / ".agents" / "skills" / skill_name
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert skill.startswith("---\n")
        assert f"name: {skill_name}" in skill
        assert f"${skill_name}" in metadata

    assert not list((REPO_ROOT / "copilot-guidance" / "skills").glob("**/SKILL.md"))


def test_measurement_subagents_are_real_toml_definitions() -> None:
    for filename in AGENTS:
        path = REPO_ROOT / ".codex" / "agents" / filename
        with path.open("rb") as stream:
            payload = tomllib.load(stream)
        assert payload["name"]
        assert payload["description"]
        assert payload["model"] == "gpt-5.6-terra"
        assert payload["model_reasoning_effort"] == "medium"
        assert payload["sandbox_mode"] == "workspace-write"
        instructions = payload["developer_instructions"].lower()
        assert "determin" in instructions or "recalcul" in instructions
        assert "source data" in instructions or "tiff" in instructions

    assert not list((REPO_ROOT / "copilot-guidance" / "agents").glob("*.md"))
