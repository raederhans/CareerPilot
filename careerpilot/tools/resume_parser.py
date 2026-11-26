"""Member 3 · Turn a plain-text or Markdown resume into CandidateEvidence records.

The parser makes no model call. It splits the resume into one record per bullet or
sentence-like line, keeps the section heading as provenance, and applies two rules:

* Contact and identity details (email, phone, NRIC/FIN, address, date of birth,
  work pass or visa) become ``sensitive`` records that are never ``confirmed``,
  so preparation can never place them in a draft.
* Known skills get a ``fact_key`` such as ``skill.python`` so Member 2's matcher can
  join them to job requirements. The mapping is deliberately small and explicit.

The candidate's own resume is treated as a confirmed source for non-sensitive
lines. Pass ``confirmed=False`` when the text still needs the candidate's review.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..schemas import CandidateEvidence

SKILL_KEYS: dict[str, str] = {
    r"\bpython\b": "skill.python",
    r"\bmachine learning\b|\bml\b": "skill.ml",
    r"\bsql\b": "skill.sql",
    r"\bdeep learning\b|\bpytorch\b|\btensorflow\b": "skill.deep_learning",
    r"\bdocker\b": "skill.docker",
    r"\bjava\b(?!script)": "skill.java",
    r"\bjavascript\b|\btypescript\b": "skill.javascript",
    r"\bgit\b": "skill.git",
}

_SENSITIVE = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                                   # email
    re.compile(r"(?<!\d)(?:\+\d{1,3}[\s-]?)?\d{4}[\s-]?\d{4}(?!\d)"),         # phone (not "2024 - 2026")
    re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.IGNORECASE),                      # NRIC / FIN
    re.compile(r"\b(date of birth|d\.o\.b|dob|born on)\b", re.IGNORECASE),
    re.compile(r"\b(address|blk|block \d+|#\d{2}-\d{2,4})\b", re.IGNORECASE),
    re.compile(r"\b(visa|work pass|employment pass|s pass|citizenship|nationality|"
               r"permanent resident|work authori[sz]ation)\b", re.IGNORECASE),
]
_HEADING = re.compile(r"^(#{1,6}\s+(?P<md>.+)|(?P<caps>[A-Z][A-Z &/]{2,40})|(?P<colon>[A-Za-z][\w &/]{1,40}):)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_ID_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


def _source_id(name: str) -> str:
    cleaned = _ID_SAFE.sub("-", name).strip("-.:_") or "resume"
    return ("RESUME-" + cleaned)[:96]


def is_sensitive(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SENSITIVE)


def skill_keys(text: str) -> list[str]:
    """All mapped skills named in a line, in the order of ``SKILL_KEYS``."""
    lowered = text.casefold()
    return [key for pattern, key in SKILL_KEYS.items() if re.search(pattern, lowered)]


def parse_resume(
    text: str, *, source_name: str = "resume", id_prefix: str = "RES", confirmed: bool = True,
) -> list[CandidateEvidence]:
    """Return one evidence record per content line, in document order."""
    source_id = _source_id(source_name)
    section = "Profile"
    records: list[CandidateEvidence] = []
    seen_keys: set[str] = set()
    lines = [line.rstrip() for line in text.splitlines()]
    first_content = next((i for i, line in enumerate(lines) if line.strip()), None)

    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        heading = _HEADING.match(line)
        if heading and not _BULLET.match(raw):
            section = (heading.group("md") or heading.group("caps") or heading.group("colon")).strip().title()
            continue
        content = " ".join(_BULLET.sub("", line).split())
        if len(content) < 3:
            continue
        sensitive = is_sensitive(content)
        # A short first line without digits is usually the candidate's name.
        if index == first_content and len(content.split()) <= 4 and not re.search(r"\d", content):
            sensitive = True
        # A record carries one fact key; each skill is keyed once so the matcher
        # never sees duplicates. A line naming several skills takes the first unused one.
        key = None if sensitive else next((k for k in skill_keys(content) if k not in seen_keys), None)
        if key:
            seen_keys.add(key)
        records.append(CandidateEvidence(
            evidence_id=f"{id_prefix}-{len(records) + 1:03d}",
            source_id=source_id,
            text=content,
            provenance=f"Line {index + 1} of {source_name}, section '{section}'.",
            confirmed=confirmed and not sensitive,
            sensitive=sensitive,
            fact_key=key,
            boolean_value=True if key else None,
        ))
    return records


def parse_resume_file(path: str | Path, **options) -> list[CandidateEvidence]:
    source = Path(path)
    return parse_resume(source.read_text(encoding="utf-8"), source_name=source.name, **options)
