#!/usr/bin/env python3
"""Export the JSONL transform output to KGX TSV alongside it.

The canonical output of this ingest is JSONL (it carries nested provenance --
`sources` is a list of Biolink RetrievalSource objects -- which TSV has no
native convention for). This produces a TSV *copy* for consumers that want it.

Koza's graph-ops verbs don't (yet) do a faithful single-file format conversion:
`split` fragments by a field and `join` only builds a DuckDB. So we do here what
a future koza `export`/`convert` verb would do internally -- load the JSONL into
DuckDB and COPY it out -- serializing multivalued/nested columns as JSON so they
round-trip losslessly (DuckDB's default struct-repr is not valid JSON/KGX).
"""

from __future__ import annotations

from pathlib import Path

import duckdb

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

# Columns holding lists or nested objects -> emit as JSON text rather than
# DuckDB's struct/list repr (e.g. `sources` = list[RetrievalSource]).
JSON_COLUMNS = {"sources", "supporting_text", "publications", "category", "equivalent_identifiers", "xref", "synonym"}


def _export(jsonl_path: Path, tsv_path: Path) -> int:
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE t AS SELECT * FROM read_json_auto('{jsonl_path}')")
        columns = [row[0] for row in con.execute("DESCRIBE t").fetchall()]
        select = ", ".join(f"to_json({c}) AS {c}" if c in JSON_COLUMNS else c for c in columns)
        con.execute(f"COPY (SELECT {select} FROM t) TO '{tsv_path}' (HEADER, DELIMITER '\t')")
        return con.execute("SELECT count(*) FROM t").fetchone()[0]
    finally:
        con.close()


def main() -> None:
    for kind in ("nodes", "edges"):
        jsonl_path = OUTPUT_DIR / f"medic_indication_{kind}.jsonl"
        if not jsonl_path.exists():
            raise FileNotFoundError(f"{jsonl_path} not found; run `just transform-all` first.")
        tsv_path = OUTPUT_DIR / f"medic_indication_{kind}.tsv"
        count = _export(jsonl_path, tsv_path)
        print(f"Exported {count} {kind} -> {tsv_path}")


if __name__ == "__main__":
    main()
