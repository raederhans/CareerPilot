# Application preparation agent (Member 3)

`LivePreparation` turns a selected job and the candidate's evidence into a reviewable application package: a resume draft, a cover letter, ATS answers and a claim-to-evidence map. Gemini chooses the wording. Deterministic rules decide what may be stated.

## Where it sits

The orchestrator calls `prepare(goal, job, evidence, previous, review, *, runtime)` after matching and any clarification. A `revise` review or a candidate's revision request calls it again with the previous package. The verifier then reviews the result before the candidate approves it.

```python
from careerpilot.agents import LivePreparation
from careerpilot.config import RuntimeConfig

preparation = LivePreparation(RuntimeConfig(mode="live", model="<course model>", max_model_calls=6))
flow = Orchestrator(discovery, preparation, verification, classifier, max_model_calls=6)
```

The replay adapter `ReplayPreparation` stays the default for tests and offline demos.

## Five steps

| Step | Kind | What happens |
| --- | --- | --- |
| 1 Filter | Rule | Only `confirmed` and non-`sensitive` evidence is usable. Nothing else is sent to the model. |
| 2 Rank and add feedback | Rule | Evidence is ranked against the job (shared ranking from `replay.py`). Up to 3 approved feedback examples are added when a lookup is supplied. |
| 3 Generate | Model | One ADK `LlmAgent` call with `output_schema=DraftOutput`, no retries, `max_llm_calls=1`. The job description is wrapped as untrusted data. Revision adds `prompts/revision.md`. |
| 4 Guard | Rule | Every sentence is checked (below). Failing sentences are removed and listed in `last_report.removed`. If none survive, the draft quotes the evidence verbatim. |
| 5 Render | Rule | Markdown drafts with evidence tags, `claim_evidence`, and ATS answers from the shared replay rule. |

With no usable evidence the agent makes no model call and returns an empty draft that says so.

## Guard rules

A sentence is a `fact` (cites evidence) or an `aspiration` (why the candidate wants the role, cites nothing).

| Code | Rejected when |
| --- | --- |
| `fact_without_evidence` | A fact cites no evidence |
| `unknown_or_private_evidence` | A cited ID is not confirmed, public evidence in this session |
| `eligibility_topic` | Any sentence mentions work authorisation, visas, citizenship, residency, nationality, salary or date of birth |
| `unsupported_number` | A number is not in the cited evidence |
| `unsupported_skill` | A named technology (Python, Docker, AWS, …) is absent from the cited evidence; this stops an unsupported clause riding on a supported one |
| `evidence_not_related` | The sentence shares no content word with its cited evidence |
| `aspiration_cites_evidence` / `aspiration_contains_number` / `aspiration_describes_experience` | An aspiration carries evidence, numbers or past-experience wording |
| `aspiration_in_resume` | An aspiration appears among resume bullets |
| `malformed_text` | Brackets or line breaks inside a sentence |

The prompt also asks the model not to write about eligibility topics; the `eligibility_topic` rule enforces it. ATS answers cover them from confirmed records. Semantic exaggeration (for example "comprehensive coursework") is not caught by these rules and is left to the verifier.

## Draft format (proposal for the verifier)

```text
# Resume draft for <job title>

## Relevant evidence
- <fact sentence> [CP-EV-001]

# Cover letter draft for <job title> at <company>

Dear Hiring Team,

<aspiration sentence> <fact sentence> [CP-EV-001, CP-EV-002]

Sincerely,
The candidate
```

`claim_evidence` maps each fact sentence, without its tags, to its sorted IDs. ATS entries use the key `ATS: <question>` as in the replay adapter. This format awaits Member 4's agreement; see `docs/member3-handoff.md`.

## Runtime and observability

- `runtime.reserve_model_call()` runs before the request. An exhausted budget raises before any network call.
- `last_usage` holds prompt, candidate and total token counts after a call, in the same shape as `AdkClassifier.last_usage`.
- `last_report` records whether the model was called, the evidence IDs sent, feedback IDs used, removed sentences and whether a fallback was used.
- Timeouts and malformed output raise `PreparationError`; the orchestrator records `agent_call_failed` and stops safely.

## Supporting tools

- `careerpilot/tools/resume_parser.py`: `parse_resume(text)` splits a plain-text or Markdown resume into evidence records. Contact, identity and work-pass lines become sensitive and unconfirmed. Known skills receive a `fact_key` (for example `skill.python`) for the matcher.
- `careerpilot/export.py`: `export_package(package, job, evidence, out_dir)` writes Markdown and JSON with an evidence map. Sensitive records appear by ID only. The default folder `local-data/exports` is ignored by git.

## Tests and evaluation cases

- `tests/test_preparation.py`: rules, model path with a local ADK model, revision, budget, feedback, orchestrator integration.
- `tests/test_resume_parser.py`, `tests/test_export.py`: the two tools.
- `tests/test_preparation_cases.py` with `data/golden_dataset/preparation/cases.json`: 8 labelled synthetic cases (4 dev, 4 held-out), each run offline.
- `docs/samples/`: drafts produced by the course model, with model name, date and token use.
