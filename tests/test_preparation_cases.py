"""Member 3 · The labelled preparation cases are valid and agree with the rules.

Each case also runs through LivePreparation with a local model that quotes the
citable evidence, so the full preparation path is exercised offline. Live scoring
on these cases belongs to Member 4's evaluation runner.
"""

import json
import re
from pathlib import Path

import pytest

from careerpilot.agents.preparation import LivePreparation, public_evidence
from careerpilot.config import RuntimeConfig
from careerpilot.replay import _build_ats_answers
from careerpilot.schemas import CandidateEvidence, JobRecord, UserGoal

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "golden_dataset" / "preparation" / "cases.json")
    .read_text(encoding="utf-8")
)["cases"]
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def load(case):
    return (UserGoal.model_validate(case["goal"]), JobRecord.model_validate(case["job"]),
            [CandidateEvidence.model_validate(row) for row in case["evidence"]])


def test_case_ids_are_unique_and_both_splits_are_present():
    ids = [case["case_id"] for case in CASES]
    assert len(ids) == len(set(ids)) >= 6
    assert {case["split"] for case in CASES} == {"dev", "heldout"}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_labels_match_the_deterministic_rules(case):
    _, job, evidence = load(case)
    public = public_evidence(evidence)
    expected = case["expected"]
    assert expected["model_called"] == bool(public)
    assert expected["citable_evidence_ids"] == sorted(item.evidence_id for item in public)
    assert expected["ats_answers"] == _build_ats_answers(job, evidence)[0]


class Runtime:
    approved_feedback_ids = ()

    def __init__(self):
        self.reserved = 0

    def reserve_model_call(self):
        self.reserved += 1


def quoting_agent(case):
    """Local model that cites each citable record verbatim: a best-behaved model."""
    pytest.importorskip("google.adk")
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    _, _, evidence = load(case)
    facts = [{"text": item.text, "kind": "fact", "evidence_ids": [item.evidence_id]}
             for item in public_evidence(evidence)]
    answer = json.dumps({"resume_bullets": facts, "cover_paragraphs": [{"sentences": facts[:2]}]})

    class Quoting(BaseLlm):
        model: str = "quoting-fixture"

        async def generate_content_async(self, llm_request, stream=False):
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text=answer)]))

    return LivePreparation(RuntimeConfig(mode="live", model="fixture", max_model_calls=1), model=Quoting())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_case_passes_offline_through_live_preparation(case):
    goal, job, evidence = load(case)
    runtime = Runtime()
    package = quoting_agent(case).prepare(goal, job, evidence, None, None, runtime=runtime)
    drafts = package.resume_draft + "\n" + package.cover_letter
    expected = case["expected"]

    assert (runtime.reserved == 1) == expected["model_called"]
    assert package.ats_answers == expected["ats_answers"]
    cited = {ref for claim, refs in package.claim_evidence.items() if not claim.startswith("ATS: ") for ref in refs}
    assert cited <= set(expected["citable_evidence_ids"])
    for phrase in case["forbidden_in_drafts"]:
        assert phrase.casefold() not in drafts.casefold()
    body_numbers = set(NUMBER.findall(re.sub(r"\[[^\]]*\]", "", drafts.split("\n", 1)[1])))
    assert body_numbers <= set(expected["allowed_numbers"])
