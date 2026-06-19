# Koza Ingest

This is a Koza ingest repository for transforming biological/biomedical data into Biolink model format.

## Project Structure

- `download.yaml` - Configuration for downloading source data
- `src/` - Transform code and configuration
  - `*.py` / `*.yaml` pairs - Transform code and koza config for each ingest
  - `*_mapping.yaml` - Lookup mapping files (if needed)
  - `versions.py` - Per-ingest upstream version fetcher (consumed by `just metadata`)
- `scripts/download.py` - Downloads source data and extracts files from the figshare tarball (driven by `download.yaml`)
- `scripts/build_agency_indications.py` - Groups the extracted per-agency indication sheets into `data/indications_by_agency.jsonl` (run by `just download`)
- `scripts/export_tsv.py` - Exports a KGX TSV copy of the JSONL output via DuckDB (`just export-tsv`)
- `scripts/write_metadata.py` - Emits `output/release-metadata.yaml` from `versions.py`
- `tests/` - Unit tests for transforms
- `output/` - Generated nodes and edges (gitignored)
  - `release-metadata.yaml` - Per-build manifest of upstream sources, versions, artifacts (kozahub-metadata-schema)
- `data/` - Downloaded source data (gitignored)

## Key Commands

- `just download` - Download source data
- `just transform-all` - Run all transforms
- `just transform <name>` - Run specific transform
- `just metadata` - Emit `output/release-metadata.yaml`
- `just export-tsv` - Write a KGX TSV copy of the JSONL output
- `just kgxval-summary` - Produce an xlsx KGX validation summary via monarch-initiative/kgxval (uvx, Python 3.13)
- `just test` - Run tests

## Adding New Ingests

When adding a new ingest:
1. Add download configuration to `download.yaml`
2. Create `src/<ingest_name>.py` with transform code
3. Create `src/<ingest_name>.yaml` with koza configuration
4. Add `<ingest_name>` to TRANSFORMS list in justfile
5. Create tests in `tests/test_<ingest_name>.py`
6. Update `src/versions.py` to declare the upstream source(s) and how to fetch their version

## Release Metadata

Every kozahub ingest emits an `output/release-metadata.yaml` describing the upstream sources, their versions, the artifacts produced, and the versions of build-time tools. This file is the contract monarch-ingest reads to assemble the merged knowledge graph's release receipt.

`src/versions.py` is the only per-ingest piece — it implements `get_source_versions()` returning a list of SourceVersion dicts. The `kozahub_metadata_schema` package provides reusable fetchers for the common patterns (HTTP Last-Modified, GitHub releases, URL-path regex, file-header parsing). The boilerplate (transform-content hashing, tool versions, build_version composition, yaml emission) is handled by `scripts/write_metadata.py`.

The `kozahub-metadata-schema` repo is expected as a sibling checkout (path-dep). Switch to a git or PyPI dep once published.

## Skills

- `.claude/skills/create-koza-ingest.md` - Create new koza ingests
- `.claude/skills/update-template.md` - Update to latest template version
