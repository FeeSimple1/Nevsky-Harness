"""Round 25 regression tests: STRATEGY_DIGEST.md exists, carries the
ADVISORY disclaimer, covers the per-scenario priors, AND is not
referenced by harness code (digest is for the LLM consumer; the
engine has no runtime dependency on it)."""
from __future__ import annotations

from pathlib import Path

import pytest


DIGEST = Path("STRATEGY_DIGEST.md")


def test_digest_file_exists():
    assert DIGEST.exists(), "STRATEGY_DIGEST.md missing from repo root"


def test_digest_marked_advisory_only():
    text = DIGEST.read_text()
    # The disclaimer must be near the top.
    head = text[:1500]
    assert "ADVISORY ONLY" in head
    assert "MAY consult" in head or "may consult" in head
    # Must explicitly say the harness doesn't load or enforce it.
    assert ("does not load" in text or "will not consult" in text
            or "does not parse" in text)
    # Must explicitly grant the LLM permission to disagree / ignore.
    assert "disagree" in text.lower() or "ignore" in text.lower()


def test_digest_covers_each_canonical_scenario():
    text = DIGEST.read_text()
    for sid in ("Pleskau", "Watland", "Peipus", "Return of the Prince",
                "Crusade on Novgorod"):
        assert sid in text, f"digest missing per-scenario section for {sid}"


def test_digest_cites_smoke_findings():
    """Section 2 (Combat Math) should reference the smoke statistics
    from Round 13 / 22 (defender bias %, Knight-flip threshold, Storm
    bias). These are the project-specific findings that distinguish
    this digest from a generic strategy text."""
    text = DIGEST.read_text()
    assert "84%" in text  # 1v1 balanced defender bias
    assert "96%" in text  # 4v4 balanced defender bias
    assert "Knight" in text and "64%" in text  # Knight-flip
    assert "garrison" in text.lower()


def test_digest_describes_russian_battle_avoidant_framing():
    text = DIGEST.read_text()
    # Section 3 must capture the framing.
    assert "Battle-Avoidant" in text or "Battle-avoidant" in text
    assert "Avoid Battle" in text
    assert "Withdraw" in text


def test_digest_describes_teuton_provender_constraint():
    text = DIGEST.read_text()
    assert "Provender" in text
    # Should mention the operating window pattern.
    assert "2-3 Campaigns" in text or "2-3 campaigns" in text


def test_harness_code_does_not_reference_digest():
    """The shipped harness (rules engine in src/nevsky/) must not load
    or reference the digest. The digest is an LLM-consumer aid, not a
    runtime input for the rules engine.

    The src/nevsky/llm/ subpackage IS the LLM-consumer interface
    (R185), so it is allowed — even expected — to reference the
    digest via on-demand lookup tools. The guardrail applies to the
    rules engine only."""
    from pathlib import Path as _P
    src = _P("src/nevsky")
    assert src.is_dir()
    for p in src.rglob("*.py"):
        # The llm/ subpackage is the LLM-consumer interface; the
        # digest-reference constraint doesn't apply to it.
        if "/llm/" in str(p).replace("\\", "/"):
            continue
        text = p.read_text()
        assert "STRATEGY_DIGEST" not in text, (
            f"{p} references STRATEGY_DIGEST — the rules engine must "
            "not depend on the digest (the llm/ subpackage is exempt)"
        )


def test_brief_acknowledges_digest_status():
    """BRIEF.md should mention the digest as an advisory consumer
    document so the design intent is explicit alongside the No-Agent
    constraint."""
    brief = Path("BRIEF.md").read_text()
    # Soft check — either the digest is named, or the No-Agent section
    # mentions advisory documents.
    assert ("STRATEGY_DIGEST" in brief
            or "advisory" in brief.lower()
            or "may consult" in brief.lower())
