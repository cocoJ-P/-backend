# Opportunity Intelligence Contract

Backend B4.1 defines the Opportunity Intelligence contract only.

There is no analyzer, no LLM, no search, and no verification in this stage.

## Four rules

1. B4 extracts claims, not verified facts.
2. Marketing content may describe a real opportunity.
3. Apparent official source is not equivalent to verified official source.
4. Unknown information must remain unknown rather than being guessed.

## What B4 can answer

> What does this content claim?

Examples of claims:

- `claimed_issuer`
- `claimed_deadline`
- `claimed_resource_value`

B4 must not output `verified = true`.

## Separations

| Content / source field | Claim field | Meaning |
|---|---|---|
| `publisher` | `claimed_issuer` | Page publisher vs claimed issuing authority |
| source `title` | `claimed_title` | Marketing headline vs opportunity name |
| source `published_at` | `claimed_publish_date` | When the page appeared vs when the opportunity is said to have been published |

## Not the same thing

- `marketing_level = high` does not mean the content is fake.
- `intermediary_level = likely` does not mean the opportunity is invalid.
- `apparent_source_type = official_like` is not a verified official source.

## Unknown

If a date cannot be turned into an absolute `date`, keep `null` and keep the original wording in evidence.

Do not replace `claimed_issuer` with `publisher` just to fill a field.

## Current objects

- `ContentIntelligenceInput`
- `ContentIntelligenceResult`
- `IntelligenceAnalysis`
- `SourceAssessment`
- `OpportunityClaim`
- `ClaimedRequirement`
- `IntelligenceEvidence`
- `IntelligenceMetadata`

`schema_version` is `1.0`. `analyzer_version` is currently `contract-only`.

This contract does not persist results and does not expose a production analyze API.

## Rule Layer

Backend B4.2 adds a deterministic Rule Layer in front of later LLM extraction.

Rules produce deterministic signals, not verified facts.

Rules assist semantic analysis but do not replace it.

A single keyword must not determine source authenticity or opportunity validity.

```text
B3 Normalized Content
↓
B4.2 RuleAnalyzer → RuleAnalysisResult
↓
B4.3 LLM Structured Extraction (not implemented)
↓
B4.4 Intelligence Orchestrator (not implemented)
```

`RuleAnalysisResult` contains `signals`, `date_candidates`, `url_candidates`, `amount_candidates`, `entity_candidates`, `evidence`, and `metadata`.

It is not `ContentIntelligenceResult`. Rule Layer does not output `marketing_level`, `intermediary_level`, `official`, or `verified`.

Semantic boundaries:

- A `gov.cn` URL candidate is `official_domain_like`. That is a domain-like signal, not a verified Opportunity official source.
- A phone number is `structure.contact_information_present`. It is not an intermediary judgment.
- Marketing keywords are signals, not proof that content is fake.
- `AmountCandidate[]` lists every explicit amount. The Rule Layer does not select the final Opportunity resource value.
- `DateCandidate` is not the final Opportunity deadline. Fuzzy phrases such as `本月底` keep `value = null`.
- Source `published_at` is never used to infer a deadline.

Evidence reuses `IntelligenceEvidence`. Quote snippets are clipped to ≤300 characters. Signal `evidence_ids` must reference evidence in the same result.

`rule_version` is `rules-v1`. Rule Layer is an internal capability: no public analyze API, no new tables.

## LLM Extraction

Backend B4.3 sends normalized content plus RuleAnalysisResult to an LLM and validates the response as `ContentIntelligenceResult`.

LLM extracts and interprets claims.

LLM does not verify external truth.

Rule signals are supporting observations, not final judgments.

Evidence must originate from supplied content or metadata.

```text
ContentIntelligenceInput + RuleAnalysisResult
↓
Prompt Builder (intelligence-extract-v1)
↓
LLMProvider.structured_generate
↓
Pydantic Validation + Evidence Validation
↓
ContentIntelligenceResult
```

The LLM analyzer does not search the web, does not verify authenticity, and does not persist runs. There is no public `/api/llm/analyze` endpoint.

`official_like` remains a content-layer appearance. It is not a verified official source.

## Intelligence Orchestration

Backend B4.4 wires ingestion, rules, and LLM extraction into a persisted pipeline.

An IntelligenceRun records an analysis execution.

A succeeded IntelligenceRun means:
the content was successfully analyzed.

It does not mean:
the claimed opportunity has been externally verified.

```text
OpportunitySource + IngestedContent
↓
RuleAnalyzer
↓
LLMIntelligenceAnalyzer
↓
IntelligenceRun (JSON snapshot)
↓
POST /api/opportunity-sources/{source_id}/analyze
```

`force=false` reuses a succeeded run with the same analysis fingerprint. `force=true` always creates a new run.

The orchestrator does not create Opportunity records, does not change `OpportunitySource.source_type` or `opportunity_id`, and does not search the web.


