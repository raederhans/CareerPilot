"""Member 3 · export: reviewable files with an evidence map and no sensitive text."""

import json

import pytest

from careerpilot.export import SENSITIVE_PLACEHOLDER, export_package, to_markdown
from careerpilot.replay import ReplayPreparation, load_evidence, load_jobs
from careerpilot.schemas import UserGoal


def package_with_sensitive_answer():
    evidence = load_evidence()
    auth = next(item for item in evidence if item.evidence_id == "CP-EV-004")
    auth.confirmed, auth.boolean_value = True, True
    auth.text = "Holds a synthetic Singapore work pass number S1234567A."
    job = load_jobs()[0]
    package = ReplayPreparation().prepare(
        UserGoal(intent="prepare"), job, evidence, None, None, runtime=None,
    )
    return package, job, evidence


def test_markdown_lists_claims_sources_and_answers_without_sensitive_text():
    package, job, evidence = package_with_sensitive_answer()
    text = to_markdown(package, job, evidence)
    assert "## Evidence map" in text
    assert "`CP-EV-001`" in text and "Synthetic university coursework record" in text
    assert "| Are you authorised to work in Singapore? | Yes |" in text
    assert "S1234567A" not in text
    assert SENSITIVE_PLACEHOLDER in text


def test_unanswered_question_is_flagged_for_the_candidate():
    evidence = load_evidence()
    job = load_jobs()[0]
    package = ReplayPreparation().prepare(UserGoal(intent="prepare"), job, evidence, None, None, runtime=None)
    assert "Unanswered: the candidate must confirm" in to_markdown(package, job, evidence)


def test_export_writes_markdown_and_json_with_metadata(tmp_path):
    package, job, evidence = package_with_sensitive_answer()
    md_path, json_path = export_package(package, job, evidence, tmp_path, metadata={"model": "local"})
    assert md_path.name == "CP-JOB-001_v1.md"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metadata"]["model"] == "local"
    assert data["package"]["version"] == 1
    assert "S1234567A" not in json_path.read_text(encoding="utf-8")


def test_export_refuses_a_package_for_another_job(tmp_path):
    package, _, evidence = package_with_sensitive_answer()
    with pytest.raises(ValueError):
        export_package(package, load_jobs()[1], evidence, tmp_path)
