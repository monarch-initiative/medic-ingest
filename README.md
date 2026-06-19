# MeDIC

[MeDIC](https://doi.org/10.6084/m9.figshare.30491081) (Medicines, Diseases, Indications, and Contraindications) is a curated resource linking drugs to their therapeutic indications, assembled from the regulatory approval documents of three agencies: the **FDA** (via DailyMed), the **EMA** (via EPAR), and Japan's **PMDA**.

Data is downloaded from Figshare: `https://ndownloader.figshare.com/files/59187533`

Rather than the merged `indicationList.tsv`, this ingest extracts the three **per-agency deduplicated indication lists** from the archive so that provenance survives:

* `matrix-indication-list/data/02_intermediate/dailymed/fda_indications_deduplicated.xlsx` (FDA)
* `matrix-indication-list/data/02_intermediate/ema/ema_indications_deduplicated.xlsx` (EMA)
* `matrix-indication-list/data/02_intermediate/pmda/pmda_indications_deduplicated.xlsx` (PMDA)
* `matrix-indication-list/data/01_raw/ema-drugs.xlsx` (EMA EPAR source URLs)

`scripts/build_agency_indications.py` (run automatically by `just download`) groups these into `data/indications_by_agency.jsonl`, **one record per drug-disease pair**, with an `agencies` list naming every regulator that approved it (each entry carrying the verbatim indication text and — for EMA — the source EPAR URL).

## Drug to Disease Indications

Each record is a single drug-disease therapeutic indication. A pair approved by more than one regulator is **one record with multiple agency entries**, so the transform emits a single edge with one supporting source per agency rather than duplicate edges. All pairs with normalizable drug and disease CURIEs are ingested; rows where ID normalization failed are dropped.

Of 10,942 pairs, **1,217 (11%) are approved by more than one agency** — 909 by two and 308 by all three (FDA + EMA + PMDA).

### Combined Source Records (`data/indications_by_agency.jsonl`)

* drug_id (`final normalized drug id` — CHEBI, UNII, RXCUI, DRUGBANK, PUBCHEM.COMPOUND, …)
* drug_label
* disease_id (`final normalized disease id` — MONDO, DOID, UMLS, HP, NCIT, …)
* disease_label
* agencies — one entry per approving regulator, each with:
  * agency (`FDA`, `EMA`, or `PMDA`) and infores (`infores:dailymed` / `infores:ema` / `infores:pmda`)
  * indication_text (verbatim indication text from the regulatory label)
  * source_url (EMA EPAR landing page; blank for FDA/PMDA, which provide none)

### Biolink Captured

Output is written as **JSONL** (`output/medic_indication_{nodes,edges}.jsonl`).

#### biolink:ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation (edges)

* id (UUID)
* subject (`drug_id`, e.g. `CHEBI:7915`, `RXCUI:2556801`)
* predicate (`biolink:treats`)
* object (`disease_id`, e.g. `MONDO:0007886`, `HP:0012531`)
* knowledge_level (`knowledge_assertion`)
* agent_type (`text_mining_agent` — MeDIC extracts/normalizes indications from label text with an LLM)
* primary_knowledge_source (`infores:medic`)
* supporting_text (list of the verbatim regulatory indication texts, one `[AGENCY]`-prefixed entry per approving regulator)
* publications (`["PMID:41385096"]`)
* sources (Biolink `RetrievalSource` retrieval path):
  * `infores:medic` as `primary_knowledge_source`, with `upstream_resource_ids` naming **every** approving regulator
  * one `supporting_data_source` per approving regulator (`infores:dailymed` for FDA, `infores:ema` for EMA, `infores:pmda` for PMDA), with the EPAR URL in `source_record_urls` where available

The **approving agency (or agencies)** are recoverable from the `supporting_data_source` entries in `sources` — an indication approved by multiple regulators is one edge with multiple supporting sources.

#### Nodes

Minimal subject/object nodes are emitted (`id`, `category`, `name`) so the graph is self-contained:

* drugs → `biolink:ChemicalEntity`
* diseases → `biolink:Disease` (HP terms → `biolink:PhenotypicFeature`)

> **This ingest is not an authoritative source for nodes.** Node records are minimal placeholders carrying only an identifier, a coarse category, and the label MeDIC happened to normalize to. The CURIE-issuing ontologies (CHEBI, UNII, RXCUI, MONDO, HP, …) remain the sources of truth for node metadata, categories, and synonyms. Downstream merges should prefer those sources and treat these nodes only as join targets for the edges.

### Design Decisions

* **Per-agency, not merged:** We ingest the per-agency lists rather than `merge_lists/indicationList.tsv` specifically to retain which regulator approved each indication, the indication text, and EMA source URLs — all of which the merge step discards.
* **Provenance modeled like DAKP:** The `sources` retrieval path mirrors the sibling Multiomics Drug Approvals KP ingest, with MeDIC as the primary knowledge source and the regulator as the upstream supporting data source.
* **Non-authoritative nodes:** see the note above.
* **Single predicate:** All indications use `biolink:treats`. (Contraindications, which MeDIC also publishes, are out of scope for this ingest.)
* **Single publication:** All edges cite `PMID:41385096`, the MeDIC resource publication, rather than individual evidence references.

### Known limitations

* `infores:ema` and `infores:pmda` are not yet registered in the InfoRes catalogue (only `infores:dailymed` is); they may need registration or remapping before production use.
* EMA source URLs are matched to indications via an active-ingredient-set join against `ema-drugs.xlsx` (~76% coverage); unmatched EMA edges and all FDA/PMDA edges carry no `source_record_urls`.

## Output formats and validation

The canonical output is JSONL, because the edges carry nested provenance (`sources` is a list of Biolink `RetrievalSource` objects) that TSV has no native convention for.

### TSV copy — `just export-tsv`

Writes `output/medic_indication_{nodes,edges}.tsv` for consumers that want KGX TSV. `scripts/export_tsv.py` loads the JSONL into DuckDB and copies it back out, serializing per the [KGX TSV spec](https://github.com/biolink/kgx/blob/master/docs/kgx_format.md):

* **Multivalued scalar columns** (`category`, `publications`, `supporting_text`) → **pipe (`|`) delimited, no wrapping brackets** — the KGX convention.
* **Nested columns** (`sources`, a list of Biolink `RetrievalSource` structs) → **JSON**. KGX TSV has no standard for nested objects (the spec's TSV example omits them; KGX's own sink would emit Python `str(dict)` reprs), so JSON-in-cell is a deliberate, lossless, non-standard extension. Round-trip via the JSONL if strict KGX TSV is required.

This exists because Koza's graph-ops verbs don't (yet) do a faithful single-file format conversion: `split` fragments output by a field and `join` only builds a DuckDB. The proper home is a future koza `export`/`convert` verb (the inverse of the `load`/`join` family, tracked in [monarch-initiative/koza#230](https://github.com/monarch-initiative/koza/issues/230)); until then we do directly in DuckDB what koza would do internally.

### KGX validation summary — `just kgxval-summary`

Runs [monarch-initiative/kgxval](https://github.com/monarch-initiative/kgxval) on the JSONL output and writes `output/medic_kgxval_summary.xlsx` — edge-count summaries by subject/predicate/object category, supporting-data-source and publication breakdowns, sample rows, and Biolink prefix / subject-object-predicate validation sheets.

kgxval requires Python 3.13 and `bmt` (biolink-model-toolkit) from git, so it runs via `uvx`, isolated from this project's 3.12 environment; the source is staged under the short name `medic` because kgxval derives Excel sheet names from it (Excel caps sheet names at 31 chars). The rollup-sampling pass is slow (~5–10 min). kgxval reads the un-normalized JSONL directly and treats it as the "normalized" source, so the prefix-error sheet flags non-canonical id prefixes (`doid`, `drugbank`, `chembl.compound`, …) that node-normalization would later resolve.

The release workflow (`.github/workflows/release.yaml`) runs this step after the pipeline so `medic_kgxval_summary.xlsx` ships as a release artifact alongside the nodes/edges. It is marked `continue-on-error`, so a kgxval failure produces no summary but never blocks the data release.

## Citation

Sundar S, et al. MeDIC: Medicines, Diseases, Indications, and Contraindications. 2025. PMID: 41385096.

## License

BSD-3-Clause
