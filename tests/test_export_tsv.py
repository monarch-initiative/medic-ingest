import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from export_tsv import _export


def test_export_serializes_nested_columns_as_json(tmp_path: Path):
    edge = {
        "id": "uuid:1",
        "subject": "CHEBI:1",
        "predicate": "biolink:treats",
        "object": "MONDO:1",
        "category": ["biolink:ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation"],
        "primary_knowledge_source": "infores:medic",
        "publications": ["PMID:41385096"],
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
    jsonl = tmp_path / "edges.jsonl"
    jsonl.write_text(json.dumps(edge) + "\n")
    tsv = tmp_path / "edges.tsv"

    count = _export(jsonl, tsv)
    assert count == 1

    import csv

    with open(tsv) as f:
        row = next(csv.DictReader(f, delimiter="\t"))

    # scalar columns stay scalar
    assert row["subject"] == "CHEBI:1"
    assert row["predicate"] == "biolink:treats"

    # nested/multivalued columns are valid JSON that round-trips
    sources = json.loads(row["sources"])
    assert {s["resource_id"] for s in sources} == {"infores:medic", "infores:dailymed"}
    assert sources[0]["resource_role"] == "primary_knowledge_source"
    assert json.loads(row["supporting_text"]) == edge["supporting_text"]
    assert json.loads(row["publications"]) == ["PMID:41385096"]
