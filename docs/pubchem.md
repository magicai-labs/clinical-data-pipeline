# PubChem Clients

Module: src/clinpipe/pubchem/

This package wraps PubChem REST APIs for:

- core compound lookup
- classification nodes (HNID)
- PUG-View annotations for clinical trials
- web fallback lookups for cases where REST payloads miss NCT IDs

## PubChemClient

Module: src/clinpipe/pubchem/client.py

Methods:

- cids_by_name(name) -> List[int]
- compound_properties(cid) -> Dict
  - CanonicalSMILES
  - InChIKey
  - IUPACName
- synonyms(cid, max_items=50) -> List[str]

## PubChemClassificationClient

Module: src/clinpipe/pubchem/classification_nodes.py

Methods:

- get_ids(hnid, id_type="cids", fmt="TXT") -> List[int]
- get_cids(hnid, fmt="TXT") -> List[int]

HNID helpers:

Module: src/clinpipe/pubchem/clinical_trials_nodes.py

- download_clinical_trials_cids(out_dir="out_hnid", include_sources=True)
  - returns dict with keys: clinical_trials, clinicaltrials_gov, eu_register, japan_niph

## PubChemPugViewClient

Module: src/clinpipe/pubchem/pug_view.py

Methods:

- get_compound_record(cid) -> JSON
- nct_ids_for_cid(cid) -> List[str]

This extracts NCT IDs from PUG-View JSON payloads using URL and text scanning.

Fallback behavior (when PUG-View default payload is empty):

1. heading-based PUG-View lookup (including clinical trials / drug and medication sections)
2. PubChem web clinicaltrials endpoint fallback (`/sdq/sphinxql.cgi`)
3. PubChem compound HTML fallback

You can also retrieve the source path:

- nct_ids_for_cid_with_source(cid) -> (List[str], str)

## PubChemWebFallbackClient

Module: src/clinpipe/pubchem/web_fallback/

Methods:

- get_sdq_payload(cid, collection="clinicaltrials", limit=200, order=None) -> Dict
- get_clinicaltrials_sdq_payload(cid) -> Dict
- get_eu_register_sdq_payload(cid) -> Dict
- get_japan_niph_sdq_payload(cid) -> Dict
- get_normalized_trials(cid, collection="clinicaltrials", limit=200) -> List[Dict]
- get_normalized_trials_union(cid, collections=(...), limit_per_collection=200) -> (List[Dict], List[str])
- get_compound_page_html(cid) -> str
- nct_ids_for_cid_with_source(cid) -> (List[str], str)
- nct_ids_for_cid(cid) -> List[str]

This is intended as a fallback layer when REST responses are incomplete for a CID.

## Workflow run metrics

The full and incremental collection workflows write `run_metrics.json` for every run, including unchanged and failed runs. Metrics are kept out of `main` so operational observations do not create snapshot commits or inflate the source/data history. The `metrics` branch contains only a short README and one immutable file per run at `runs/YYYY/MM/{mode}_{run_id}_{run_attempt}.json`.

Each file records workflow identity and timing, dispatch parameters, shard/CID counts, scanned/new/changed/unchanged/error row counts, baseline and result checksums, final file size and row count, dataset/history change indicators, pruning information, changed assets, and warnings. Unknown values are `null`, not zero. The same file is available from the workflow run's Artifacts section for 90 days as `run-metrics-{mode}-{run_id}-{run_attempt}`.

Unchanged runs are still written to the metrics branch, while `main` snapshot data remains commit-on-change. For reproducible paper analysis, fix and report the observation window's start and end dates before aggregating these files.

## Snapshot sharding

Repository snapshots use 32 deterministic shards per asset, assigned by `cid % 32`. Latest shards are ordinary JSON arrays so Pages and other static clients can read them directly. Timestamped history shards are gzip-compressed. Every asset directory contains a manifest with row counts, file sizes, SHA-256 checksums, source checksum, shard strategy, and generation time.

During migration, monolithic files under `snapshots/clinical_trials/latest/*.json` remain available to the incremental collector. Pages prefers the shard manifest and exposes uncompressed shard directories. Use `scripts/snapshot_shards.py materialize` for consumers that require one JSON array.

Normalized trial rows use a common schema across collections:
- collection (human-readable source name)
- collection_code (raw SDQ collection code)
- id (ctid or eudractnumber)
- date (date or updatedate normalized to date)
- title
- phase
- status
- id_url (trial hyperlink from source)
- cids

Union schema mode:
- Merges rows from ctgov/eu/jp collections
- Keeps common keys and collection-specific keys together
- Aligns rows so all keys exist (missing values are None)

## Examples

Resolve CID and synonyms:

```python
from clinpipe.pubchem import PubChemClient

pub = PubChemClient()
cids = pub.cids_by_name("aspirin")
props = pub.compound_properties(cids[0])
syms = pub.synonyms(cids[0], max_items=20)
```

Get NCT IDs via PUG-View:

```python
from clinpipe.pubchem import PubChemPugViewClient

pv = PubChemPugViewClient()
print(pv.nct_ids_for_cid(2244))
```
