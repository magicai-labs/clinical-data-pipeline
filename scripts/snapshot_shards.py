#!/usr/bin/env python3
"""Write and materialize deterministic, manifest-described JSON snapshot shards."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable


def _row_shard(row: Any, count: int) -> int:
    if isinstance(row, dict) and isinstance(row.get("cid"), int):
        return row["cid"] % count
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big") % count


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_shards(
    source: Path,
    output_dir: Path,
    *,
    asset: str,
    generated_at: str,
    shard_count: int = 32,
    compress: bool = False,
) -> dict[str, Any]:
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        rows = [rows]
    buckets: list[list[Any]] = [[] for _ in range(shard_count)]
    for row in rows:
        buckets[_row_shard(row, shard_count)].append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".json.gz" if compress else ".json"
    files = []
    for index, bucket in enumerate(buckets):
        path = output_dir / f"shard-{index:03d}{suffix}"
        payload = json.dumps(bucket, ensure_ascii=False, separators=(",", ":")) + "\n"
        if compress:
            with path.open("wb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as zipped:
                    with io.TextIOWrapper(zipped, encoding="utf-8") as stream:
                        stream.write(payload)
        else:
            path.write_text(payload, encoding="utf-8")
        files.append({
            "index": index,
            "path": path.name,
            "rows": len(bucket),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })

    manifest = {
        "schema_version": 1,
        "asset": asset,
        "generated_at": generated_at,
        "format": "json-array",
        "compression": "gzip" if compress else None,
        "shard_strategy": "cid_modulo",
        "shard_count": shard_count,
        "row_count": len(rows),
        "source_sha256": _sha256(source),
        "shards": files,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def materialize(manifest_path: Path, output: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    for shard in manifest["shards"]:
        path = manifest_path.parent / shard["path"]
        if manifest.get("compression") == "gzip":
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                part = json.load(stream)
        else:
            part = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(part)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(prog="snapshot-shards")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--asset", required=True)
    create.add_argument("--generated-at", required=True)
    create.add_argument("--shard-count", type=int, default=32)
    create.add_argument("--compress", action="store_true")
    merge = sub.add_parser("materialize")
    merge.add_argument("--manifest", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "create":
        write_shards(args.source, args.output_dir, asset=args.asset, generated_at=args.generated_at,
                     shard_count=args.shard_count, compress=args.compress)
    else:
        materialize(args.manifest, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
