# medic-ingest justfile

# Package directory
PKG := "src"

# Explicitly enumerate transforms (add new ingests here)
TRANSFORMS := "medic_indication"

# List all commands
_default:
    @just --list

# Initialize a new project
[group('project management')]
setup: _git-init install _git-add
    git commit -m "Initialize medic-ingest"

# Install dependencies
[group('project management')]
install:
    uv sync --group dev

# Download source data (uses scripts/download.py for tar_extract support;
# medic's figshare archive ships as a tarball, which kghub-downloader can't
# unpack on its own), then combine the per-agency sheets into one TSV.
[group('ingest')]
download: install
    uv run python scripts/download.py
    uv run python scripts/build_agency_indications.py

# Run all transforms
[group('ingest')]
transform-all: download
    #!/usr/bin/env bash
    set -euo pipefail
    for t in {{TRANSFORMS}}; do
        if [ -n "$t" ]; then
            echo "Transforming $t..."
            uv run koza transform {{PKG}}/$t.yaml -f jsonl
        fi
    done

# Emit output/release-metadata.yaml describing this build's upstream sources and artifacts
[group('ingest')]
metadata:
    uv run python scripts/write_metadata.py

# Export a KGX TSV copy of the JSONL output (nested columns as JSON); see scripts/export_tsv.py
[group('ingest')]
export-tsv:
    uv run python scripts/export_tsv.py

# Produce an xlsx KGX validation summary via monarch-initiative/kgxval (uvx, Python 3.13)
[group('ingest')]
kgxval-summary:
    #!/usr/bin/env bash
    set -euo pipefail
    # kgxval needs Python 3.13 + bmt-from-git, so it runs via uvx, isolated from this
    # project's 3.12 env. It reads the JSONL output directly. The source is staged under
    # the short name `medic` because kgxval derives Excel sheet names from it and Excel
    # caps sheet names at 31 chars. The rollup-sampling pass is slow (~5-10 min).
    workdir="$(mktemp -d)"
    mkdir -p "$workdir/medic"
    cp output/medic_indication_nodes.jsonl output/medic_indication_edges.jsonl "$workdir/medic/"
    ( cd "$workdir" && uvx --python 3.13 --from 'git+https://github.com/monarch-initiative/kgxval' \
        many_sources "$workdir" )
    xlsx="$(find "$workdir/data/output" -name '*.xlsx' | head -1)"
    cp "$xlsx" output/medic_kgxval_summary.xlsx
    echo "Wrote output/medic_kgxval_summary.xlsx"

# Run full pipeline: install, download, transform, metadata, test
[group('ingest')]
run: test transform-all metadata

# Run specific transform
[group('ingest')]
transform NAME:
    uv run koza transform {{PKG}}/{{NAME}}.yaml -f jsonl

# Run tests
[group('development')]
test: install
    uv run pytest

# Run tests with coverage
[group('development')]
test-cov: install
    uv run pytest --cov=. --cov-report=term-missing

# Lint code
[group('development')]
lint:
    uv run ruff check .

# Format code
[group('development')]
format:
    uv run ruff format .

# Clean output directory
[group('ingest')]
clean:
    rm -rf output/

# Hidden recipes
_git-init:
    git init

_git-add:
    git add .
