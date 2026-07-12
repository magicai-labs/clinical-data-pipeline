# Changelog

All notable changes to this project are documented in this file.

## Unreleased

## v0.6.3 - 2026-07-12

### Changed

- Updated Young-Mook Kang's contributor affiliation in the English and Korean READMEs to include both the Korea Research Institute of Chemical Technology (KRICT) and the National AI for Science Research Center (NAIS).

## v0.6.2 - 2026-07-12

### Changed

- Added the README as the PyPI project description with Markdown rendering metadata.
- Added PyPI project links for the repository, documentation, issues, and changelog.
- Added package classifiers, research-oriented keywords, and explicit MIT license metadata.
- Added PyPI, Python, CI, and license badges plus direct project links to the README.
- Clarified that the package supports research data collection and does not provide medical advice.

## v0.6.0 - 2026-02-23

### Changed

- Updated CLI documentation to recommend `clinpipe` as the primary command:
  - `docs/cli.md`
  - `docs/cli.ko.md`
- Added `pip` and `uv` install examples for `clinpipe` in CLI docs.
- Updated README Quickstart install commands to use PyPI package install (`clinpipe`) for end users.
- Updated README/README.ko smoke quickstart commands to use `clinpipe collect-ctgov` (user-facing path).

### Added

- Added import-compatible alias package `clinpipe`:
  - `src/clinpipe/__init__.py`
  - `src/clinpipe/cli.py`
  - `src/clinpipe/ctgov/__init__.py`
  - `src/clinpipe/ctgov/client.py`
  - `src/clinpipe/pubchem/__init__.py`
  - `src/clinpipe/pubchem/client.py`
  - `src/clinpipe/pubchem/classification_nodes.py`
  - `src/clinpipe/pubchem/clinical_trials_nodes.py`
  - `src/clinpipe/pubchem/pug_view.py`
  - `src/clinpipe/pubchem/web_fallback/__init__.py`
  - `src/clinpipe/pipeline/__init__.py`
  - `src/clinpipe/pipeline/build_dataset.py`
  - `src/clinpipe/pipeline/linker.py`
  - `src/clinpipe/pipeline/collect_ctgov_docs_service.py`
  - `src/clinpipe/pipeline/cid_to_nct.py`
- Added unit test for alias package imports:
  - `tests/test_clinpipe_alias_import_unit.py`
- Updated package entrypoint:
  - `clinpipe = \"clinpipe.cli:main\"`

## v0.5.2 - 2026-02-23

### Changed

- Updated `.github/workflows/publish_pypi.yml`:
  - added `twine upload --verbose` for better diagnostics
  - added explicit failure hints for token/scope issues and "file already exists" reuse errors
- Updated README/README.ko with correct TestPyPI install command using:
  - `--index-url https://test.pypi.org/simple/`
  - `--extra-index-url https://pypi.org/simple`

## v0.5.1 - 2026-02-23

### Changed

- Renamed package distribution to `clinpipe` in `pyproject.toml`.
- Added dual CLI entry points:
  - `clinpipe` (primary)
  - `clinical-data-analyzer` (legacy alias)
- Updated CLI program name/help references to prefer `clinpipe`.
- Added runtime notice for legacy alias usage:
  - can be suppressed with `CLINPIPE_HIDE_LEGACY_NOTICE=1`
- Updated README/README.ko examples to use `clinpipe`.

## v0.5.0 - 2026-02-23

### Added

- Added CID shard options to PubChem trials exporter:
  - `--cid-offset`
  - `--cid-count`
- Added shard merge script:
  - `scripts/merge_pubchem_trials_shards.py`
  - merges `trials.jsonl/json` across shard output dirs into one dataset
- Added unit test for shard merge behavior:
  - `tests/test_merge_pubchem_trials_shards_unit.py`
- Added unit test for shard option behavior in export script:
  - `tests/test_export_pubchem_trials_dataset_unit.py::test_export_pubchem_trials_dataset_shard_options_unit`

### Changed

- Updated `.github/workflows/clinical_compound_table_pages.yml` to support shard collection mode:
  - new input `shard_size` (default `500`, `0` disables shard mode)
  - collects shard outputs and merges them via `scripts/merge_pubchem_trials_shards.py`

## v0.4.0 - 2026-02-23

### Added

- Added PubChem trials snapshot updater:
  - `scripts/update_pubchem_trials_history.py`
  - persists:
    - `snapshots/clinical_trials/latest/trials.json`
    - `snapshots/clinical_trials/history/trials_*.json`
    - `snapshots/clinical_trials/collection_state.json`
- Added unit tests for PubChem snapshot update behavior:
  - `tests/test_update_pubchem_trials_history_unit.py`

### Changed

- Updated `.github/workflows/clinical_compound_table_pages.yml`:
  - added daily schedule trigger
  - added snapshot update + commit/push step for `trials.json` history under `snapshots/clinical_trials`
  - added history retention option (`retention_days`, default 365)
  - changed `contents` permission to `write` for automated snapshot commits

## v0.3.1 - 2026-02-10

### Added

- Added filtered export controls for PubChem trials table UIs:
  - DataTables mode: `Export CSV`, `Export JSON`
  - Tabulator mode: `Export CSV`, `Export JSON`
- Added unit test for PubChem table HTML builder:
  - `tests/test_build_pubchem_trials_table_unit.py`

### Changed

- Updated download filenames for filtered exports to:
  - `clinical_trials_list_filtered.csv`
  - `clinical_trials_list_filtered.json`

## v0.3.0 - 2026-02-10

### Added

- Added scheduled GitHub Actions workflow for CTGov collection and table publishing:
  - `.github/workflows/ctgov_collect.yml`
- Added dedicated GitHub Pages workflow for PubChem trials table publishing:
  - `.github/workflows/clinical_compound_table_pages.yml`
- Added static table builder:
  - `scripts/build_studies_table.py` (CSV -> `docs/data/{studies.csv,studies.json,index.html}`)
- Added studies history updater:
  - `scripts/update_studies_history.py`
  - persists latest studies snapshot and change history in:
    - `data/ctgov/studies.jsonl`
    - `data/ctgov/history/studies_*.jsonl`
    - `data/ctgov/collection_state.json`
- Added dual study links in normalized/table outputs:
  - `ctgov_url` and `pubchem_url` in clinical compound trial dataset
  - static table now shows both CTGov and PubChem links
- Added PubChem trials export pipeline:
  - `scripts/export_pubchem_trials_dataset.py`
  - exports normalized union rows across ctgov/eu/jp collections (`trials.jsonl`, `trials.csv`, `trials.json`, `summary.json`)
- Added PubChem trials HTML builders:
  - `scripts/build_pubchem_trials_table.py`
  - supports `vanilla`, `datatables`, and `tabulator` modes

### Changed

- Refactored PubChem web fallback modules from a single file to provider-based package layout.
- Normalized PubChem trial row schema now uses unified fields:
  - `collection`, `collection_code`, `id`, `date`, `id_url`, `title`, `phase`, `status`, `cids`
- PubChem trial export now stores structure images as base64 data URIs in output rows.
- Added fallback to `ConnectivitySMILES` when `CanonicalSMILES` is missing in compound properties.
- Updated `ctgov_collect` workflow to focus on scheduled collection/snapshot updates, while Pages deployment is handled by `pubchem_table_pages`.

### Tests

- Added unit test for studies history update behavior:
  - `tests/test_update_studies_history_unit.py`
- Added unit test for static studies table builder:
  - `tests/test_build_studies_table_unit.py`
- Added unit test for PubChem trials export script:
  - `tests/test_export_pubchem_trials_dataset_unit.py`

## v0.2.0 - 2026-02-09

### Added (Service Refactor)

- Added service-oriented CTGov collection module:
  - `src/clinical_data_analyzer/pipeline/collect_ctgov_docs_service.py`
  - `CollectCtgovDocsConfig`
  - `CollectCtgovDocsResult`
  - `collect_ctgov_docs(...)`
- Added thin script wrappers:
  - `scripts/collect_ctgov_docs.py` (main step1-3 runner, also supports quick smoke via limits)

### Changed (Collection Flow)

- Refactored step1-3 collection to **streaming mode**:
  - process one CID at a time
  - map NCT IDs for that CID
  - fetch CTGov study docs immediately (instead of waiting for all CID mapping to finish)
- Updated collected `studies.jsonl` rows to include top-level `cid` for easier downstream joins.
- Improved user-facing progress logs and startup context messages.
- Improved failure messaging in script layer with human-readable reason + raw error.

### Added

- Added staged MVP scripts under `scripts/`:
  - `fetch_cids.py`
  - `map_cid_to_nct.py`
  - `fetch_ctgov_docs.py`
  - `build_clinical_dataset.py`
  - `run_mvp_pipeline.py`
  - shared utilities in `mvp_pipeline_lib.py`
- Added PubChem web fallback client:
  - `src/clinical_data_analyzer/pubchem/web_fallback.py`
  - supports PubChem web clinical trials endpoint (`/sdq/sphinxql.cgi`) and HTML fallback.
- Added CID-level error capture in `cid_nct_links.jsonl` and `compounds.jsonl` when API calls fail.

### Changed

- Improved CID -> NCT resolution priority:
  1. PubChem PUG-View default payload
  2. PUG-View heading lookup (including Drug and Medication Information section)
  3. PubChem web clinical trials endpoint fallback (`sdq/sphinxql.cgi`)
  4. PubChem compound page HTML fallback
  5. CT.gov term-link fallback (optional)
- Updated `scripts/map_cid_to_nct.py` and `scripts/run_mvp_pipeline.py`:
  - `--use-ctgov-fallback` option supported.
- Updated `src/clinical_data_analyzer/pipeline/cid_to_nct.py`:
  - source tracking for fallback path
  - non-fail-fast behavior with per-CID error recording.

### Removed

- Removed one-off demo wrapper `scripts/collect_ctgov_docs_first1.py`.
- Standardized smoke test path to `scripts/collect_ctgov_docs.py --limit-cids 1 --limit-ncts 1`.

### Documentation

- Updated usage and behavior docs for fallback strategy, streaming collection flow, and service-oriented structure.

### Tests

- Added and expanded tests for:
  - PUG-View heading fallback behavior
  - web fallback (`sdq` first, HTML second)
  - CT.gov fallback behavior
  - non-fail-fast error handling for CID mapping pipeline.
