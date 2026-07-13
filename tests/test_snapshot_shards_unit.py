import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from snapshot_shards import materialize, write_shards


def test_snapshot_shards_are_deterministic_and_materialize(tmp_path: Path):
    source = tmp_path / "source.json"
    rows = [{"cid": 33, "id": "b"}, {"cid": 1, "id": "a"}, {"cid": 2, "id": "c"}]
    source.write_text(json.dumps(rows), encoding="utf-8")
    output = tmp_path / "latest" / "trials"

    manifest = write_shards(source, output, asset="trials", generated_at="2026-01-01T00:00:00Z", shard_count=4)

    assert manifest["row_count"] == 3
    assert json.loads((output / "shard-001.json").read_text()) == rows[:2]
    combined = tmp_path / "combined.json"
    assert materialize(output / "manifest.json", combined) == 3
    assert sorted(json.loads(combined.read_text()), key=lambda row: row["id"]) == sorted(rows, key=lambda row: row["id"])


def test_compressed_history_shards(tmp_path: Path):
    source = tmp_path / "source.json"
    source.write_text('[{"cid":5}]\n', encoding="utf-8")
    output = tmp_path / "history" / "stamp" / "trials"
    manifest = write_shards(source, output, asset="trials", generated_at="stamp", shard_count=2, compress=True)

    assert manifest["compression"] == "gzip"
    with gzip.open(output / "shard-001.json.gz", "rt", encoding="utf-8") as stream:
        assert json.load(stream) == [{"cid": 5}]
