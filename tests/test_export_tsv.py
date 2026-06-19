"""TSV export serialization rules, per the KGX TSV spec.

https://github.com/biolink/kgx/blob/master/docs/kgx_format.md

Two deliberate decisions are asserted here:

1. Multivalued *scalar* columns serialize as pipe-delimited values with NO
   wrapping brackets and NO quotes -- the KGX convention.
2. *Nested* columns (`sources`, a list of RetrievalSource structs) have no KGX
   TSV standard, so we serialize them as JSON (valid, parseable, lossless).
   This is a deliberate non-standard extension.
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from export_tsv import _export


def _edge_record():
    return {
        "id": "uuid:1",
        "subject": "CHEBI:1",
        "predicate": "biolink:treats",
        "object": "MONDO:1",
        "category": ["biolink:ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation"],
        "primary_knowledge_source": "infores:medic",
        "publications": ["PMID:41385096", "PMID:99999999"],
        "supporting_text": ["[FDA] indicated for ...", "[EMA] indicated ..."],
        "sources": [
            {
                "resource_id": "infores:medic",
                "resource_role": "primary_knowledge_source",
                "upstream_resource_ids": ["infores:dailymed"],
            },
            {"resource_id": "infores:dailymed", "resource_role": "supporting_data_source"},
        ],
    }


def _export_one(tmp_path: Path, record: dict) -> dict:
    jsonl = tmp_path / "edges.jsonl"
    jsonl.write_text(json.dumps(record) + "\n")
    tsv = tmp_path / "edges.tsv"
    count = _export(jsonl, tsv)
    assert count == 1
    with open(tsv) as f:
        return next(csv.DictReader(f, delimiter="\t"))


def test_scalar_columns_unchanged(tmp_path: Path):
    row = _export_one(tmp_path, _edge_record())
    assert row["subject"] == "CHEBI:1"
    assert row["predicate"] == "biolink:treats"
    assert row["primary_knowledge_source"] == "infores:medic"


def test_multivalued_scalars_are_pipe_delimited_without_brackets(tmp_path: Path):
    """KGX spec: multivalued fields use pipe (`|`) as delimiter, no brackets/quotes."""
    row = _export_one(tmp_path, _edge_record())

    assert row["publications"] == "PMID:41385096|PMID:99999999"
    assert row["supporting_text"] == "[FDA] indicated for ...|[EMA] indicated ..."
    # single-value list still has no wrapping brackets
    assert row["category"] == "biolink:ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation"

    # none of these are JSON arrays (no `["..."]` wrapping). supporting_text content
    # legitimately starts with `[FDA]`, so check for the JSON-array opener specifically.
    for col in ("publications", "supporting_text", "category"):
        assert not row[col].startswith('["'), f"{col} should not be a JSON array: {row[col]!r}"
        assert not row[col].endswith('"]'), f"{col} should not be a JSON array: {row[col]!r}"


def test_nested_sources_serialized_as_json(tmp_path: Path):
    """Nested struct list has no KGX TSV standard; we emit valid JSON that round-trips."""
    row = _export_one(tmp_path, _edge_record())

    sources = json.loads(row["sources"])  # must be valid JSON
    assert {s["resource_id"] for s in sources} == {"infores:medic", "infores:dailymed"}
    by_role = {s["resource_role"]: s for s in sources}
    assert by_role["primary_knowledge_source"]["upstream_resource_ids"] == ["infores:dailymed"]


def test_node_category_pipe_delimited(tmp_path: Path):
    node = {"id": "HP:1", "name": "Pain", "category": ["biolink:PhenotypicFeature"]}
    jsonl = tmp_path / "nodes.jsonl"
    jsonl.write_text(json.dumps(node) + "\n")
    tsv = tmp_path / "nodes.tsv"
    _export(jsonl, tsv)
    with open(tsv) as f:
        row = next(csv.DictReader(f, delimiter="\t"))
    assert row["category"] == "biolink:PhenotypicFeature"
    assert "[" not in row["category"]
