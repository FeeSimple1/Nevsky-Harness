"""Ransom capability controls. Combat and Disband are covered through public actions."""


def test_smoke_101_apply_ransom_no_recipient_when_no_friendly_lord():
    """If killer side has Ransom in play but no friendly Lord is at the
    Locale, apply_ransom still returns {"ransom": True} with the coin
    "lost_no_recipient" — same shape used by existing callers."""
    from nevsky.campaign import apply_ransom
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play = ["T16"]  # Teutonic Ransom
    rus = next(lid for lid, lord in s.lords.items()
               if lord.side == "russian" and lord.state == "mustered")
    # No Teutonic Lord at pskov for the test.
    for lord in s.lords.values():
        if lord.side == "teutonic" and lord.location == "pskov":
            lord.location = "riga"
    res = apply_ransom(s, rus, "teutonic", "pskov")
    assert res["ransom"] is True
    assert "coin_lost_no_recipient" in res


def test_smoke_101_apply_ransom_no_ransom_capability():
    """If killer side has no Ransom in play, return {"ransom": False}."""
    from nevsky.campaign import apply_ransom
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=2)
    # No Ransom capability for teutonic.
    s.decks.teutonic.capabilities_in_play = []
    rus = next(lid for lid, lord in s.lords.items()
               if lord.side == "russian" and lord.state == "mustered")
    res = apply_ransom(s, rus, "teutonic", "pskov")
    assert res["ransom"] is False
