"""Member 3 · Export an ApplicationPackage for human review as Markdown and JSON.

Both files carry an evidence map: every claim with the IDs, source and provenance
it rests on. A sensitive record is listed by ID only; its text never leaves the
session. Files go to ``local-data/exports`` by default, which git ignores.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .schemas import ApplicationPackage, CandidateEvidence, JobRecord

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "local-data" / "exports"
SENSITIVE_PLACEHOLDER = "(sensitive record: text withheld)"


def evidence_map(
    package: ApplicationPackage, evidence: Sequence[CandidateEvidence],
) -> list[dict[str, Any]]:
    """One row per claim, resolving each ID to its source without exposing sensitive text."""
    by_id = {item.evidence_id: item for item in evidence}
    rows = []
    for claim, refs in package.claim_evidence.items():
        sources = []
        for ref in refs:
            item = by_id.get(ref)
            if item is None:
                sources.append({"evidence_id": ref, "text": "(missing from session)", "provenance": ""})
            elif item.sensitive:
                sources.append({"evidence_id": ref, "text": SENSITIVE_PLACEHOLDER, "provenance": ""})
            else:
                sources.append({"evidence_id": ref, "text": item.text, "provenance": item.provenance})
        rows.append({"claim": claim, "sources": sources})
    return rows


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(
    package: ApplicationPackage, job: JobRecord, evidence: Sequence[CandidateEvidence],
    *, metadata: dict[str, Any] | None = None,
) -> str:
    meta = metadata or {}
    lines = [
        f"# Application package · {job.title} at {job.company}",
        "",
        f"- Job ID: `{job.job_id}` · Version: {package.version}",
        f"- Exported: {meta.get('exported_at', '')}",
    ]
    for key in ("model", "total_token_count", "note"):
        if key in meta:
            lines.append(f"- {key.replace('_', ' ').capitalize()}: {meta[key]}")
    lines += ["", "---", "", package.resume_draft, "", "---", "", package.cover_letter, "", "---", "",
              "## Application questions", ""]
    if package.ats_answers:
        lines += ["| Question | Answer |", "| --- | --- |"]
        lines += [
            f"| {_cell(q)} | {_cell(a) if a is not None else '**Unanswered: the candidate must confirm**'} |"
            for q, a in package.ats_answers.items()
        ]
    else:
        lines.append("This job asks no application questions.")
    lines += ["", "## Evidence map", "", "| Claim | Evidence | Source text | Provenance |",
              "| --- | --- | --- | --- |"]
    for row in evidence_map(package, evidence):
        for source in row["sources"]:
            lines.append(
                f"| {_cell(row['claim'])} | `{source['evidence_id']}` | {_cell(source['text'])} "
                f"| {_cell(source['provenance'])} |"
            )
    return "\n".join(lines) + "\n"


def export_package(
    package: ApplicationPackage, job: JobRecord, evidence: Sequence[CandidateEvidence],
    out_dir: str | Path | None = None, *, metadata: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write ``<job_id>_v<version>.md`` and ``.json``; return both paths."""
    if package.job_id != job.job_id:
        raise ValueError("The package belongs to a different job.")
    meta = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **(metadata or {})}
    target = Path(out_dir) if out_dir is not None else DEFAULT_DIR
    target.mkdir(parents=True, exist_ok=True)
    stem = f"{job.job_id}_v{package.version}"
    md_path = target / f"{stem}.md"
    json_path = target / f"{stem}.json"
    md_path.write_text(to_markdown(package, job, evidence, metadata=meta), encoding="utf-8")
    json_path.write_text(json.dumps({
        "metadata": meta,
        "job": {"job_id": job.job_id, "title": job.title, "company": job.company},
        "package": package.model_dump(mode="json"),
        "evidence_map": evidence_map(package, evidence),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path
