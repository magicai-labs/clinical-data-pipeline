#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Magic AI Research Association

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set

COMPOUND_FIELDS: Sequence[str] = (
    "cid",
    "smiles",
    "inchikey",
    "iupac_name",
    "image_base64",
    "compound_error",
)
TRIAL_COMPACT_DROP_FIELDS = {"smiles", "inchikey", "iupac_name", "image_base64", "compound_error"}


def _load_rows(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        return [obj]
    return []


def _row_key(row: Dict[str, object]) -> str:
    cid = row.get("cid")
    collection_code = row.get("collection_code") or row.get("collection")
    trial_id = row.get("id")
    return f"{cid}|{collection_code}|{trial_id}"


def _is_clinical_trial_row(row: Dict[str, object]) -> bool:
    return (
        isinstance(row.get("cid"), int)
        and bool(row.get("id"))
        and bool(row.get("collection_code") or row.get("collection"))
    )


def _load_active_cids(path: Path | None) -> Set[int] | None:
    if path is None:
        return None
    return {
        int(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().isdigit()
    }


def _build_header(rows: Iterable[Dict[str, object]], base_first: Sequence[str]) -> List[str]:
    keys: Set[str] = set()
    for row in rows:
        keys.update(row.keys())
    ordered_base = [k for k in base_first if k in keys]
    rest = sorted([k for k in keys if k not in ordered_base])
    return ordered_base + rest


def _write_csv(path: Path, rows: List[Dict[str, object]], header: Sequence[str]) -> int:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(header))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in header})
    return len(rows)


def _write_json_array(path: Path, rows: Sequence[Dict[str, object]]) -> int:
    """Match the full exporter format: one compact JSON object per line."""
    with path.open("w", encoding="utf-8") as output:
        output.write("[\n")
        for index, row in enumerate(rows):
            if index:
                output.write(",\n")
            output.write(json.dumps(row, ensure_ascii=False))
        output.write("\n]\n")
    return len(rows)


def _extract_compounds(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    compounds_by_cid: Dict[int, Dict[str, object]] = {}
    for row in rows:
        cid = row.get("cid")
        if not isinstance(cid, int):
            continue
        candidate = {k: row.get(k) for k in COMPOUND_FIELDS}
        existing = compounds_by_cid.get(cid)
        if existing is None:
            compounds_by_cid[cid] = candidate
            continue
        for k in COMPOUND_FIELDS:
            if k == "cid":
                continue
            if existing.get(k) is None and candidate.get(k) is not None:
                existing[k] = candidate.get(k)
    return [compounds_by_cid[cid] for cid in sorted(compounds_by_cid)]


def _compact_rows(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    return [{k: v for k, v in row.items() if k not in TRIAL_COMPACT_DROP_FIELDS} for row in rows]


def main() -> int:
    p = argparse.ArgumentParser(prog="merge-trials-incremental")
    p.add_argument("--base-json", required=True, help="Existing full trials.json")
    p.add_argument("--delta-json", required=True, help="New incremental trials.json")
    p.add_argument("--out-dir", required=True, help="Output dataset directory")
    p.add_argument(
        "--active-cids-file",
        default=None,
        help="Optional successful current CID universe; rows outside it are removed",
    )
    args = p.parse_args()

    base_rows = _load_rows(Path(args.base_json))
    delta_rows = _load_rows(Path(args.delta_json))
    active_cids = _load_active_cids(Path(args.active_cids_file) if args.active_cids_file else None)

    filtered_nonclinical_rows = sum(
        1 for row in [*base_rows, *delta_rows] if not _is_clinical_trial_row(row)
    )
    inactive_cid_rows = sum(
        1
        for row in base_rows
        if _is_clinical_trial_row(row)
        and active_cids is not None
        and row.get("cid") not in active_cids
    )
    base_rows = [
        row
        for row in base_rows
        if _is_clinical_trial_row(row)
        and (active_cids is None or row.get("cid") in active_cids)
    ]
    delta_rows = [row for row in delta_rows if _is_clinical_trial_row(row)]

    merged_map: Dict[str, Dict[str, object]] = {}
    for row in base_rows:
        merged_map[_row_key(row)] = row
    for row in delta_rows:
        merged_map[_row_key(row)] = row

    merged_rows = list(merged_map.values())

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "trials.json"
    csv_path = out_dir / "trials.csv"
    compounds_json_path = out_dir / "compounds.json"
    compounds_csv_path = out_dir / "compounds.csv"
    compact_json_path = out_dir / "trials_compact.json"
    compact_csv_path = out_dir / "trials_compact.csv"
    cids_path = out_dir / "cids.txt"
    summary_path = out_dir / "summary.json"

    _write_json_array(json_path, merged_rows)

    preferred_header = [
        "cid",
        "collection",
        "collection_code",
        "id",
        "id_url",
        "title",
        "phase",
        "status",
        "date",
        "smiles",
        "inchikey",
        "iupac_name",
        "image_base64",
        "compound_error",
    ]
    header = _build_header(merged_rows, preferred_header)
    csv_rows = _write_csv(csv_path, merged_rows, header)

    compounds_rows = _extract_compounds(merged_rows)
    compounds_json_path.write_text(
        json.dumps(compounds_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    compounds_csv_rows = _write_csv(compounds_csv_path, compounds_rows, COMPOUND_FIELDS)

    compact_rows = _compact_rows(merged_rows)
    _write_json_array(compact_json_path, compact_rows)
    compact_header = _build_header(
        compact_rows,
        [
            "cid",
            "collection",
            "collection_code",
            "id",
            "id_url",
            "title",
            "phase",
            "status",
            "date",
            "cids",
            "note",
            "error",
        ],
    )
    compact_csv_rows = _write_csv(compact_csv_path, compact_rows, compact_header)

    cids = sorted({row.get("cid") for row in merged_rows if isinstance(row.get("cid"), int)})
    cids_path.write_text("\n".join(str(x) for x in cids) + ("\n" if cids else ""), encoding="utf-8")

    summary = {
        "base_json": args.base_json,
        "delta_json": args.delta_json,
        "n_base_rows": len(base_rows),
        "n_delta_rows": len(delta_rows),
        "n_filtered_nonclinical_rows": filtered_nonclinical_rows,
        "n_removed_inactive_cid_rows": inactive_cid_rows,
        "n_rows": len(merged_rows),
        "n_cids": len(cids),
        "n_compounds": len(compounds_rows),
        "json": str(json_path),
        "csv": str(csv_path),
        "compounds_json": str(compounds_json_path),
        "compounds_csv": str(compounds_csv_path),
        "trials_compact_json": str(compact_json_path),
        "trials_compact_csv": str(compact_csv_path),
        "cids": str(cids_path),
        "csv_rows": csv_rows,
        "compounds_csv_rows": compounds_csv_rows,
        "trials_compact_csv_rows": compact_csv_rows,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"base_rows: {len(base_rows)}")
    print(f"delta_rows: {len(delta_rows)}")
    print(f"merged_rows: {len(merged_rows)}")
    print(f"out_json: {json_path}")
    print(f"out_csv: {csv_path}")
    print(f"compounds_json: {compounds_json_path}")
    print(f"compounds_csv: {compounds_csv_path}")
    print(f"trials_compact_json: {compact_json_path}")
    print(f"trials_compact_csv: {compact_csv_path}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
