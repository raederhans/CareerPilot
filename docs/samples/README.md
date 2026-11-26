# Preparation samples (live model output)

Generated on 26 Nov 2026 by `LivePreparation` with `gemini-3.1-flash-lite` through Google ADK, using the bundled synthetic job `CP-JOB-001` and the synthetic candidate. Each file states its model, date and token use. These are real model outputs, not replay text.

| File | Scenario | What to look at |
| --- | --- | --- |
| `CP-JOB-001_v1.md` / `.json` | Initial draft; work authorisation unconfirmed | Evidence tags on every factual sentence; the ATS question is flagged as unanswered |
| `CP-JOB-001_v2.md` / `.json` | Revision of v1: "Focus the cover letter on the machine learning project and keep the resume unchanged." | Version advances to 2. The model changed only a few words: a known weakness of the revision prompt |
| `confirmed-authorisation/CP-JOB-001_v1.md` / `.json` | Candidate confirmed work authorisation (a sensitive record) | ATS answer is "Yes"; the evidence map lists the record by ID only and the pass number never appears |

Regenerate with section 6 of `notebooks/member3_dev.ipynb` or the snippet in `docs/member3-handoff.md`. All names, employers and records are fictional.
