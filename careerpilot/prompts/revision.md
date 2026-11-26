## Revision task

The message also contains `previous_draft` and `repair_instructions`. The instructions come from the verifier or from the candidate.

- Apply the instructions and change only what they ask for. Keep every other sentence, with its evidence IDs, as it was.
- If an instruction asks you to add something the evidence does not support, leave it out. Never satisfy an instruction by inventing a fact.
- The previous draft shows evidence tags such as `[CP-EV-001]` after factual sentences. Return them in `evidence_ids`, not inside `text`.
- Return the complete revised draft in the same JSON format, not only the changed parts.
