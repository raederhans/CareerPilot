# Member 3 handoff · application preparation

**From:** Member 3 (Yuan) · **Branch:** `member3-preparation` · **Status on 26 Nov 2026:** module complete and tested; integration decisions open below.

The live preparation agent, its tools and its tests are ready on the branch. The full suite passes (220 tests on Python 3.12 with `google-adk==2.15.1`). Live runs with `gemini-3.1-flash-lite` reach `awaiting_approval` through the orchestrator. Design notes: [preparation.md](preparation.md). Live outputs: [samples/](samples/).

## What is ready

| Item | Location |
| --- | --- |
| `LivePreparation` (one bounded ADK call, deterministic evidence guard, revision path) | `careerpilot/agents/preparation.py` |
| Drafting and revision prompts | `careerpilot/prompts/preparation.md`, `revision.md` |
| Resume parser (plain text or Markdown → `CandidateEvidence`) | `careerpilot/tools/resume_parser.py` |
| Markdown/JSON export with an evidence map | `careerpilot/export.py` |
| 8 labelled preparation cases (4 dev, 4 held-out) | `data/golden_dataset/preparation/` |
| Tests | `tests/test_preparation.py`, `test_preparation_cases.py`, `test_resume_parser.py`, `test_export.py` |
| Live samples with model, date and token use | `docs/samples/` |

## Open decisions (please fill in before the 29 Nov integration)

| # | Owner | Question | Proposal from Member 3 | Decision |
| --- | --- | --- | --- | --- |
| 1 | Member 4 | Draft format the verifier parses | Each factual sentence ends with `[EV-ID]` or `[EV-1, EV-2]`; `claim_evidence` keys are the sentence text without tags; aspiration sentences carry no tag; ATS keys stay `ATS: <question>` | |
| 2 | Member 4 | Feedback lookup for few-shot reuse | `feedback_lookup(ids) -> list[dict]`, each dict with `before`, `after`, `note`; Member 3 injects up to 3 | |
| 3 | Member 1 | How clarification requests travel | Keep the contract: unresolved ATS answers are `None`, the verifier returns `human_required`, the orchestrator pauses | |
| 4 | Member 1 | Token usage in the trace for specialists | Read `last_usage` from any agent object, not only the classifier (patch below) | |
| 5 | Member 1 | A live model sometimes returns an unchanged revision | Today this raises `UnsupportedRevision` and the session ends `blocked`. Option: count it as one repair attempt and try again within `max_repairs` | |
| 6 | Member 1 + 4 | Course model name and budget per session | `gemini-3.1-flash-lite`; preparation uses 1 call per draft and 1 per repair, about 1,300 tokens each | |

## For Member 1 · orchestrator and notebook

1. **Plug in the agent for live mode.** The replay adapter stays the default for tests.

    ```python
    from careerpilot.agents import LivePreparation

    config = RuntimeConfig.from_env()            # CAREERPILOT_MODE=live etc.
    preparation = LivePreparation(config) if config.mode == "live" else ReplayPreparation()
    flow = Orchestrator(discovery, preparation, verification, config=config)
    ```

    Budget: classification 1 + preparation up to 3 (first draft and two repairs) + Members 2 and 4. Set `CAREERPILOT_MAX_MODEL_CALLS` accordingly.

2. **Record specialist token usage (decision 4).** In `Orchestrator._call`, the usage block runs only for `tool == "classify"`. A general version:

    ```python
    source = {"classify": self.classifier, "prepare": self.preparation,
              "review": self.verification, "discover": self.discovery, "match": self.discovery}.get(tool)
    reported = getattr(source, "last_usage", {}) if state.model_calls_used > before else {}
    ```

3. **Do not combine `LivePreparation` with `ReplayVerification`.** The replay verifier accepts only the replay template, so every model-written draft returns `revise` and the session ends `repair_limit_exhausted`. Until Member 4's verifier lands, use the interim verifier in `tests/test_preparation.py` (`InterimVerification`) or keep replay for both.

## For Member 4 · verification, learning and evaluation

1. **Agree on the draft format (decision 1).** Examples: `docs/samples/CP-JOB-001_v1.md`. The guard's issue codes (`eligibility_topic`, `unsupported_number`, `unsupported_skill`, `unknown_or_private_evidence`, …) can double as verifier error codes if useful.
2. **What the guard cannot judge.** It is lexical. Please cover these semantically:
    - exaggeration that adds no new term, for example "comprehensive coursework";
    - a sentence that names the right skill but overstates what the evidence says;
    - whether a revision actually followed its instruction (see the weak v2 sample).
3. **Feedback store (decision 2).** Pass the lookup when constructing the agent: `LivePreparation(config, feedback_lookup=store.get)`. Approved IDs arrive through `runtime.approved_feedback_ids`; `last_report.feedback_ids_used` shows which were applied.
4. **Evaluation cases.** `data/golden_dataset/preparation/cases.json` uses a proposed format (`careerpilot-preparation-cases/v0`); rename fields freely. Held-out cases PREP-003, 004, 006, 007 have not been used for tuning. Live self-check on the dev cases (26 Nov, one run each):

    | Case | Model called | Forbidden phrases | Extra numbers | Citations allowed | ATS correct | Removed by guard |
    | --- | --- | --- | --- | --- | --- | --- |
    | PREP-001 | yes | none | none | yes | yes | none |
    | PREP-002 | no | none | none | yes | yes | none |
    | PREP-005 | yes | none | none | yes | yes | 1 `unsupported_skill` |
    | PREP-008 | yes | none | none | yes | yes | none |

    These are single runs on 4 cases, not an evaluation result. The comparison experiments and the grounded-claim rate belong to your runner.

## For Member 2 · discovery and matching

1. **Fact keys.** `parse_resume` assigns `skill.python`, `skill.ml`, `skill.sql`, `skill.deep_learning`, `skill.docker`, `skill.java`, `skill.javascript` and `skill.git` (`SKILL_KEYS` in `resume_parser.py`). Please use the same names in job requirements, or tell me the names you prefer.
2. **One key per record.** A line naming several skills receives the first key not yet used, so the matcher never sees two records for one key.
3. **Skill words in evidence text.** The `unsupported_skill` rule compares named technologies with the cited evidence text, not its `fact_key`. If your retrieval creates evidence records, include the skill name in `text`. In PREP-005 a record keyed `skill.python` did not say "Python", and a model sentence about Python was removed.
4. **Evidence IDs must stay stable** between matching and preparation, since drafts cite them.

## Known limitations

- Revision quality is weak: in the v2 sample the model changed only a few words. A stronger revision prompt or a verifier check is the next improvement.
- The guard is lexical; semantic overstatement passes it (see Member 4, item 2).
- The resume parser treats a short first line as the candidate's name and marks it sensitive; it cannot detect every personal detail.

## Regenerate the samples

From the project root with `.env` holding `GOOGLE_API_KEY`:

```python
from careerpilot.agents import LivePreparation
from careerpilot.catalog import load_evidence, load_jobs
from careerpilot.config import RuntimeConfig
from careerpilot.export import export_package
from careerpilot.schemas import UserGoal

class Runtime:
    approved_feedback_ids = ()
    def reserve_model_call(self): pass

job, evidence = load_jobs()[0], load_evidence()
agent = LivePreparation(RuntimeConfig(mode="live", model="gemini-3.1-flash-lite", max_model_calls=5))
package = agent.prepare(UserGoal(intent="prepare"), job, evidence, None, None, runtime=Runtime())
export_package(package, job, evidence, "docs/samples",
               metadata={"model": "gemini-3.1-flash-lite", "total_token_count": agent.last_usage.get("total_token_count")})
```
