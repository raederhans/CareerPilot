# Design sources and implementation record

The starting point was a practical question from AutoJobApply. Once a job and a candidate record are available, which decisions can software make, and where does a candidate need to intervene? CareerPilot narrows that question to the preparation of one evidence-linked draft.

| Source | Design reference | Implementation in this project |
| --- | --- | --- |
| CA6123 Group Project Brief, 2 November 2026, §§2–4 and Appendices A–C | Four-stage agent cycle, oversight, observable decisions and reproducible Python | The notebook shows a session from intent to a reviewed, human-approved draft. Specialist evaluation is a later team milestone. |
| CareerPilot Team Development Brief v1.0, 24 November 2026, pp. 2–5 | Four team roles, shared records, two-repair ceiling, read-only tools, offline fixtures | Typed protocols, bounded session transitions, human gates and local replay adapters |
| AutoJobApply, `src/applypilot/pipeline.py` and `src/applypilot/apply/decision.py` | Staged execution and a decision before a consequential action | The orchestrator routes by intent. Candidate confirmation and approval of an exact reviewed version are explicit state transitions. |
| AutoJobApply, `src/applypilot/discovery/budget.py` and `src/applypilot/apply/application_plan.py` | Check an allowance before a call and preserve the source of a decision | Per-session step and model-call limits, stable evidence IDs, a redacted trace and a reviewable draft |

The reference revision is `9d2258b3635f6b4d75c25d0945c2bbdc94251f89` in the raederhans/AutoJobApply fork. Its upstream is Pickle-Pixel/ApplyPilot and its declared license is AGPL-3.0-only. The initial CareerPilot implementation was written for this assignment. No upstream source files, snippets, prompts, candidate records or database contents were imported. If the team later adapts source code, record the permission, original contributors, license, source revision, exact files and changes here before integration. [Reference revision](https://github.com/raederhans/AutoJobApply/tree/9d2258b3635f6b4d75c25d0945c2bbdc94251f89) · [Upstream notice](https://github.com/raederhans/AutoJobApply/blob/9d2258b3635f6b4d75c25d0945c2bbdc94251f89/NOTICE.md)

## Implementation log

| Date | Workstream | Inspectable result |
| --- | --- | --- |
| 25 Nov 2026 | Member 1 integration foundation | Shared schemas, route classifier, bounded orchestrator, JSON checkpoints, fixture adapters, notebook, architecture figure and workflow tests |
| 25 Nov 2026 | Reusability and public release checks | Catalogue injection, typed requirements and candidate facts, ranking before truncation, version and evidence checks at approval, clean-install and cross-occupation tests |
| 26 Nov 2026 | Member 3 application preparation | `LivePreparation` with one bounded ADK call and a deterministic evidence guard, preparation and revision prompts, resume parser, Markdown/JSON export, 8 labelled preparation cases and module tests ([module notes](preparation.md)). Written for this assignment with AI coding assistance, which is disclosed on the final video slide. Ranking and ATS answer rules are reused from Member 1's `replay.py`. |

The example employer names, job listings, skills records and permission answer are fictional. Source IDs exist to make the examples traceable within the prototype.
