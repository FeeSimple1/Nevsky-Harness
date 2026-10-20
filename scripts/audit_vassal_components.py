"""Repeat the machine-readable subset of the Vassal 2.1 component audit.

Usage: PYTHONPATH=src python scripts/audit_vassal_components.py /path/Nevsky_2.1.vmod

Reads an existing download without executing the module or extracting artwork.
This is deliberately pinned to the inspected module, not a general Vassal
parser or a rules oracle. Printed transport counts and vassal counters were
checked visually; see docs/VASSAL_AUDIT_20261019.md for that evidence and limits.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from nevsky.static_data import load_cards, load_locales, load_lords


SHA256 = "efe44cf19d75e528b3270ceae1a125ef8880f2c94559ecd2ef37d8b99e0c4c57"
TERRITORIES = {"Danish Estonia", "Crusader Livonia", "Novgorodan Rus"}
FORCES = {
    "Knights": "knights", "Sergeants": "sergeants", "Men-at-Arms": "men_at_arms",
    "Light Horse": "light_horse", "Militia": "militia", "Asiatic Horse": "asiatic_horse",
}


def identifier(name):
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace(" ", "_")


def audit(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SHA256:
        raise ValueError("Module checksum differs from the inspected Nevsky 2.1 release")
    with ZipFile(path) as module:
        root = ET.fromstring(module.read("buildFile.xml"))
    problems = []
    checks = {}

    def check(label, actual, expected):
        if actual != expected:
            problems.append({"check": label, "module_adjusted": actual, "harness": expected})

    board = next(e for e in root.iter() if e.tag.endswith(".Board") and e.get("name") == "Nevsky")
    names = [identifier(e.get("name")) for z in board.iter()
             if z.tag.endswith(".Zone") and z.get("name") in TERRITORIES
             for e in z.iter() if e.tag.endswith(".Region")]
    check("locale identifiers", sorted(names), sorted(load_locales()))
    checks["locales"] = len(names)

    slots = Counter(e.get("entryName") for e in root.iter() if e.tag.endswith(".CardSlot"))
    numbered = sorted(re.match(r"([TR]\d+) -", n)[1] for n in slots
                      if re.match(r"[TR](?:[1-9]|1[0-8]) -", n))
    check("numbered Arts of War IDs", numbered,
          sorted(cid for cid, card in load_cards().items() if not card.get("no_event")))
    for side in "TR":
        check(f"{side} blank cards", slots[f"{side}0 - No Event / No Capability"],
              sum(cid.startswith(side) and bool(card.get("no_event"))
                  for cid, card in load_cards().items()))
    command = {n: c for n, c in slots.items() if n.endswith(" - Command Card")}
    check("Command card identities", len(command), 14)
    for name, count in command.items():
        check(f"Command copies: {name}", count, 3)
    checks.update(numbered_aow=len(numbered), blank_aow=6, command_cards=sum(command.values()))

    prototypes = {e.get("name"): e.text for e in root.iter()
                  if e.tag.endswith(".PrototypeDefinition")}
    lords = load_lords()
    checked_lords = []
    for name, text in prototypes.items():
        if not name.startswith("Stats "):
            continue
        short = name.removeprefix("Stats ")
        lid = "knud_and_abel" if short == "Knud" else identifier(short)
        # Stats prototypes contain no nested pieces. Their trailing field
        # lists pair directly; other prototype types need different decoding.
        traits, values = text.rsplit("/", 1)
        fields = dict((t[5:], v) for t, v in zip(
            re.split(r"\\*\t", traits.removeprefix("+/null/")),
            re.split(r"\\*\t", values)) if t.startswith("mark;"))
        for rating in ("Service", "Lordship", "Command"):
            check(f"{lid} {rating}", int(fields[rating]), lords[lid]["ratings"][rating.lower()])
        # Fealty is omitted on Teutonic Stats and wrong for Aleksandr in
        # this module. All printed Fealty ratings were reviewed separately.
        placements = re.findall(r"prototype\\;([^\\\t;]+)", prototypes[f"Mat {short}"])
        forces = Counter(FORCES[p] for p in placements if p in FORCES)
        if lid in ("hermann", "knud_and_abel"):
            forces["men_at_arms"] -= 1
            forces["militia"] += 1  # documented second-edition changes
        check(f"{lid} starting forces", dict(forces), lords[lid]["starting_forces"])
        assets = Counter()
        for placement in placements:
            match = re.fullmatch(r"(Coin|Provender|Ship) Marker (\d+)", placement)
            if match:
                assets[match[1].lower()] += int(match[2])
        if lid == "knud_and_abel":
            assets["coin"] += 1  # second edition
        check(f"{lid} fixed assets", dict(assets),
              {k: v for k, v in lords[lid]["starting_assets"].items() if v})
        checked_lords.append(lid)
    check("Lord identity coverage", sorted(checked_lords), sorted(lords))
    checks["lords"] = len(checked_lords)
    checks["saved_scenarios"] = len([e for e in root.iter()
                                     if e.tag.endswith(".PredefinedSetup") and e.get("file")])
    return {"module_sha256": digest, "checks": checks, "problems": problems,
            "limits": "Inventory, Lord Service/Lordship/Command, forces and fixed assets only; "
                      "scenario positions, map ways, printed choices and vassals reviewed separately."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    args = parser.parse_args()
    report = audit(args.module)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(bool(report["problems"]))
