import sys

import pytest
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    KnowledgeLevelEnum,
    NamedThing,
    ResourceRoleEnum,
    SmallMolecule,
)

sys.path.insert(0, "src")
import medic_indication as mi
from medic_indication import resolve_disease, resolve_drug, transform_record

# --- disease normalization (strictly MONDO SSSOM) ------------------------------------------------


def test_disease_remapped_to_mondo_with_original_preserved():
    r = resolve_disease("UMLS:C1", "heart failure", {"UMLS:C1": ("MONDO:9", "congestive heart failure")})
    assert r.id == "MONDO:9"
    assert r.name == "congestive heart failure"
    assert r.category == "biolink:Disease"
    assert r.original_id == "UMLS:C1"


def test_disease_already_mondo_is_unchanged():
    r = resolve_disease("MONDO:9", "x", {})
    assert r.id == "MONDO:9"
    assert r.original_id is None


def test_disease_without_mondo_match_keeps_id_and_medic_label():
    """Strictly MONDO SSSOM: no exact match means the id is left alone (no other normalizer)."""
    r = resolve_disease("UMLS:C2", "some disease", {})
    assert r.id == "UMLS:C2"
    assert r.name == "some disease"
    assert r.category == "biolink:Disease"
    assert r.original_id is None


def test_hp_without_mondo_match_is_phenotypic_feature():
    r = resolve_disease("HP:0012531", "Pain", {})
    assert r.category == "biolink:PhenotypicFeature"
    assert r.id == "HP:0012531"


# --- drug normalization (NodeNorm) ---------------------------------------------------------------


def test_drug_resolved_via_nodenorm_with_category_and_equivalents():
    norm = {
        "CHEBI:1": {
            "id": "CHEBI:1",
            "name": "Polythiazide",
            "category": "biolink:SmallMolecule",
            "equivalent_identifiers": ["UNII:9", "PUBCHEM.COMPOUND:5"],
        }
    }
    r = resolve_drug("CHEBI:1", "polythiazide", norm)
    assert r.id == "CHEBI:1"
    assert r.name == "Polythiazide"
    assert r.category == "biolink:SmallMolecule"
    assert r.equivalent_identifiers == ["UNII:9", "PUBCHEM.COMPOUND:5"]
    assert r.original_id is None


def test_drug_remapped_to_preferred_id_preserves_original():
    norm = {"RXCUI:5": {"id": "CHEBI:9", "name": "Y", "category": "biolink:Drug", "equivalent_identifiers": []}}
    r = resolve_drug("RXCUI:5", "y", norm)
    assert r.id == "CHEBI:9"
    assert r.original_id == "RXCUI:5"


def test_unresolved_drug_keeps_id_and_medic_label():
    r = resolve_drug("FOO:1", "fallback name", {})
    assert r.id == "FOO:1"
    assert r.name == "fallback name"
    assert r.category == "biolink:ChemicalEntity"


# --- node class resolution -----------------------------------------------------------------------


def test_node_class_resolves_specific_biolink_class():
    cls, category = mi._node_class("biolink:SmallMolecule")
    assert cls is SmallMolecule
    assert category == "biolink:SmallMolecule"


def test_node_class_falls_back_to_named_thing_for_unknown_category():
    cls, category = mi._node_class("biolink:NotARealClass")
    assert cls is NamedThing
    assert category == "biolink:NamedThing"


# --- full transform ------------------------------------------------------------------------------


@pytest.fixture
def lookups(monkeypatch):
    monkeypatch.setattr(mi, "_MONDO_MAP", {"UMLS:C1": ("MONDO:0005009", "congestive heart failure")})
    monkeypatch.setattr(
        mi,
        "_NORM",
        {
            "CHEBI:8327": {
                "id": "CHEBI:8327",
                "name": "Polythiazide",
                "category": "biolink:SmallMolecule",
                "equivalent_identifiers": ["UNII:9"],
            }
        },
    )


@pytest.fixture
def record():
    return {
        "drug_id": "CHEBI:8327",
        "drug_label": "Polythiazide",
        "disease_id": "UMLS:C1",
        "disease_label": "heart failure",
        "agencies": [
            {"agency": "FDA", "infores": "infores:dailymed", "source_url": "", "indication_text": "indicated for ..."},
        ],
    }


def _kg(record):
    return transform_record(None, record)


def test_transform_normalizes_subject_and_object(lookups, record):
    kg = _kg(record)
    edge = kg.edges[0]
    assert isinstance(edge, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)
    assert edge.subject == "CHEBI:8327"
    assert edge.object == "MONDO:0005009"
    assert edge.original_object == "UMLS:C1"  # disease was remapped
    assert edge.original_subject is None  # drug id unchanged
    assert edge.predicate == "biolink:treats"


def test_transform_emits_typed_nodes(lookups, record):
    nodes = {n.id: n for n in _kg(record).nodes}
    assert set(nodes) == {"CHEBI:8327", "MONDO:0005009"}
    assert "biolink:SmallMolecule" in nodes["CHEBI:8327"].category
    assert nodes["CHEBI:8327"].equivalent_identifiers == ["UNII:9"]
    assert "biolink:Disease" in nodes["MONDO:0005009"].category
    assert nodes["MONDO:0005009"].name == "congestive heart failure"


def test_transform_keeps_provenance_fields(lookups, record):
    edge = _kg(record).edges[0]
    assert edge.knowledge_level == KnowledgeLevelEnum.knowledge_assertion
    assert edge.agent_type == AgentTypeEnum.text_mining_agent
    assert edge.primary_knowledge_source == "infores:medic"
    assert edge.publications == ["PMID:41385096"]
    assert edge.supporting_text == ["[FDA] indicated for ..."]
    supporting = next(s for s in edge.sources if s.resource_role == ResourceRoleEnum.supporting_data_source)
    assert supporting.resource_id == "infores:dailymed"
