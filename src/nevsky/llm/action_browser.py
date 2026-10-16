"""Lossless, state-versioned presentation of the existing legal-action menu.

This module neither generates nor ranks moves. Concrete validation remains in
llm_self_play; original parameterized templates are retained alongside its
expansions. State fingerprints are private. Display versions are random session
names plus revisions, never hashes of hidden cards or future dice.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from collections import Counter
from copy import deepcopy
from typing import Any

from nevsky.llm.tools import legal_actions_for_side


class SelectionError(ValueError):
    """An invalid/stale browser selection; no fallback may be substituted."""


class MenuList(list):
    """The legacy list API, without a second menu dump in notebook displays."""

    def __repr__(self):
        return f"<Legal actions: {len(self)}; use actions() to browse or list(value) to inspect>"

    def _repr_pretty_(self, printer, cycle):
        printer.text(repr(self))


class DisplayDict(dict):
    """Full structured return data; concise notebook echo after printing it."""

    def __repr__(self):
        return "<Structured result; use dict(value) to inspect>"

    def _repr_pretty_(self, printer, cycle):
        printer.text(repr(self))


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _signature(entry):
    return encode({k: v for k, v in entry.items() if k != "_unvalidated_template"})


def _contains(value, target):
    if value == target:
        return True
    if isinstance(value, dict):
        return (isinstance(target, str) and target in value) or any(
            _contains(v, target) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains(v, target) for v in value)
    return value == target or value == f"lord:{target}"


def _field_matches(value, key, target):
    if isinstance(value, dict):
        return (key in value and _contains(value[key], target)) or any(
            _field_matches(v, key, target) for v in value.values())
    if isinstance(value, list):
        return any(_field_matches(v, key, target) for v in value)
    return False


def _literal(value):
    """Distinguish a fixed template argument from a descriptive parameter slot."""
    if isinstance(value, str):
        return not any(c in value for c in "<[{?")
    if isinstance(value, (dict, list)):
        return False
    return True


class ActionBrowser:
    """One helper session; filters never renumber the canonical catalog.

    `validated` must be the existing helper's validated-menu callable. Caller
    diagnostics remain there. Cached entries are never returned by reference.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._epoch = secrets.token_urlsafe(12)
        self._revision = 0
        self._state = None
        self._fingerprint = None
        self._catalogs = {}

    def sync(self, state):
        digest = hashlib.sha256(state.model_dump_json().encode()).digest()
        if state is not self._state or digest != self._fingerprint:
            self._state = state
            self._fingerprint = digest
            self._revision += 1
            self._catalogs.clear()
        return f"{self._epoch}.{self._revision}"

    def catalog(self, state, side, validated):
        if side not in ("teutonic", "russian"):
            raise ValueError("side must be teutonic or russian")
        version = self.sync(state)
        if side not in self._catalogs:
            legacy = deepcopy(validated(state, side))
            entries = deepcopy(legacy)
            # Expanding a pay template to one-coin examples is NOT a replacement
            # for its arbitrary legal units, recipients and combinations.
            known = {_signature(a) for a in entries}
            for original in legal_actions_for_side(state, side):
                if "args_template" in original and _signature(original) not in known:
                    entries.append(deepcopy(original))
                    known.add(_signature(original))
            self._catalogs[side] = (legacy, entries)
        legacy, entries = self._catalogs[side]
        rows = [{"id": f"{version}:{side[0]}:{i}",
                 "legacy_index": i if i < len(legacy) else None,
                 "action": deepcopy(a)} for i, a in enumerate(entries)]
        return version, MenuList(deepcopy(legacy)), rows

    def overview(self, state, side, validated):
        version, legacy, rows = self.catalog(state, side, validated)
        counts = Counter(r["action"]["type"] for r in rows)
        templates = Counter(r["action"]["type"] for r in rows
                            if "args_template" in r["action"])
        return {"version": version, "side": side, "total": len(rows),
                "legacy_total": len(legacy),
                "categories": {k: {"entries": counts[k], "templates": templates[k]}
                               for k in sorted(counts)}}

    def page(self, state, side, validated, *, category=None, lord=None,
             params=None, query=None, templates=None, page=1, page_size=12):
        if type(page) is not int or page < 1:
            raise ValueError("page must be a positive integer (first page is 1)")
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("page_size must be an integer from 1 to 100")
        if category is not None and not isinstance(category, str):
            raise TypeError("category must be an action-type string")
        if query is not None and not isinstance(query, str):
            raise TypeError("query must be a string")
        if params is not None and not isinstance(params, dict):
            raise TypeError("params must be a dictionary of argument names to values")
        if templates is not None and type(templates) is not bool:
            raise TypeError("templates must be True, False, or None")
        if lord is not None and lord not in state.lords:
            raise ValueError(f"unknown Lord {lord!r}")
        version, _, rows = self.catalog(state, side, validated)
        selected = []
        for row in rows:
            a = row["action"]
            templated = "args_template" in a
            if category is not None and a["type"] != category:
                continue
            if templates is not None and templates != templated:
                continue
            # Unbound templates are conservatively retained in Lord/argument
            # filters. Their exact applicability is checked when instantiated.
            if lord is not None and not templated and not _contains(a, lord):
                continue
            if params and not templated and not all(
                    _field_matches(a.get("args", {}), k, v) for k, v in params.items()):
                continue
            if query is not None and query.casefold() not in encode(a).casefold():
                continue
            selected.append(row)
        pages = max(1, (len(selected) + page_size - 1) // page_size)
        if page > pages:
            raise ValueError(f"page {page} out of range; {pages} page(s), no action applied")
        return DisplayDict(version=version, side=side, total=len(rows),
                           matched=len(selected), page=page, pages=pages,
                           page_size=page_size, next_page=page + 1 if page < pages else None,
                           items=selected[(page - 1) * page_size:page * page_size])

    def get(self, state, side, validated, identifier):
        version = self.sync(state)
        if not isinstance(identifier, str):
            raise SelectionError("use a displayed state-bound action ID")
        parts = identifier.split(":")
        if len(parts) != 3:
            raise SelectionError("malformed action ID; call actions() again; no action applied")
        old, owner, ordinal = parts
        if old != version:
            raise SelectionError("stale action ID: position changed or was loaded; "
                                 "call show()/actions() again; no action applied")
        if owner != side[0]:
            raise SelectionError("action ID belongs to a different perspective; "
                                 "specify its owner with side=; no action applied")
        _, _, rows = self.catalog(state, side, validated)
        if not ordinal.isdigit() or str(int(ordinal)) != ordinal or int(ordinal) >= len(rows):
            raise SelectionError("unknown action ID; no action applied")
        return deepcopy(rows[int(ordinal)])

    def resolve(self, state, side, validated, identifier, args=None):
        entry = self.get(state, side, validated, identifier)["action"]
        if args is not None and not isinstance(args, dict):
            raise SelectionError("args must be a dictionary; no action applied")
        if not isinstance(entry.get("args"), dict) and args is None:
            raise SelectionError("parameterized action: inspect action(ID), then "
                                 "apply(ID, args={...}); no action applied")
        bound = deepcopy(entry.get("args", {}))
        for key, value in entry.get("args_template", {}).items():
            if _literal(value):
                bound.setdefault(key, value)
        supplied = args or {}
        for key, value in bound.items():
            if key in supplied and supplied[key] != value:
                raise SelectionError(f"cannot change bound argument {key!r} of this ID; "
                                     "select a different action/template; no action applied")
        bound.update(deepcopy(supplied))
        return {"type": entry["type"], "side": side, "args": bound}
