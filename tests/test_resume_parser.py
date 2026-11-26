"""Member 3 · resume_parser: deterministic split, sensitivity and skill keys."""

from careerpilot.agents.preparation import public_evidence
from careerpilot.tools.resume_parser import is_sensitive, parse_resume

RESUME = """Alex Tan
alex.tan@example.com | +65 9123 4567
Blk 123 Jurong West St 41 #05-123

## Education
- MSc Applied AI, Example University, 2026 - 2027
- Completed Python programming coursework covering data structures.

SKILLS
- Python, SQL and Git
- Machine learning: compared 3 supervised classification models in a course project.

Projects:
* Built a PyTorch image classifier reaching 91% validation accuracy.
* Work pass status: to be confirmed.
"""


def test_each_content_line_becomes_one_record_with_section_provenance():
    records = parse_resume(RESUME, source_name="alex_resume.md")
    texts = [r.text for r in records]
    assert "MSc Applied AI, Example University, 2026 - 2027" in texts
    assert all(r.source_id == "RESUME-alex_resume.md" for r in records)
    edu = next(r for r in records if r.text.startswith("MSc"))
    assert "section 'Education'" in edu.provenance
    assert [r.evidence_id for r in records][:2] == ["RES-001", "RES-002"]


def test_contact_identity_and_work_pass_lines_are_sensitive_and_unconfirmed():
    records = parse_resume(RESUME)
    sensitive = {r.text for r in records if r.sensitive}
    assert "Alex Tan" in sensitive
    assert "alex.tan@example.com | +65 9123 4567" in sensitive
    assert "Blk 123 Jurong West St 41 #05-123" in sensitive
    assert "Work pass status: to be confirmed." in sensitive
    assert all(not r.confirmed for r in records if r.sensitive)
    public_texts = " ".join(r.text for r in public_evidence(records))
    assert "@" not in public_texts and "9123" not in public_texts


def test_year_ranges_and_scores_are_not_mistaken_for_phone_numbers():
    assert not is_sensitive("MSc Applied AI, Example University, 2026 - 2027")
    assert not is_sensitive("Reached 91% validation accuracy on 10000 images.")
    assert is_sensitive("Call 9123 4567")


def test_known_skills_get_one_fact_key_each():
    records = parse_resume(RESUME)
    keys = {r.fact_key: r.text for r in records if r.fact_key}
    assert keys["skill.python"] == "Completed Python programming coursework covering data structures."
    assert keys["skill.sql"] == "Python, SQL and Git"
    assert keys["skill.ml"].startswith("Machine learning")
    assert keys["skill.deep_learning"].startswith("Built a PyTorch")
    assert all(r.boolean_value is True for r in records if r.fact_key)
    assert sum(1 for r in records if r.fact_key == "skill.python") == 1


def test_unconfirmed_option_keeps_every_record_out_of_drafts():
    assert public_evidence(parse_resume(RESUME, confirmed=False)) == []
