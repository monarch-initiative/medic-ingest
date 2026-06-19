import sys

import pytest
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    KnowledgeLevelEnum,
    ResourceRoleEnum,
)

sys.path.insert(0, "src")
from medic_indication import transform_record


def _agency(agency, infores, source_url="", indication_text="indicated for ..."):
    return {
        "agency": agency,
        "infores": infores,
        "source_url": source_url,
        "indication_text": indication_text,
    }


@pytest.fixture
def fda_record():
    return {
        "drug_id": "CHEBI:7915",
        "drug_label": "Pantoprazole",
        "disease_id": "DOID:10017",
        "disease_label": "multiple endocrine neoplasia type 1",
        "agencies": [_agency("FDA", "infores:dailymed", indication_text="Pantoprazole is indicated for ...")],
    }


@pytest.fixture
def ema_record():
    return {
        "drug_id": "RXCUI:2556801",
        "drug_label": "estradiol / norethindrone / relugolix Pill",
        "disease_id": "MONDO:0007886",
        "disease_label": "uterine fibroid",
        "agencies": [
            _agency(
                "EMA",
                "infores:ema",
                source_url="https://www.ema.europa.eu/en/medicines/human/EPAR/ryeqo",
                indication_text="Ryeqo is indicated in adult women ...",
            )
        ],
    }


@pytest.fixture
def multi_agency_record():
    return {
        "drug_id": "CHEBI:17750",
        "drug_label": "Betaine",
        "disease_id": "MONDO:0004737",
        "disease_label": "homocystinuria",
        "agencies": [
            _agency("FDA", "infores:dailymed", indication_text="Cystadane is indicated for ..."),
            _agency("EMA", "infores:ema", source_url="https://www.ema.europa.eu/x", indication_text="indicated ..."),
            _agency("PMDA", "infores:pmda", indication_text="indicated ..."),
        ],
    }


def _edge(record):
    kg = transform_record(None, record)
    assert len(kg.edges) == 1
    return kg.edges[0]


def _supporting(assoc):
    return [s for s in assoc.sources if s.resource_role == ResourceRoleEnum.supporting_data_source]


def test_record_produces_single_association(fda_record):
    assoc = _edge(fda_record)
    assert isinstance(assoc, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)
    assert assoc.subject == "CHEBI:7915"
    assert assoc.object == "DOID:10017"
    assert assoc.predicate == "biolink:treats"


def test_emits_minimal_subject_and_object_nodes(fda_record):
    nodes = {n.id: n for n in transform_record(None, fda_record).nodes}
    assert set(nodes) == {"CHEBI:7915", "DOID:10017"}
    assert "biolink:ChemicalEntity" in nodes["CHEBI:7915"].category
    assert nodes["CHEBI:7915"].name == "Pantoprazole"
    assert "biolink:Disease" in nodes["DOID:10017"].category


def test_hp_object_becomes_phenotypic_feature(fda_record):
    record = {**fda_record, "disease_id": "HP:0012531", "disease_label": "Pain"}
    nodes = {n.id: n for n in transform_record(None, record).nodes}
    assert "biolink:PhenotypicFeature" in nodes["HP:0012531"].category


def test_association_has_required_fields(fda_record):
    assoc = _edge(fda_record)
    assert assoc.id is not None
    assert assoc.knowledge_level == KnowledgeLevelEnum.knowledge_assertion
    assert assoc.agent_type == AgentTypeEnum.text_mining_agent
    assert assoc.primary_knowledge_source == "infores:medic"
    assert assoc.publications == ["PMID:41385096"]


def test_single_agency_provenance(fda_record):
    """The approving regulator is recoverable from the retrieval-source path."""
    assoc = _edge(fda_record)
    primary = next(s for s in assoc.sources if s.resource_role == ResourceRoleEnum.primary_knowledge_source)
    assert primary.resource_id == "infores:medic"
    assert primary.upstream_resource_ids == ["infores:dailymed"]

    supporting = _supporting(assoc)
    assert len(supporting) == 1
    assert supporting[0].resource_id == "infores:dailymed"


def test_multi_agency_edge_has_one_supporting_source_each(multi_agency_record):
    """A pair approved by 3 agencies is one edge with 3 supporting sources."""
    assoc = _edge(multi_agency_record)
    supporting = _supporting(assoc)
    assert {s.resource_id for s in supporting} == {"infores:dailymed", "infores:ema", "infores:pmda"}

    primary = next(s for s in assoc.sources if s.resource_role == ResourceRoleEnum.primary_knowledge_source)
    assert primary.upstream_resource_ids == ["infores:dailymed", "infores:ema", "infores:pmda"]


def test_description_attributes_text_by_agency(multi_agency_record):
    desc = _edge(multi_agency_record).description
    assert desc.startswith("[FDA] Cystadane is indicated for ...")
    assert "[EMA]" in desc and "[PMDA]" in desc


def test_ema_source_url_attached_to_supporting_source(ema_record):
    supporting = _supporting(_edge(ema_record))[0]
    assert supporting.source_record_urls == ["https://www.ema.europa.eu/en/medicines/human/EPAR/ryeqo"]


def test_no_source_url_means_no_record_urls(fda_record):
    supporting = _supporting(_edge(fda_record))[0]
    assert supporting.source_record_urls is None
