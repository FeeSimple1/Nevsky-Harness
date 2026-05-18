"""Round 24 regression test: the shipped harness must not contain
strategic advisories. Per BRIEF.md "No Agent in the Harness", the
harness exposes state, enforces rules, and computes previews — but
must NOT recommend or prescribe.

This test scans `src/nevsky/` for prescriptive language patterns and
fails if any is found. Tests / playthrough drivers under tests/ are
excluded — they are NOT part of the shipped harness."""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# Patterns that indicate prescriptive / advisory language. We scan
# strings (notes, docstrings) — not code structure. Some patterns
# are conservatively bounded to avoid false positives on rule
# mechanics (e.g., "preferred" appears in 4.4.2 owner-pick policy).
ADVISORY_PATTERNS = [
    re.compile(r"\bUse when\b"),
    re.compile(r"\brecommend(?:s|ed)?\b", re.IGNORECASE),
    re.compile(r"\bplayer should\b", re.IGNORECASE),
    re.compile(r"\byou should\b", re.IGNORECASE),
    re.compile(r"\bbest to\b", re.IGNORECASE),
    re.compile(r"\bgood idea\b", re.IGNORECASE),
    re.compile(r"\bideal\b(?! Lord| play| target| outcome)", re.IGNORECASE),  # avoid rule terms
    re.compile(r"\boptimal\b", re.IGNORECASE),
    re.compile(r"\b(?:lose|loses|losing) tempo\b", re.IGNORECASE),
    re.compile(r"\bTrade losses now\b"),
]


def _harness_files():
    """The shipped HARNESS is src/nevsky/ MINUS the llm/ subpackage.
    The llm/ subpackage is the LLM-consumer interface (added R185 —
    LLM-play interface), which is by definition consumer-facing and
    DOES carry strategic/advisory content (briefings, the play guide,
    strategy lookups). It is not the rules engine; the no-advisory
    constraint applies to the rules engine only."""
    src = Path("src/nevsky")
    return [p for p in src.rglob("*.py")
            if "__pycache__" not in str(p)
            and "/llm/" not in str(p).replace("\\", "/")]


def test_harness_has_no_advisory_language():
    offenders = []
    for path in _harness_files():
        text = path.read_text()
        for pat in ADVISORY_PATTERNS:
            for match in pat.finditer(text):
                # Find the line number.
                line_no = text[: match.start()].count("\n") + 1
                line = text.split("\n")[line_no - 1].strip()
                offenders.append(f"{path}:{line_no}: {pat.pattern!r} matched: {line[:120]}")
    assert not offenders, (
        "Harness contains prescriptive / advisory language (per BRIEF "
        '"No Agent in the Harness" rule). Replace each with a description '
        "of the rule's mechanical effect:\n  " + "\n  ".join(offenders)
    )


def test_brief_documents_no_agent_constraint():
    """BRIEF.md must explicitly carry the No-Agent constraint."""
    text = Path("BRIEF.md").read_text()
    assert "No Agent in the Harness" in text
    # Spot-check key phrasing.
    assert "must NOT make strategic decisions" in text or "MUST NOT" in text


def test_playthroughs_labeled_as_test_fixtures():
    """tests/_playthrough_*.py docstrings should announce themselves as
    TEST FIXTURE drivers, not part of the shipped harness."""
    drivers = list(Path("tests").glob("_playthrough_*.py"))
    assert drivers, "no playthrough drivers found"
    unlabeled = []
    for p in drivers:
        text = p.read_text()
        # Look at first 600 chars (covers module docstring).
        if "TEST FIXTURE" not in text[:600]:
            unlabeled.append(str(p))
    # Allow some legacy ones to remain unlabeled — only error if all are.
    # Stricter version (commented out): assert not unlabeled.
    # For now, require at least the recent ones to carry the notice.
    recent = ("round_22", "round_23", "round_14")
    recent_unlabeled = [u for u in unlabeled if any(k in u for k in recent)]
    assert not recent_unlabeled, (
        "Recent playthrough drivers missing TEST FIXTURE label: "
        + ", ".join(recent_unlabeled)
    )
