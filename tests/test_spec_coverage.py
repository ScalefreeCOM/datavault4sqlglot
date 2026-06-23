"""
Forced spec<->case coverage check.

This test guarantees every spec-ID has an executable case: it loads the manifest
(``spec_manifest.yml``) and the
actual YAML cases, then asserts they match exactly *per entity*. A spec-ID without
a case, a case without a manifest entry, or a case filed under the wrong entity all
fail here — so coverage drift can never pass silently.

Run with:  python -m pytest tests/test_spec_coverage.py -v
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml

from cases.case_loader import load_all_cases

_MANIFEST = Path(__file__).parent / "spec_manifest.yml"


# Top-level manifest keys that are NOT entity -> id lists.
_NON_ENTITY_KEYS = {"partial_coverage"}


def _load_manifest() -> dict:
    return yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))


def _manifest_ids(data: dict) -> dict[str, set[str]]:
    return {k: set(v or []) for k, v in data.items() if k not in _NON_ENTITY_KEYS}


def _case_ids() -> dict[str, set[str]]:
    by_entity: dict[str, set[str]] = defaultdict(set)
    for case in load_all_cases():
        by_entity[case.entity.value].add(case.id)
    return dict(by_entity)


def test_spec_coverage_matches_manifest():
    manifest = _manifest_ids(_load_manifest())
    cases = _case_ids()

    problems: list[str] = []
    for entity in sorted(set(manifest) | set(cases)):
        want = manifest.get(entity, set())
        have = cases.get(entity, set())
        missing = sorted(want - have)   # spec-ID with no case
        orphan = sorted(have - want)    # case with no manifest entry
        if missing:
            problems.append(f"[{entity}] spec-IDs without a case: {missing}")
        if orphan:
            problems.append(f"[{entity}] cases without a manifest entry: {orphan}")

    assert not problems, "Spec coverage drift:\n" + "\n".join(problems)


def test_partial_coverage_entries_reference_real_cases():
    # partial_coverage documents IDs whose case only PARTIALLY asserts the spec.
    # Guard against drift: every ID listed there must correspond to a real case.
    partial = _load_manifest().get("partial_coverage") or {}
    case_ids = {case.id for case in load_all_cases()}
    unknown = sorted(set(partial) - case_ids)
    assert not unknown, f"partial_coverage lists IDs with no case: {unknown}"
