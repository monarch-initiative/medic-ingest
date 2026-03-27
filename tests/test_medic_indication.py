import pytest
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    KnowledgeLevelEnum,
)

import sys
sys.path.insert(0, "src")
from medic_indication import transform_record


@pytest.fixture
def chebi_drug_row():
    return {
        "drug|disease": "DOID:10017|CHEBI:7915",
        "disease ID labels": "multiple endocrine neoplasia type 1",
        "drug ID Label": "Pantoprazole",
        "drug ID": "CHEBI:7915",
        "disease IDs": "DOID:10017",
        "active ingredients in therapy": "['PANTOPRAZOLE']",
        "list of diseases": "['MULTIPLE ENDOCRINE NEOPLASIA TYPE 1)']",
    }


@pytest.fixture
def drugbank_drug_row():
    return {
        "drug|disease": "DOID:12177|DRUGBANK:DB00028",
        "disease ID labels": "common variable immunodeficiency",
        "drug ID Label": "Human immunoglobulin G",
        "drug ID": "DRUGBANK:DB00028",
        "disease IDs": "DOID:12177",
        "active ingredients in therapy": "['HUMAN IMMUNOGLOBULIN G']",
        "list of diseases": "['COMMON VARIABLE IMMUNODEFICIENCY (CVID)']",
    }


def test_chebi_drug_produces_association(chebi_drug_row):
    result = transform_record(None, chebi_drug_row)
    assert result is not None
    assert len(result) == 1

    assoc = result[0]
    assert isinstance(assoc, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)
    assert assoc.subject == "CHEBI:7915"
    assert assoc.object == "DOID:10017"
    assert assoc.predicate == "biolink:treats"


def test_drugbank_drug_produces_association(drugbank_drug_row):
    result = transform_record(None, drugbank_drug_row)
    assert result is not None
    assert len(result) == 1

    assoc = result[0]
    assert isinstance(assoc, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)
    assert assoc.subject == "DRUGBANK:DB00028"
    assert assoc.object == "DOID:12177"
    assert assoc.predicate == "biolink:treats"


def test_association_has_required_fields(chebi_drug_row):
    result = transform_record(None, chebi_drug_row)
    assoc = result[0]

    assert assoc.id is not None
    assert assoc.subject == "CHEBI:7915"
    assert assoc.object == "DOID:10017"
    assert assoc.predicate == "biolink:treats"
    assert assoc.knowledge_level == KnowledgeLevelEnum.knowledge_assertion
    assert assoc.agent_type == AgentTypeEnum.automated_agent
    assert assoc.primary_knowledge_source == "infores:medic"
    assert assoc.publications == ["PMID:41385096"]
