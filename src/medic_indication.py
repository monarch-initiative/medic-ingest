"""MeDIC drug-to-disease indications, with normalized nodes.

Edges are emitted one per (drug, disease) pair (see scripts/build_agency_indications.py),
carrying agency provenance, verbatim indication text, and EMA source URLs.

Node identifiers are normalized:
- **Diseases** strictly via the authoritative MONDO SSSOM exact-match mappings
  (data/mondo.sssom.tsv) -> MONDO, with the MONDO label. No other service is allowed to change a
  disease id: HP phenotypes and diseases with no MONDO exact match keep their id and MeDIC's label.
- **Drugs** via the SRI Node Normalizer (canonical id, label, most-specific Biolink category,
  equivalent identifiers).

When an identifier is changed by normalization, the pre-normalization id is preserved on the edge
as ``original_subject`` / ``original_object`` (standard KGX practice). Lookups are built once in
``on_data_begin`` (SSSOM load + a batched Node Normalizer call over the input's unique CURIEs).
"""

from __future__ import annotations

import csv
import json
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import biolink_model.datamodel.pydanticmodel_v2 as biolink
import koza
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    KnowledgeLevelEnum,
    NamedThing,
    ResourceRoleEnum,
    RetrievalSource,
)
from koza import KozaTransform
from koza.model.graphs import KnowledgeGraph

INFORES_MEDIC = "infores:medic"
MEDIC_PUBLICATION = "PMID:41385096"

AGENCY_INFORES = {
    "FDA": "infores:dailymed",
    "EMA": "infores:ema",
    "PMDA": "infores:pmda",
}

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SSSOM_FILE = DATA_DIR / "mondo.sssom.tsv"
INPUT_FILE = DATA_DIR / "indications_by_agency.jsonl"

NODENORM_URL = "https://nodenormalization-sri.renci.org/get_normalized_nodes"
NODENORM_CHUNK = 1000

# Populated once in on_data_begin.
_MONDO_MAP: dict[str, tuple[str, str]] = {}  # external disease CURIE -> (MONDO id, MONDO label)
_NORM: dict[str, dict[str, Any]] = {}  # CURIE -> {id, name, category, equivalent_identifiers}


class Resolved:
    """A normalized endpoint: its canonical node, plus the original id if it was changed."""

    def __init__(
        self,
        id: str,
        name: str | None,
        category: str,  # biolink CURIE, e.g. "biolink:Disease"
        equivalent_identifiers: list[str] | None = None,
        original_id: str | None = None,
    ):
        self.id = id
        self.name = name
        self.category = category
        self.equivalent_identifiers = equivalent_identifiers or []
        self.original_id = original_id


# --- lookup construction (on_data_begin) ---------------------------------------------------------


def _load_mondo_sssom(path: Path) -> dict[str, tuple[str, str]]:
    """Map external disease CURIE -> (MONDO id, MONDO label) from SSSOM exact matches."""
    mapping: dict[str, tuple[str, str]] = {}
    with open(path) as f:
        rows = csv.DictReader((line for line in f if not line.startswith("#")), delimiter="\t")
        for row in rows:
            if row.get("predicate_id") != "skos:exactMatch":
                continue
            obj = row.get("object_id")
            subj = row.get("subject_id")
            if obj and subj and obj not in mapping:  # first exact match wins
                mapping[obj] = (subj, row.get("subject_label") or "")
    return mapping


def _scan_curies(path: Path) -> tuple[set[str], set[str]]:
    """Collect unique drug and disease CURIEs from the combined input."""
    drugs: set[str] = set()
    diseases: set[str] = set()
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            drugs.add(rec["drug_id"])
            diseases.add(rec["disease_id"])
    return drugs, diseases


def _nodenorm_batch(curies: list[str]) -> dict[str, dict[str, Any]]:
    """Resolve CURIEs via the SRI Node Normalizer, in chunks."""
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(curies), NODENORM_CHUNK):
        chunk = curies[start : start + NODENORM_CHUNK]
        payload = json.dumps({"curies": chunk, "conflate": True}).encode()
        req = urllib.request.Request(NODENORM_URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        for curie, value in data.items():
            if not value:
                continue
            node_id = value["id"]
            types = value.get("type") or ["biolink:NamedThing"]
            out[curie] = {
                "id": node_id["identifier"],
                "name": node_id.get("label"),
                "category": types[0],
                "equivalent_identifiers": [e["identifier"] for e in value.get("equivalent_identifiers", [])],
            }
    return out


@koza.on_data_begin()
def load_lookups(koza_transform: KozaTransform) -> None:
    _MONDO_MAP.clear()
    _MONDO_MAP.update(_load_mondo_sssom(SSSOM_FILE))

    # Diseases are normalized strictly via MONDO SSSOM (below); only drugs go to NodeNorm.
    drugs, _diseases = _scan_curies(INPUT_FILE)
    _NORM.clear()
    _NORM.update(_nodenorm_batch(sorted(drugs)))

    koza_transform.log(
        f"MONDO SSSOM exact matches: {len(_MONDO_MAP)}; NodeNorm resolved {len(_NORM)}/{len(drugs)} drug CURIEs"
    )


# --- resolution + node building ------------------------------------------------------------------


def resolve_disease(curie: str, fallback_label: str | None, mondo_map: dict[str, tuple[str, str]]) -> Resolved:
    """Diseases are normalized strictly via MONDO SSSOM exact match.

    Without a MONDO exact match the id is left unchanged (we do not let any other service
    normalize disease ids) and labeled from MeDIC's own label; HP ids are phenotypic features.
    """
    mapped = mondo_map.get(curie)
    if mapped:
        mondo_id, label = mapped
        return Resolved(
            id=mondo_id,
            name=label or None,
            category="biolink:Disease",
            original_id=curie if mondo_id != curie else None,
        )
    category = "biolink:PhenotypicFeature" if curie.startswith("HP:") else "biolink:Disease"
    return Resolved(id=curie, name=fallback_label or None, category=category)


def resolve_drug(curie: str, fallback_label: str | None, norm: dict[str, dict[str, Any]]) -> Resolved:
    """Drugs normalize via NodeNorm (we trust it as the chemical authority)."""
    info = norm.get(curie)
    if info:
        return Resolved(
            id=info["id"],
            name=info.get("name"),
            category=info["category"],
            equivalent_identifiers=info.get("equivalent_identifiers", []),
            original_id=curie if info["id"] != curie else None,
        )
    return Resolved(id=curie, name=fallback_label or None, category="biolink:ChemicalEntity")


def _node_class(category: str) -> tuple[type, str]:
    """Resolve a Biolink category CURIE to its pydantic class.

    Falls back to NamedThing (with a NamedThing category, since each class pins its category
    via a Literal) when the category names no NamedThing subclass.
    """
    cls = getattr(biolink, category.removeprefix("biolink:"), None)
    if isinstance(cls, type) and issubclass(cls, NamedThing):
        return cls, category
    return NamedThing, "biolink:NamedThing"


def _node(resolved: Resolved) -> NamedThing:
    cls, category = _node_class(resolved.category)
    return cls(
        id=resolved.id,
        name=resolved.name or None,
        category=[category],
        equivalent_identifiers=resolved.equivalent_identifiers or None,
        provided_by=[INFORES_MEDIC],
    )


@koza.transform_record()
def transform_record(koza_transform: KozaTransform, record: dict[str, Any]) -> KnowledgeGraph:
    """Transform one normalized MeDIC drug-disease pair into a Biolink treats edge + nodes."""
    agencies = record["agencies"]

    sources = [
        RetrievalSource(
            id=f"uuid:{uuid.uuid4()}",
            resource_id=INFORES_MEDIC,
            resource_role=ResourceRoleEnum.primary_knowledge_source,
            upstream_resource_ids=[a["infores"] for a in agencies],
        )
    ]
    for a in agencies:
        url = a.get("source_url") or ""
        sources.append(
            RetrievalSource(
                id=f"uuid:{uuid.uuid4()}",
                resource_id=a["infores"],
                resource_role=ResourceRoleEnum.supporting_data_source,
                source_record_urls=[url] if url else None,
            )
        )

    supporting_text = [f"[{a['agency']}] {a['indication_text']}" for a in agencies if a.get("indication_text")] or None

    drug = resolve_drug(record["drug_id"], record.get("drug_label"), _NORM)
    disease = resolve_disease(record["disease_id"], record.get("disease_label"), _MONDO_MAP)

    association = ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation(
        id=f"uuid:{uuid.uuid4()}",
        subject=drug.id,
        original_subject=drug.original_id,
        predicate="biolink:treats",
        object=disease.id,
        original_object=disease.original_id,
        knowledge_level=KnowledgeLevelEnum.knowledge_assertion,
        agent_type=AgentTypeEnum.text_mining_agent,
        primary_knowledge_source=INFORES_MEDIC,
        sources=sources,
        supporting_text=supporting_text,
        publications=[MEDIC_PUBLICATION],
    )

    return KnowledgeGraph(nodes=[_node(drug), _node(disease)], edges=[association])
