"""Member 3 · Application preparation agent backed by Gemini through Google ADK.

The model chooses the wording. Deterministic rules decide what may be stated:

1. Only confirmed, non-sensitive evidence is sent to the model.
2. The model returns structured sentences. Each one is a ``fact`` that cites
   evidence IDs or an ``aspiration`` about the target role that cites nothing.
3. A guard removes any sentence whose citations, numbers or wording are not
   supported by the cited evidence. The model cannot add a claim the rules reject.
4. ATS answers never come from the model. They reuse the replay rule, so a
   sensitive fact is answered only yes/no and an unresolved fact stays ``None``.

Draft format proposed to the verifier (Member 4), pending team agreement:
a factual sentence is followed by its evidence tags, for example
``Completed a machine learning course project. [CP-EV-002]``. Several sources are
written ``[CP-EV-001, CP-EV-002]``. ``claim_evidence`` maps the sentence text
without tags to the sorted IDs. Aspiration sentences carry no tag.
"""

from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

from pydantic import BaseModel, Field, ValidationError

from ..config import RuntimeConfig
# Shared with Member 1's replay rules so the verifier expects identical answers.
from ..replay import _build_ats_answers, _rank_evidence
from ..schemas import (
    ApplicationPackage, CandidateEvidence, JobRecord, ReviewResult, Runtime,
    UnsupportedRevision, UserGoal,
)

FeedbackLookup = Callable[[Sequence[str]], list[dict[str, Any]]]

MAX_PROMPT_EVIDENCE = 12
MAX_FEEDBACK_EXAMPLES = 3
MAX_JOB_TEXT = 4000
EMPTY_PROFILE = "No confirmed, non-sensitive profile evidence is available yet."
GREETING = "Dear Hiring Team,"
SIGN_OFF = "Sincerely,"
SIGNATURE = "The candidate"


class PreparationError(RuntimeError):
    """The model call failed or returned output that cannot be used safely."""


# ---------------------------------------------------------------------------
# Structured model output
# ---------------------------------------------------------------------------

class DraftSentence(BaseModel):
    """One sentence. A fact must cite evidence; an aspiration must not."""

    text: str = Field(min_length=1, max_length=400)
    kind: Literal["fact", "aspiration"]
    evidence_ids: list[str] = Field(default_factory=list)


class CoverParagraph(BaseModel):
    sentences: list[DraftSentence]


class DraftOutput(BaseModel):
    """The only shape the model may return."""

    resume_bullets: list[DraftSentence]
    cover_paragraphs: list[CoverParagraph]


# ---------------------------------------------------------------------------
# Guard report, shown in the notebook and available to tests
# ---------------------------------------------------------------------------

@dataclass
class GuardIssue:
    section: Literal["resume", "cover"]
    text: str
    code: str


@dataclass
class PreparationReport:
    model_called: bool = False
    prompt_evidence_ids: list[str] = field(default_factory=list)
    feedback_ids_used: list[str] = field(default_factory=list)
    removed: list[GuardIssue] = field(default_factory=list)
    resume_fallback: bool = False
    cover_fallback: bool = False


# ---------------------------------------------------------------------------
# Deterministic rules (no model involved)
# ---------------------------------------------------------------------------

_TAGS = re.compile(r"\s*\[[A-Za-z0-9_.:,\s-]+\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"[^\W_]+(?:[+#]+)?")
_PAST_EXPERIENCE = re.compile(
    r"\b(i have|i've|i had|i was|i completed|i built|i led|i developed|i worked|"
    r"i used|i managed|experience (?:in|with)|years? of)\b",
    re.IGNORECASE,
)
# Eligibility facts are answered only through ATS answers from confirmed records.
_ELIGIBILITY = re.compile(
    r"\b(authori[sz](?:ed|ation)|work pass|employment pass|visa|citizen(?:ship)?|"
    r"permanent resident|residency|nationality|salary|date of birth)\b",
    re.IGNORECASE,
)
# A named technology must appear in the evidence the sentence cites. This catches a
# supported clause joined to an unsupported one ("... models and Kubernetes").
_SKILL_TERMS = re.compile(
    r"\b(python|java|javascript|typescript|c\+\+|c#|golang|rust|scala|sql|nosql|"
    r"machine learning|deep learning|pytorch|tensorflow|keras|scikit-learn|pandas|numpy|"
    r"docker|kubernetes|aws|azure|gcp|google cloud|spark|hadoop|airflow|git|linux|"
    r"react|node\.js|django|flask|fastapi|llms?|nlp|computer vision|tableau|power bi)\b",
    re.IGNORECASE,
)
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "using", "used",
    "role", "candidate", "completed", "course", "experience", "have", "has", "was",
    "were", "are", "skills", "skill", "work", "worked", "strong", "basic",
}


def normalise(text: str) -> str:
    """Collapse whitespace and drop any evidence tags the model copied into text."""
    return " ".join(_TAGS.sub("", text).split())


def public_evidence(evidence: Sequence[CandidateEvidence]) -> list[CandidateEvidence]:
    """Rule 1: confirmed and non-sensitive records are the only ones a draft may use."""
    return [item for item in evidence if item.confirmed and not item.sensitive]


def _content_words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if len(word) >= 3} - _STOP


def check_sentence(
    sentence: DraftSentence, allowed: dict[str, CandidateEvidence],
) -> str | None:
    """Return an issue code, or ``None`` when the sentence may enter the draft."""
    text = normalise(sentence.text)
    if not text or "\n" in sentence.text or "[" in text or "]" in text:
        return "malformed_text"
    if _ELIGIBILITY.search(text):
        return "eligibility_topic"
    if sentence.kind == "aspiration":
        if sentence.evidence_ids:
            return "aspiration_cites_evidence"
        if _NUMBER.search(text):
            return "aspiration_contains_number"
        if _PAST_EXPERIENCE.search(text):
            return "aspiration_describes_experience"
        return None
    ids = list(dict.fromkeys(sentence.evidence_ids))
    if not ids:
        return "fact_without_evidence"
    if any(item_id not in allowed for item_id in ids):
        return "unknown_or_private_evidence"
    cited = [allowed[item_id] for item_id in ids]
    source_text = " ".join(
        f"{item.text} {item.fact_value if item.fact_value is not None else ''}" for item in cited
    )
    if not set(_NUMBER.findall(text)) <= set(_NUMBER.findall(source_text)):
        return "unsupported_number"
    named = {term.casefold() for term in _SKILL_TERMS.findall(text)}
    if named - {term.casefold() for term in _SKILL_TERMS.findall(source_text)}:
        return "unsupported_skill"
    if not _content_words(text) & _content_words(source_text):
        return "evidence_not_related"
    return None


def guard_draft(
    draft: DraftOutput, evidence: Sequence[CandidateEvidence], report: PreparationReport,
) -> tuple[list[DraftSentence], list[list[DraftSentence]]]:
    """Rule 3: keep only sentences the rules accept and record every removal."""
    allowed = {item.evidence_id: item for item in public_evidence(evidence)}

    def keep(sentence: DraftSentence, section: Literal["resume", "cover"]) -> bool:
        code = check_sentence(sentence, allowed)
        if code is not None:
            report.removed.append(GuardIssue(section, sentence.text, code))
            return False
        return True

    bullets = [
        DraftSentence(text=normalise(s.text), kind=s.kind, evidence_ids=sorted(set(s.evidence_ids)))
        for s in draft.resume_bullets
        if s.kind == "fact" and keep(s, "resume")
    ]
    for s in draft.resume_bullets:
        if s.kind == "aspiration":
            report.removed.append(GuardIssue("resume", s.text, "aspiration_in_resume"))
    paragraphs = []
    for paragraph in draft.cover_paragraphs:
        kept = [
            DraftSentence(text=normalise(s.text), kind=s.kind, evidence_ids=sorted(set(s.evidence_ids)))
            for s in paragraph.sentences if keep(s, "cover")
        ]
        if kept:
            paragraphs.append(kept)
    return bullets, paragraphs


def _tag(sentence: DraftSentence) -> str:
    if sentence.kind == "aspiration":
        return sentence.text
    return f"{sentence.text} [{', '.join(sentence.evidence_ids)}]"


def render_resume(job: JobRecord, bullets: Sequence[DraftSentence]) -> str:
    lines = [f"# Resume draft for {normalise(job.title)}", "", "## Relevant evidence"]
    if bullets:
        lines.extend(f"- {_tag(item)}" for item in bullets)
    else:
        lines.append(EMPTY_PROFILE)
    return "\n".join(lines)


def render_cover_letter(job: JobRecord, paragraphs: Sequence[Sequence[DraftSentence]]) -> str:
    lines = [f"# Cover letter draft for {normalise(job.title)} at {normalise(job.company)}", "", GREETING, ""]
    if paragraphs:
        for paragraph in paragraphs:
            lines.extend([" ".join(_tag(item) for item in paragraph), ""])
    else:
        lines.extend([EMPTY_PROFILE, ""])
    lines.extend([SIGN_OFF, SIGNATURE])
    return "\n".join(lines)


def verbatim_facts(evidence: Sequence[CandidateEvidence], limit: int) -> list[DraftSentence]:
    """Fallback: quote the evidence itself when no model sentence survives the guard."""
    return [
        DraftSentence(text=normalise(item.text), kind="fact", evidence_ids=[item.evidence_id])
        for item in evidence[:limit]
    ]


def build_claim_evidence(
    bullets: Sequence[DraftSentence], paragraphs: Sequence[Sequence[DraftSentence]],
    ats_references: dict[str, list[str]],
) -> dict[str, list[str]]:
    claims: dict[str, set[str]] = {}
    for sentence in [*bullets, *(s for p in paragraphs for s in p)]:
        if sentence.kind == "fact":
            claims.setdefault(sentence.text, set()).update(sentence.evidence_ids)
    result = {claim: sorted(refs) for claim, refs in claims.items()}
    result.update({f"ATS: {question}": refs for question, refs in ats_references.items()})
    return result


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

class LivePreparation:
    """Implements ``PreparationAgent.prepare`` with one bounded Gemini call per draft.

    ``model`` accepts an ADK ``BaseLlm`` so tests and the notebook can run offline.
    ``feedback_lookup`` turns approved feedback IDs into example dictionaries; it
    belongs to Member 4's feedback store and may be omitted until that exists.
    """

    mode = "live"

    def __init__(
        self, config: RuntimeConfig, *, model: Any = None,
        feedback_lookup: FeedbackLookup | None = None, max_output_tokens: int = 2048,
        temperature: float = 0.4,
    ):
        if config.mode != "live" or not config.model:
            raise ValueError("LivePreparation requires a live configuration with a course-approved model.")
        self.config = config
        self._model = model
        self.feedback_lookup = feedback_lookup
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.last_usage: dict[str, int] = {}
        self.last_report = PreparationReport()

    # -- PreparationAgent protocol ------------------------------------------------

    def prepare(
        self, goal: UserGoal, job: JobRecord, evidence: list[CandidateEvidence],
        previous: ApplicationPackage | None, review: ReviewResult | None, *, runtime: Runtime,
    ) -> ApplicationPackage:
        self.last_usage = {}
        report = self.last_report = PreparationReport()
        usable = _rank_evidence(public_evidence(evidence), goal, job)
        ats_answers, ats_references = _build_ats_answers(job, evidence)

        if not usable:
            # Rule: nothing to say means no model call and no invented content.
            bullets, paragraphs = [], []
        else:
            prompt_evidence = usable[:MAX_PROMPT_EVIDENCE]
            report.prompt_evidence_ids = [item.evidence_id for item in prompt_evidence]
            examples = self._feedback_examples(runtime, report)
            message = self._message(goal, job, prompt_evidence, examples, previous, review)
            instruction = self._instruction(revising=previous is not None)
            runtime.reserve_model_call()  # Before the request; exhaustion stops here.
            report.model_called = True
            draft = self._generate(instruction, message)
            bullets, paragraphs = guard_draft(draft, evidence, report)
            if not bullets:
                report.resume_fallback = True
                bullets = verbatim_facts(prompt_evidence, limit=5)
            if not any(s.kind == "fact" for p in paragraphs for s in p):
                report.cover_fallback = True
                paragraphs = [*paragraphs, verbatim_facts(prompt_evidence, limit=3)]

        package = ApplicationPackage(
            job_id=job.job_id,
            resume_draft=render_resume(job, bullets),
            cover_letter=render_cover_letter(job, paragraphs),
            ats_answers=ats_answers,
            claim_evidence=build_claim_evidence(bullets, paragraphs, ats_references),
            version=(previous.version + 1) if previous else 1,
        )
        if previous is not None and (
            package.resume_draft == previous.resume_draft
            and package.cover_letter == previous.cover_letter
            and package.ats_answers == previous.ats_answers
        ):
            raise UnsupportedRevision("The requested revision would not change the current draft.")
        return package

    # -- Prompt assembly ---------------------------------------------------------------

    def _feedback_examples(self, runtime: Runtime, report: PreparationReport) -> list[dict[str, Any]]:
        ids = list(runtime.approved_feedback_ids)[:MAX_FEEDBACK_EXAMPLES]
        if not ids or self.feedback_lookup is None:
            return []
        examples = list(self.feedback_lookup(ids))[:MAX_FEEDBACK_EXAMPLES]
        report.feedback_ids_used = ids[: len(examples)]
        return examples

    @staticmethod
    def _instruction(*, revising: bool) -> str:
        folder = Path(__file__).resolve().parents[1] / "prompts"
        base = (folder / "preparation.md").read_text(encoding="utf-8")
        if revising:
            base += "\n\n" + (folder / "revision.md").read_text(encoding="utf-8")
        return base

    @staticmethod
    def _message(
        goal: UserGoal, job: JobRecord, evidence: Sequence[CandidateEvidence],
        examples: Sequence[dict[str, Any]], previous: ApplicationPackage | None,
        review: ReviewResult | None,
    ) -> str:
        payload: dict[str, Any] = {
            "task": "revise" if previous is not None else "draft",
            "job": {
                "title": job.title, "company": job.company, "location": job.location,
                "requirements": [req.label for req in job.requirements],
            },
            # Untrusted text: the prompt tells the model to treat it as data only.
            "job_description": "<<<JOB_TEXT\n" + job.description[:MAX_JOB_TEXT] + "\nJOB_TEXT>>>",
            "candidate_goal": {"target_roles": goal.target_roles, "preferences": goal.preferences},
            "evidence": [{"evidence_id": item.evidence_id, "text": item.text} for item in evidence],
            "approved_feedback_examples": list(examples),
        }
        if previous is not None:
            payload["previous_draft"] = {
                "resume": previous.resume_draft, "cover_letter": previous.cover_letter,
            }
            payload["repair_instructions"] = list(review.repair_instructions) if review else []
        return json.dumps(payload, ensure_ascii=False, indent=2)

    # -- One bounded ADK call -----------------------------------------------------------

    def _generate(self, instruction: str, message: str) -> DraftOutput:
        """Run the async ADK call from plain Python or from inside a notebook loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._generate_async(instruction, message))
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(
                lambda: asyncio.run(self._generate_async(instruction, message))
            ).result()

    async def _generate_async(self, instruction: str, message: str) -> DraftOutput:
        try:
            return await asyncio.wait_for(
                self._run(instruction, message), timeout=self.config.timeout_seconds,
            )
        except ImportError as error:
            raise PreparationError("Install requirements-live.txt to enable live preparation.") from error
        except PreparationError:
            raise
        except TimeoutError as error:
            raise PreparationError("Preparation timed out.") from error
        except Exception as error:
            raise PreparationError("Preparation failed. Check the course model configuration.") from error

    async def _run(self, instruction: str, message: str) -> DraftOutput:
        from google.adk.models.google_llm import Gemini
        from google.genai import types

        no_retry = types.HttpRetryOptions(attempts=1)
        gemini = None if self._model is not None else Gemini(
            model=self.config.model, retry_options=no_retry,
        )
        try:
            return await self._run_agent(instruction, message, gemini or self._model, no_retry)
        finally:
            if gemini is not None:
                # Close the HTTP client inside this event loop; otherwise it is closed
                # after asyncio.run() ends and prints "Event loop is closed".
                try:
                    await gemini.api_client.aio.aclose()
                except Exception:
                    pass

    async def _run_agent(self, instruction: str, message: str, model: Any, no_retry: Any) -> DraftOutput:
        from google.adk.agents import LlmAgent
        from google.adk.agents.run_config import RunConfig
        from google.adk.apps import App
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        agent = LlmAgent(
            name="application_preparation",
            model=model,
            instruction=instruction,
            output_schema=DraftOutput,
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(
                temperature=self.temperature, max_output_tokens=self.max_output_tokens,
                http_options=types.HttpOptions(
                    timeout=int(self.config.timeout_seconds * 1000), retry_options=no_retry,
                ),
            ),
        )
        app = App(name="careerpilot_preparation", root_agent=agent)
        sessions = InMemorySessionService()
        session = await sessions.create_session(app_name=app.name, user_id="candidate")
        content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
        final_text = ""
        async with Runner(app=app, session_service=sessions) as runner:
            async for event in runner.run_async(
                user_id="candidate", session_id=session.id, new_message=content,
                run_config=RunConfig(max_llm_calls=1),
            ):
                if event.usage_metadata:
                    for name in ("prompt_token_count", "candidates_token_count", "total_token_count"):
                        value = getattr(event.usage_metadata, name, None)
                        if value is not None:
                            self.last_usage[name] = value
                if event.is_final_response() and event.content and event.content.parts:
                    final_text = "".join(
                        part.text for part in event.content.parts if part.text and not part.thought
                    )
        if not final_text:
            raise PreparationError("The model returned no draft.")
        try:
            return DraftOutput.model_validate_json(final_text)
        except ValidationError as error:
            raise PreparationError("The model returned a draft in the wrong format.") from error
