#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Magic AI Research Association

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import requests

from clinical_data_analyzer.pubchem import (
    PubChemClassificationClient,
    PubChemClient,
    PubChemWebFallbackClient,
)

COMPOUND_FIELDS: Sequence[str] = (
    "cid",
    "smiles",
    "inchikey",
    "iupac_name",
    "image_base64",
    "compound_error",
)
TRIAL_COMPACT_DROP_FIELDS = {"smiles", "inchikey", "iupac_name", "image_base64", "compound_error"}


def _parse_csv_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _read_cids_file(path: Path) -> List[int]:
    if not path.exists():
        raise FileNotFoundError(f"cids file not found: {path}")
    vals: List[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.isdigit():
            vals.append(int(s))
    return vals


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_jsonl(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _iter_jsonl(path: Path) -> Iterable[Dict[str, object]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _iter_json_rows(path: Path) -> Iterable[Dict[str, object]]:
    if not path.exists():
        return
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        for row in obj:
            if isinstance(row, dict):
                yield row
        return
    if isinstance(obj, dict):
        yield obj


def _extract_processed_cids(path: Path) -> Set[int]:
    out: Set[int] = set()
    for row in _iter_jsonl(path) or []:
        cid = row.get("cid")
        if isinstance(cid, int):
            out.add(cid)
    return out


def _build_union_header(path: Path, base_first: Sequence[str]) -> List[str]:
    keys: Set[str] = set()
    for row in _iter_jsonl(path) or []:
        keys.update(row.keys())
    ordered_base = [k for k in base_first if k in keys]
    rest = sorted([k for k in keys if k not in ordered_base])
    return ordered_base + rest


def _write_csv_from_jsonl(jsonl_path: Path, csv_path: Path, header: Sequence[str]) -> int:
    n = 0
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(header))
        w.writeheader()
        for row in _iter_jsonl(jsonl_path) or []:
            w.writerow({k: row.get(k) for k in header})
            n += 1
    return n


def _write_json_array_from_jsonl(jsonl_path: Path, json_path: Path) -> int:
    n = 0
    with json_path.open("w", encoding="utf-8") as out:
        out.write("[\n")
        first = True
        for row in _iter_jsonl(jsonl_path) or []:
            if not first:
                out.write(",\n")
            out.write(json.dumps(row, ensure_ascii=False))
            first = False
            n += 1
        out.write("\n]\n")
    return n


def _extract_compounds_from_jsonl(jsonl_path: Path) -> List[Dict[str, object]]:
    compounds_by_cid: Dict[int, Dict[str, object]] = {}
    for row in _iter_jsonl(jsonl_path) or []:
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


def _write_json_rows(path: Path, rows: Sequence[Dict[str, object]]) -> int:
    path.write_text(json.dumps(list(rows), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(rows)


def _write_csv_rows(path: Path, rows: Sequence[Dict[str, object]], header: Sequence[str]) -> int:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(header))
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in header})
    return len(rows)


def _build_compact_header(path: Path, base_first: Sequence[str]) -> List[str]:
    keys: Set[str] = set()
    for row in _iter_jsonl(path) or []:
        keys.update({k for k in row.keys() if k not in TRIAL_COMPACT_DROP_FIELDS})
    ordered_base = [k for k in base_first if k in keys]
    rest = sorted([k for k in keys if k not in ordered_base])
    return ordered_base + rest


def _write_compact_csv_from_jsonl(jsonl_path: Path, csv_path: Path, header: Sequence[str]) -> int:
    n = 0
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(header))
        w.writeheader()
        for row in _iter_jsonl(jsonl_path) or []:
            compact = {k: v for k, v in row.items() if k not in TRIAL_COMPACT_DROP_FIELDS}
            w.writerow({k: compact.get(k) for k in header})
            n += 1
    return n


def _write_compact_json_from_jsonl(jsonl_path: Path, json_path: Path) -> int:
    n = 0
    with json_path.open("w", encoding="utf-8") as out:
        out.write("[\n")
        first = True
        for row in _iter_jsonl(jsonl_path) or []:
            compact = {k: v for k, v in row.items() if k not in TRIAL_COMPACT_DROP_FIELDS}
            if not first:
                out.write(",\n")
            out.write(json.dumps(compact, ensure_ascii=False))
            first = False
            n += 1
        out.write("\n]\n")
    return n


def _fetch_png_data_uri(cid: int, *, image_size: str = "400x400", timeout: float = 60.0) -> Tuple[Optional[str], Optional[str]]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG"
    params = {"image_size": image_size}
    transient_http_status = {429, 500, 502, 503, 504}
    retries = 3

    for attempt in range(1, retries + 1):
        try:
            with requests.Session() as s:
                r = s.get(url, params=params, timeout=timeout)
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                if r.status_code in transient_http_status and attempt < retries:
                    time.sleep(0.6 * attempt)
                    continue
                return None, f"image_http_error:{r.status_code}:{e}"

            b64 = base64.b64encode(r.content).decode("ascii")
            return f"data:image/png;base64,{b64}", None
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(0.6 * attempt)
                continue
            return None, f"image_request_error:{type(e).__name__}:{e}"
    return None, "image_fetch_exhausted"


def _dedupe(values: Sequence[int]) -> List[int]:
    seen: Set[int] = set()
    out: List[int] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _sanitize_trial_row(row: Dict[str, object]) -> Dict[str, object]:
    # Keep normalized schema (`id`, `date`) only.
    drop_keys = {"ctid", "eudractnumber", "updatedate"}
    return {k: v for k, v in row.items() if k not in drop_keys}


def _trial_key(row: Dict[str, object]) -> str:
    cid = row.get("cid")
    collection_code = row.get("collection_code") or row.get("collection")
    trial_id = row.get("id")
    return f"{cid}|{collection_code}|{trial_id}"


def _trial_hash(row: Dict[str, object]) -> str:
    # Treat missing optional fields and explicit nulls as equivalent for incremental comparison.
    stable = {k: v for k, v in row.items() if k != "image_base64" and v is not None}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_incremental_index(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in _iter_json_rows(path) or []:
        out[_trial_key(row)] = _trial_hash(row)
    return out


def _select_incremental_rows(rows: List[Dict[str, object]], index: Optional[Dict[str, str]]) -> Tuple[List[Dict[str, object]], int, int, int]:
    if index is None:
        return rows, len(rows), 0, 0

    selected: List[Dict[str, object]] = []
    n_new = 0
    n_changed = 0
    n_skipped = 0

    for row in rows:
        key = _trial_key(row)
        current_hash = _trial_hash(row)
        previous_hash = index.get(key)
        if previous_hash is None:
            selected.append(row)
            n_new += 1
            continue
        if previous_hash != current_hash:
            selected.append(row)
            n_changed += 1
            continue
        n_skipped += 1

    return selected, n_new, n_changed, n_skipped


def _print_progress(
    *,
    idx: int,
    total: int,
    cid: int,
    added_rows: int,
    total_rows: int,
    skipped: bool = False,
    errored: bool = False,
) -> None:
    pct = (idx / total * 100.0) if total else 0.0
    status = "skipped" if skipped else ("error" if errored else "ok")
    print(
        f"[export] {idx}/{total} ({pct:.1f}%) cid={cid} status={status} "
        f"added_rows={added_rows} total_rows={total_rows}"
    )


def main() -> int:
    p = argparse.ArgumentParser(prog="export-pubchem-trials-dataset")
    p.add_argument("--hnid", type=int, default=1856916, help="PubChem HNID (default: 1856916)")
    p.add_argument("--extra-hnids", default=None, help="Comma-separated extra HNIDs")
    p.add_argument(
        "--cids-file",
        default=None,
        help="Optional precomputed CID text file (one CID per line). If set, HNID fetch is skipped.",
    )
    p.add_argument("--limit-cids", type=int, default=None, help="Limit number of CIDs for testing")
    p.add_argument("--cid-offset", type=int, default=0, help="Start index in deduped CID list (for shard runs)")
    p.add_argument("--cid-count", type=int, default=None, help="Number of CIDs to process from offset")
    p.add_argument("--out-dir", default="out/pubchem_trials_dataset", help="Output directory")
    p.add_argument(
        "--collections",
        default="clinicaltrials,clinicaltrials_eu,clinicaltrials_jp",
        help="Comma-separated SDQ collections",
    )
    p.add_argument("--limit-per-collection", type=int, default=200, help="Max rows per collection per CID")
    p.add_argument("--image-size", default="400x400", help="2D PNG size (e.g. 300x300)")
    p.add_argument("--skip-images", action="store_true", help="Do not fetch 2D PNG images")
    p.add_argument("--resume", action="store_true", help="Resume from existing trials.jsonl")
    p.add_argument(
        "--incremental-from",
        default=None,
        help="If set, compare with existing trials.json and write only new/changed rows",
    )
    p.add_argument("--progress-every", type=int, default=50, help="Progress print interval")
    p.add_argument("--show-progress", action="store_true", help="Print per-CID progress logs")
    args = p.parse_args()
    if args.cid_offset < 0:
        raise ValueError("--cid-offset must be >= 0")
    if args.cid_count is not None and args.cid_count <= 0:
        raise ValueError("--cid-count must be > 0")
    if args.cid_count is not None and args.limit_cids is not None:
        raise ValueError("Use either --cid-count or --limit-cids, not both")

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    cids_txt = out_dir / "cids.txt"
    jsonl_path = out_dir / "trials.jsonl"
    csv_path = out_dir / "trials.csv"
    json_path = out_dir / "trials.json"
    compounds_json_path = out_dir / "compounds.json"
    compounds_csv_path = out_dir / "compounds.csv"
    trials_compact_json_path = out_dir / "trials_compact.json"
    trials_compact_csv_path = out_dir / "trials_compact.csv"
    summary_path = out_dir / "summary.json"

    if not args.resume and jsonl_path.exists():
        jsonl_path.unlink()

    class_client = PubChemClassificationClient()
    pubchem = PubChemClient()
    fallback = PubChemWebFallbackClient()

    hnids = [args.hnid] + [int(x) for x in _parse_csv_list(args.extra_hnids)]

    # 1) Collect and dedupe CIDs
    cids: List[int] = []
    if args.cids_file:
        cids = _dedupe(_read_cids_file(Path(args.cids_file)))
    else:
        for hnid in hnids:
            cids.extend(class_client.get_cids(hnid, fmt="TXT"))
        cids = _dedupe(cids)
    total_cids_before_slice = len(cids)

    if args.cid_offset:
        cids = cids[args.cid_offset :]

    if args.cid_count is not None:
        cids = cids[: args.cid_count]
    elif args.limit_cids is not None:
        cids = cids[: args.limit_cids]

    cids_txt.write_text("\n".join(str(c) for c in cids) + "\n", encoding="utf-8")

    collections = tuple(_parse_csv_list(args.collections))
    if not collections:
        raise ValueError("At least one collection is required")

    processed_cids: Set[int] = set()
    if args.resume and jsonl_path.exists():
        processed_cids = _extract_processed_cids(jsonl_path)

    incremental_index: Optional[Dict[str, str]] = None
    if args.incremental_from:
        incremental_path = Path(args.incremental_from)
        incremental_index = _load_incremental_index(incremental_path)
        print(f"[export] incremental baseline={incremental_path} indexed_keys={len(incremental_index)}")

    print(
        f"[export] start hnids={hnids} collections={list(collections)} "
        f"cids={len(cids)} total_cids={total_cids_before_slice} "
        f"offset={args.cid_offset} count={args.cid_count} "
        f"resume={args.resume} skip_images={args.skip_images}"
    )

    total_rows = 0
    total_with_trials = 0
    total_with_errors = 0
    total_new_rows = 0
    total_changed_rows = 0
    total_skipped_unchanged_rows = 0

    # 2) CID -> trials union rows + smiles + image
    for idx, cid in enumerate(cids, start=1):
        if cid in processed_cids:
            if args.show_progress:
                _print_progress(
                    idx=idx,
                    total=len(cids),
                    cid=cid,
                    added_rows=0,
                    total_rows=total_rows,
                    skipped=True,
                )
            continue

        smiles = None
        inchikey = None
        iupac_name = None
        compound_error = None
        try:
            props = pubchem.compound_properties(cid)
            smiles = props.get("CanonicalSMILES")
            inchikey = props.get("InChIKey")
            iupac_name = props.get("IUPACName")
        except Exception as e:
            compound_error = f"compound_props_error:{type(e).__name__}:{e}"

        image_base64 = None
        if not args.skip_images:
            image_base64, _ = _fetch_png_data_uri(cid, image_size=args.image_size)

        try:
            union_rows, _ = fallback.get_normalized_trials_union(
                cid,
                collections=collections,
                limit_per_collection=args.limit_per_collection,
            )
        except Exception as e:
            err_row = {
                "cid": cid,
                "collections": list(collections),
                "error": f"trials_union_error:{type(e).__name__}:{e}",
                "smiles": smiles,
                "inchikey": inchikey,
                "iupac_name": iupac_name,
                "compound_error": compound_error,
                "image_base64": image_base64,
            }
            selected_rows, n_new, n_changed, n_skipped = _select_incremental_rows([err_row], incremental_index)
            if selected_rows:
                _write_jsonl(jsonl_path, selected_rows)
            total_rows += len(selected_rows)
            total_with_errors += 1
            total_new_rows += n_new
            total_changed_rows += n_changed
            total_skipped_unchanged_rows += n_skipped
            if args.show_progress:
                _print_progress(
                    idx=idx,
                    total=len(cids),
                    cid=cid,
                    added_rows=len(selected_rows),
                    total_rows=total_rows,
                    errored=True,
                )
            continue

        if union_rows:
            total_with_trials += 1
        else:
            # Keep a placeholder row for traceability
            union_rows = [
                {
                    "collection": None,
                    "id": None,
                    "title": None,
                    "phase": None,
                    "status": None,
                    "date": None,
                    "id_url": None,
                    "cids": None,
                    "note": "no_trials_found",
                }
            ]

        out_rows: List[Dict[str, object]] = []
        for r in union_rows:
            row = _sanitize_trial_row(dict(r))
            row.update(
                {
                    "cid": cid,
                    "smiles": smiles,
                    "inchikey": inchikey,
                    "iupac_name": iupac_name,
                    "compound_error": compound_error,
                    "image_base64": image_base64,
                }
            )
            out_rows.append(row)

        selected_rows, n_new, n_changed, n_skipped = _select_incremental_rows(out_rows, incremental_index)
        if selected_rows:
            _write_jsonl(jsonl_path, selected_rows)
        total_rows += len(selected_rows)
        total_new_rows += n_new
        total_changed_rows += n_changed
        total_skipped_unchanged_rows += n_skipped

        if args.show_progress:
            _print_progress(
                idx=idx,
                total=len(cids),
                cid=cid,
                added_rows=len(selected_rows),
                total_rows=total_rows,
            )

        if args.progress_every > 0 and (idx % args.progress_every == 0 or idx == len(cids)):
            print(f"[export] processed {idx}/{len(cids)} cids, rows={total_rows}")

    # 3) Export CSV and JSON array from JSONL
    preferred_header = [
        "cid",
        "collection",
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
    header = _build_union_header(jsonl_path, preferred_header)
    csv_rows = _write_csv_from_jsonl(jsonl_path, csv_path, header)
    json_rows = _write_json_array_from_jsonl(jsonl_path, json_path)

    compounds_rows = _extract_compounds_from_jsonl(jsonl_path)
    compounds_json_rows = _write_json_rows(compounds_json_path, compounds_rows)
    compounds_csv_rows = _write_csv_rows(compounds_csv_path, compounds_rows, COMPOUND_FIELDS)

    compact_preferred_header = [
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
    ]
    compact_header = _build_compact_header(jsonl_path, compact_preferred_header)
    compact_csv_rows = _write_compact_csv_from_jsonl(jsonl_path, trials_compact_csv_path, compact_header)
    compact_json_rows = _write_compact_json_from_jsonl(jsonl_path, trials_compact_json_path)

    summary = {
        "hnids": hnids,
        "collections": list(collections),
        "cid_offset": args.cid_offset,
        "cid_count": args.cid_count,
        "cids_file": args.cids_file,
        "n_cids_total": total_cids_before_slice,
        "n_cids": len(cids),
        "n_rows": total_rows,
        "n_new_rows": total_new_rows,
        "n_changed_rows": total_changed_rows,
        "n_skipped_unchanged_rows": total_skipped_unchanged_rows,
        "n_cids_with_trials": total_with_trials,
        "n_error_rows": total_with_errors,
        "n_shards": 1,
        "n_cids_processed": len(cids),
        "n_rows_scanned": total_new_rows + total_changed_rows + total_skipped_unchanged_rows,
        "n_delta_rows": total_new_rows + total_changed_rows,
        "incremental_from": args.incremental_from,
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
        "json": str(json_path),
        "csv_rows": csv_rows,
        "json_rows": json_rows,
        "n_compounds": len(compounds_rows),
        "compounds_json": str(compounds_json_path),
        "compounds_csv": str(compounds_csv_path),
        "compounds_json_rows": compounds_json_rows,
        "compounds_csv_rows": compounds_csv_rows,
        "trials_compact_json": str(trials_compact_json_path),
        "trials_compact_csv": str(trials_compact_csv_path),
        "trials_compact_json_rows": compact_json_rows,
        "trials_compact_csv_rows": compact_csv_rows,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"cids: {len(cids)}")
    print(f"rows: {total_rows}")
    print(f"jsonl: {jsonl_path}")
    print(f"csv: {csv_path}")
    print(f"json: {json_path}")
    print(f"compounds_json: {compounds_json_path}")
    print(f"compounds_csv: {compounds_csv_path}")
    print(f"trials_compact_json: {trials_compact_json_path}")
    print(f"trials_compact_csv: {trials_compact_csv_path}")
    print(f"summary: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
