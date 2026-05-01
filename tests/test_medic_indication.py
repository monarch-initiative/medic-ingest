from unittest.mock import MagicMock, patch

import pytest
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    Disease,
    Drug,
    KnowledgeLevelEnum,
    NamedThing,
)

import sys
sys.path.insert(0, "src")
from medic_indication import _nameres_lookup, transform_record


@pytest.fixture(autouse=True)
def clear_nameres_cache():
    """Clear the NameRes LRU cache before each test."""
    _nameres_lookup.cache_clear()


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


@pytest.fixture
def mondo_disease_row():
    """Row where the disease uses a MONDO prefix (excluded)."""
    return {
        "drug|disease": "MONDO:0005148|DRUGBANK:DB00028",
        "disease ID labels": "type 2 diabetes mellitus",
        "drug ID Label": "Human immunoglobulin G",
        "drug ID": "DRUGBANK:DB00028",
        "disease IDs": "MONDO:0005148",
        "active ingredients in therapy": "['HUMAN IMMUNOGLOBULIN G']",
        "list of diseases": "['TYPE 2 DIABETES MELLITUS']",
    }


@pytest.fixture
def nameres_failed_row():
    """Row where the drug ID is 'NameRes Failed'."""
    return {
        "drug|disease": "DOID:10017|NameRes Failed",
        "disease ID labels": "multiple endocrine neoplasia type 1",
        "drug ID Label": "NameRes Failed",
        "drug ID": "NameRes Failed",
        "disease IDs": "DOID:10017",
        "active ingredients in therapy": "['UNKNOWN']",
        "list of diseases": "['MULTIPLE ENDOCRINE NEOPLASIA TYPE 1)']",
    }


def _mock_nameres_response(curie_data: dict):
    """Create a mock response for NameRes reverse_lookup."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = curie_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# --- NameRes Failed filtering tests ---


@patch("medic_indication.requests.post")
def test_nameres_failed_row_skipped(mock_post, nameres_failed_row):
    """Rows with 'NameRes Failed' as drug ID should produce no entities."""
    result = transform_record(None, nameres_failed_row)
    assert result == []
    mock_post.assert_not_called()


# --- NameRes lookup tests ---


@patch("medic_indication.requests.post")
def test_nameres_lookup_returns_specific_class(mock_post, drugbank_drug_row):
    """NameRes returning 'Drug' type should produce a Drug node, not NamedThing."""
    mock_post.return_value = _mock_nameres_response({
        "DRUGBANK:DB00028": {
            "preferred_name": "Immune globulin human",
            "types": ["Drug", "ChemicalEntity"],
            "curie": "DRUGBANK:DB00028",
        },
        "DOID:12177": {
            "preferred_name": "CVID",
            "types": ["Disease", "DiseaseOrPhenotypicFeature"],
            "curie": "DOID:12177",
        },
    })
    result = transform_record(None, drugbank_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]

    drug_nodes = [n for n in nodes if n.id == "DRUGBANK:DB00028"]
    assert len(drug_nodes) == 1
    assert isinstance(drug_nodes[0], Drug)
    assert drug_nodes[0].name == "Immune globulin human"

    disease_nodes = [n for n in nodes if n.id == "DOID:12177"]
    assert len(disease_nodes) == 1
    assert isinstance(disease_nodes[0], Disease)
    assert disease_nodes[0].name == "CVID"


@patch("medic_indication.requests.post")
def test_nameres_lookup_fallback_on_failure(mock_post, drugbank_drug_row):
    """When NameRes fails, nodes should fall back to NamedThing with source name."""
    mock_post.side_effect = Exception("Connection error")
    result = transform_record(None, drugbank_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]

    drug_nodes = [n for n in nodes if n.id == "DRUGBANK:DB00028"]
    assert len(drug_nodes) == 1
    assert drug_nodes[0].name == "Human immunoglobulin G"
    assert type(drug_nodes[0]) is NamedThing


@patch("medic_indication.requests.post")
def test_nameres_lookup_cached(mock_post, drugbank_drug_row):
    """Calling with same CURIE twice should only make one HTTP call per unique CURIE."""
    mock_post.return_value = _mock_nameres_response({
        "DRUGBANK:DB00028": {
            "preferred_name": "Immune globulin human",
            "types": ["Drug"],
            "curie": "DRUGBANK:DB00028",
        },
        "DOID:12177": {
            "preferred_name": "CVID",
            "types": ["Disease"],
            "curie": "DOID:12177",
        },
    })
    # Call transform twice with the same row
    transform_record(None, drugbank_drug_row)
    transform_record(None, drugbank_drug_row)

    # Each unique CURIE should result in exactly one HTTP call
    # DRUGBANK:DB00028 and DOID:12177 = 2 calls total (cached on second transform)
    assert mock_post.call_count == 2


@patch("medic_indication.requests.post")
def test_nameres_uses_source_name_when_preferred_name_null(mock_post, drugbank_drug_row):
    """When NameRes returns null preferred_name, source name should be used."""
    mock_post.return_value = _mock_nameres_response({
        "DRUGBANK:DB00028": {
            "preferred_name": None,
            "types": ["Drug"],
            "curie": "DRUGBANK:DB00028",
        },
        "DOID:12177": {
            "preferred_name": None,
            "types": ["Disease"],
            "curie": "DOID:12177",
        },
    })
    result = transform_record(None, drugbank_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]

    drug_nodes = [n for n in nodes if n.id == "DRUGBANK:DB00028"]
    assert drug_nodes[0].name == "Human immunoglobulin G"
    assert isinstance(drug_nodes[0], Drug)


# --- Association tests (mock NameRes to avoid HTTP calls) ---


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_chebi_drug_produces_association(mock_post, chebi_drug_row):
    result = transform_record(None, chebi_drug_row)
    associations = [r for r in result if isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    assert len(associations) == 1

    assoc = associations[0]
    assert assoc.subject == "CHEBI:7915"
    assert assoc.object == "DOID:10017"
    assert assoc.predicate == "biolink:treats"


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_drugbank_drug_produces_association(mock_post, drugbank_drug_row):
    result = transform_record(None, drugbank_drug_row)
    associations = [r for r in result if isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    assert len(associations) == 1

    assoc = associations[0]
    assert assoc.subject == "DRUGBANK:DB00028"
    assert assoc.object == "DOID:12177"
    assert assoc.predicate == "biolink:treats"


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_association_has_required_fields(mock_post, chebi_drug_row):
    result = transform_record(None, chebi_drug_row)
    associations = [r for r in result if isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    assoc = associations[0]

    assert assoc.id is not None
    assert assoc.subject == "CHEBI:7915"
    assert assoc.object == "DOID:10017"
    assert assoc.predicate == "biolink:treats"
    assert assoc.knowledge_level == KnowledgeLevelEnum.knowledge_assertion
    assert assoc.agent_type == AgentTypeEnum.automated_agent
    assert assoc.primary_knowledge_source == "infores:medic"
    assert assoc.publications == ["PMID:41385096"]


# --- Node exclusion tests (mock NameRes to avoid HTTP calls) ---


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_chebi_drug_excluded_from_nodes(mock_post, chebi_drug_row):
    """CHEBI-prefixed drug should NOT produce a node."""
    result = transform_record(None, chebi_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    node_ids = [n.id for n in nodes]
    assert "CHEBI:7915" not in node_ids


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_mondo_disease_excluded_from_nodes(mock_post, mondo_disease_row):
    """MONDO-prefixed disease should NOT produce a node."""
    result = transform_record(None, mondo_disease_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    node_ids = [n.id for n in nodes]
    assert "MONDO:0005148" not in node_ids


# --- Node inclusion tests (mock NameRes to avoid HTTP calls) ---


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_drugbank_drug_produces_node(mock_post, drugbank_drug_row):
    """DRUGBANK-prefixed drug should produce a node."""
    result = transform_record(None, drugbank_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    drug_nodes = [n for n in nodes if n.id == "DRUGBANK:DB00028"]
    assert len(drug_nodes) == 1
    node = drug_nodes[0]
    assert node.name == "Human immunoglobulin G"
    assert node.provided_by == ["infores:medic"]


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_doid_disease_produces_node(mock_post, drugbank_drug_row):
    """DOID-prefixed disease should produce a node."""
    result = transform_record(None, drugbank_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    disease_nodes = [n for n in nodes if n.id == "DOID:12177"]
    assert len(disease_nodes) == 1
    node = disease_nodes[0]
    assert node.name == "common variable immunodeficiency"
    assert node.provided_by == ["infores:medic"]


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_chebi_row_only_produces_disease_node(mock_post, chebi_drug_row):
    """Row with CHEBI drug and DOID disease: only disease node emitted."""
    result = transform_record(None, chebi_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    assert len(nodes) == 1
    assert nodes[0].id == "DOID:10017"
    assert nodes[0].name == "multiple endocrine neoplasia type 1"


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_mondo_row_only_produces_drug_node(mock_post, mondo_disease_row):
    """Row with DRUGBANK drug and MONDO disease: only drug node emitted."""
    result = transform_record(None, mondo_disease_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    assert len(nodes) == 1
    assert nodes[0].id == "DRUGBANK:DB00028"
    assert nodes[0].name == "Human immunoglobulin G"


@patch("medic_indication.requests.post", return_value=_mock_nameres_response({}))
def test_drugbank_row_produces_two_nodes(mock_post, drugbank_drug_row):
    """Row with DRUGBANK drug and DOID disease: both nodes emitted."""
    result = transform_record(None, drugbank_drug_row)
    nodes = [r for r in result if isinstance(r, NamedThing) and not isinstance(r, ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation)]
    assert len(nodes) == 2
    node_ids = {n.id for n in nodes}
    assert node_ids == {"DRUGBANK:DB00028", "DOID:12177"}
