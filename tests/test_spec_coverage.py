"""
Forced spec<->case coverage check.

Two layers guarantee coverage cannot drift silently:

1. Manifest reconciliation: every spec-ID in ``spec_manifest.yml`` has a YAML case
   and vice-versa, per entity (a missing case, an orphan case, or a case whose
   ``entity`` field is wrong all fail).
2. Physical placement: case files carry no duplicate id, sit in the directory that
   matches their ``entity``, and are named after their id (``2.1.1.1`` ->
   ``2_1_1_1.yml``). The set-based reconciliation alone cannot see these — a
   duplicate id collapses in a set and a misfiled/misnamed file is invisible to
   it — so they are enforced separately here.

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


def _real_records() -> list[tuple[str, str, str]]:
    """(relative-path, id, entity) for every case file on disk."""
    cases_dir = Path(__file__).parent / "cases"
    records: list[tuple[str, str, str]] = []
    for path in sorted(cases_dir.glob("**/*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        rel = path.relative_to(cases_dir).as_posix()
        records.append((rel, data["id"], data["entity"]))
    return records


def _placement_problems(records: list[tuple[str, str, str]]) -> list[str]:
    """Structural problems the set-based manifest reconciliation cannot see.

    ``records`` is a list of (relative-path, id, entity). Flags any file whose
    name disagrees with its id, whose directory disagrees with its entity, or any
    id that appears in more than one file.
    """
    problems: list[str] = []
    by_id: dict[str, list[str]] = defaultdict(list)
    for rel, case_id, entity in records:
        p = Path(rel)
        expected_stem = case_id.replace(".", "_")
        if p.stem != expected_stem:
            problems.append(
                f"{rel}: filename '{p.name}' does not match id '{case_id}' "
                f"(expected '{expected_stem}.yml')"
            )
        if p.parent.name != entity:
            problems.append(
                f"{rel}: directory '{p.parent.name}' does not match entity '{entity}'"
            )
        by_id[case_id].append(rel)
    for case_id, paths in sorted(by_id.items()):
        if len(paths) > 1:
            problems.append(f"duplicate id '{case_id}' across files: {sorted(paths)}")
    return problems


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


# ---------------------------------------------------------------------------
# Physical placement: the manifest check above compares *sets* of ids, so it
# cannot see a duplicate id, a file in the wrong entity folder, or a filename
# that disagrees with its id. These checks enforce the "exactly one, correctly
# filed" promise the set comparison alone does not.
# ---------------------------------------------------------------------------

def test_case_files_are_well_placed():
    assert _placement_problems(_real_records()) == []


def test_placement_problems_detects_duplicate_id():
    records = [
        ("hub/2_1_1_1.yml", "2.1.1.1", "hub"),
        ("hub/2_1_1_1.yml", "2.1.1.1", "hub"),
    ]
    problems = _placement_problems(records)
    assert any("duplicate id" in p and "2.1.1.1" in p for p in problems)


def test_placement_problems_detects_wrong_directory():
    # stem matches the id, but the file sits under link/ while entity is hub.
    records = [("link/2_1_1_1.yml", "2.1.1.1", "hub")]
    problems = _placement_problems(records)
    assert any("directory" in p for p in problems)
    assert not any("filename" in p for p in problems)


def test_placement_problems_detects_filename_mismatch():
    # directory matches the entity, but the filename has nothing to do with the id.
    records = [("hub/banana.yml", "2.1.1.1", "hub")]
    problems = _placement_problems(records)
    assert any("filename" in p for p in problems)
    assert not any("directory" in p for p in problems)
