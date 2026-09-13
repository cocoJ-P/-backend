# API

Base: `http://127.0.0.1:8000`

错误：`{ "error": { "code": string, "message": string, "details": any } }`

---

## Health

`GET /api/health`

```json
{ "status": "ok", "service": "string", "environment": "string", "database": "ok" }
```

---

## Enterprises

`GET /api/enterprises`

```json
[{ "id": "uuid", "name": "string", "registration_region": "string|null", "enterprise_type": "technology_startup|sme|large_enterprise|other", "industry": "string|null" }]
```

`POST /api/enterprises` → 201

```json
{ "name": "string", "registration_region": "string|null", "established_at": "YYYY-MM-DD|null", "enterprise_type": "technology_startup|sme|large_enterprise|other", "industry": "string|null" }
```

`GET /api/enterprises/{enterprise_id}`

```json
{ "id": "uuid", "name": "string", "registration_region": "string|null", "established_at": "YYYY-MM-DD|null", "enterprise_type": "string", "industry": "string|null", "created_at": "ISO", "updated_at": "ISO" }
```

`GET /api/enterprises/{enterprise_id}/state`

```json
{
  "id": "uuid", "enterprise_id": "uuid",
  "product_stage": "idea|prototype|demo|product_validation|commercial_validation|scaling|mature",
  "business_stage": "pre_revenue|early_revenue|repeatable_revenue|growth|scale",
  "team_size": "int|null",
  "revenue_stage": "no_revenue|early_revenue|stable_revenue|growth_revenue|unknown",
  "funding_stage": "bootstrapped|pre_seed|seed|pre_a|series_a|later|unknown",
  "ip_count": "int|null",
  "qualifications": ["string"] | null,
  "current_goal": "string|null",
  "current_constraint": "string|null",
  "recent_events": ["string"] | null,
  "available_materials": ["string"] | null,
  "effective_at": "ISO", "created_at": "ISO"
}
```

`POST /api/enterprises/{enterprise_id}/states` → 201

```json
{
  "product_stage": "demo",
  "business_stage": "pre_revenue",
  "team_size": 4,
  "revenue_stage": "no_revenue",
  "funding_stage": "bootstrapped",
  "ip_count": null,
  "qualifications": ["string"],
  "current_goal": "string|null",
  "current_constraint": "string|null",
  "recent_events": ["string"],
  "available_materials": ["string"],
  "effective_at": "ISO|null"
}
```

---

## Opportunities

`GET /api/opportunities?type=policy|competition|financial_service|equity_funding|park_service|scenario|other`

```json
[{ "id": "uuid", "type": "string", "title": "string", "issuer": "string|null", "region": "string|null", "deadline": "YYYY-MM-DD|null", "status": "draft|active|upcoming|expired|closed|unknown" }]
```

`POST /api/opportunities` → 201

```json
{
  "type": "policy",
  "title": "string",
  "issuer": "string|null",
  "region": "string|null",
  "publish_date": "YYYY-MM-DD|null",
  "deadline": "YYYY-MM-DD|null",
  "status": "draft",
  "official_url": "string|null",
  "summary": "string|null",
  "resource_value": {},
  "required_materials": ["string"],
  "application_process": ["string"]
}
```

`GET /api/opportunities/{opportunity_id}`

```json
{
  "id": "uuid", "type": "string", "title": "string", "issuer": "string|null", "region": "string|null",
  "publish_date": "YYYY-MM-DD|null", "deadline": "YYYY-MM-DD|null",
  "status": "string", "official_url": "string|null", "summary": "string|null",
  "resource_value": {}, "required_materials": ["string"], "application_process": ["string"],
  "sources": [], "requirements": [],
  "created_at": "ISO", "updated_at": "ISO"
}
```

`GET /api/opportunities/{opportunity_id}/sources`

`POST /api/opportunities/{opportunity_id}/sources` → 201

`POST /api/opportunity-sources` → 201

```json
{
  "opportunity_id": "uuid|null",
  "source_type": "official_document|official_news|official_wechat|media_article|wechat_article|service_provider|other|unknown",
  "title": "string",
  "publisher": "string|null",
  "url": "string|null",
  "published_at": "ISO|null",
  "content_excerpt": "string|null"
}
```

```json
{
  "id": "uuid", "opportunity_id": "uuid|null", "source_type": "string",
  "title": "string|null", "publisher": "string|null", "url": "string|null",
  "published_at": "ISO|null", "content_excerpt": "string|null",
  "created_at": "ISO", "updated_at": "ISO"
}
```

`GET /api/opportunities/{opportunity_id}/requirements`

`POST /api/opportunities/{opportunity_id}/requirements` → 201

```json
{
  "key": "string",
  "label": "string",
  "operator": "equals|not_equals|in|not_in|gte|lte|gt|lt|contains|exists|manual_review",
  "expected_value": {},
  "required": true,
  "description": "string|null",
  "source_reference": "string|null"
}
```

```json
{
  "id": "uuid", "opportunity_id": "uuid", "key": "string", "label": "string",
  "operator": "string", "expected_value": {}, "required": true,
  "description": "string|null", "source_reference": "string|null", "created_at": "ISO"
}
```

---

## Content

`POST /api/content/ingest` → 201

```json
{ "content_type": "url|text", "content": "string" }
```

```json
{
  "normalized_content": {
    "input_type": "url|text",
    "original_input": "string",
    "source_url": "string|null",
    "resolved_url": "string|null",
    "content_type": "string|null",
    "title": "string|null",
    "publisher": "string|null",
    "published_at": "ISO|null",
    "text": "string|null",
    "excerpt": "string|null",
    "fetch_status": "not_required|success|failed|blocked|timeout|invalid_url|unsupported_content_type",
    "extraction_status": "success|partial|failed|not_required|insufficient_content|unsupported",
    "http_status": "int|null",
    "warnings": ["string"]
  },
  "source": { "id": "uuid", "opportunity_id": "uuid|null" },
  "ingestion": { "id": "uuid", "source_id": "uuid" }
}
```

---

## Intelligence

`POST /api/opportunity-sources/{source_id}/analyze`

```json
{ "ingestion_id": "uuid|null", "force": false }
```

```json
{
  "run": {
    "id": "uuid",
    "source_id": "uuid",
    "ingestion_id": "uuid",
    "status": "running|succeeded|failed",
    "input_hash": "string",
    "analysis_fingerprint": "string",
    "rule_version": "string",
    "prompt_version": "string",
    "provider": "string",
    "model": "string",
    "input_char_count": 0,
    "input_truncated": false,
    "error_code": "string|null",
    "error_message": "string|null",
    "started_at": "ISO",
    "completed_at": "ISO|null",
    "created_at": "ISO"
  },
  "reused": false,
  "intelligence_result": {
    "analysis": {
      "content_nature": "opportunity_announcement|opportunity_interpretation|news_report|marketing_content|service_content|general_information|mixed|unknown",
      "opportunity_relevance": "high|medium|low|none|unknown",
      "confidence": 0.8,
      "warnings": ["string"]
    },
    "source_assessment": {
      "apparent_source_type": "official_like|media_like|service_provider_like|individual_like|unknown",
      "marketing_level": "none|low|medium|high|unknown",
      "marketing_signals": ["string"],
      "intermediary_level": "none|possible|likely|unknown",
      "intermediary_signals": ["string"],
      "originality_claim": "claims_original|appears_repost|appears_interpretation|unclear"
    },
    "opportunity_claim": {
      "claimed_type": "policy|null",
      "claimed_title": "string|null",
      "claimed_issuer": "string|null",
      "claimed_region": "string|null",
      "claimed_publish_date": "YYYY-MM-DD|null",
      "claimed_deadline": "YYYY-MM-DD|null",
      "claimed_status": "active|upcoming|expired|closed|unknown|null",
      "claimed_summary": "string|null",
      "claimed_resource_value": {
        "funding": { "description": "string|null", "amount": "number|null", "currency": "string|null", "amount_type": "string|null" },
        "scenario": "bool|string|null",
        "financing": "string|null",
        "service": "string|null",
        "other": ["string"]
      },
      "claimed_requirements": [{
        "key": "string", "label": "string", "operator": "string",
        "expected_value": {}, "required": false, "description": "string|null",
        "confidence": 0.0, "evidence_ids": ["string"]
      }],
      "claimed_required_materials": ["string"],
      "claimed_application_process": ["string"],
      "claimed_official_url": "string|null",
      "claim_confidence": 0.0
    },
    "evidence": [{ "id": "string", "kind": "direct_quote|metadata|derived_signal", "field": "string|null", "text": "string", "source": "string|null" }],
    "metadata": { "schema_version": "1.0", "analyzer_version": "string", "created_at": "ISO" }
  }
}
```

`GET /api/intelligence-runs/{run_id}`

```json
{ "run": {}, "intelligence_result": {} }
```

`GET /api/opportunity-sources/{source_id}/intelligence-runs?limit=20`

---

## Identity

`GET /api/me`

Header: `X-Dev-User-Id: uuid`（仅开发环境，不是生产认证）

```json
{
  "user": { "id": "uuid", "display_name": "Demo User", "status": "active" },
  "enterprise": { "id": "uuid", "name": "筑脉科技" },
  "membership": { "id": "uuid", "role": "owner|admin|member", "status": "active|inactive" }
}
```

---

## User Submissions

全部需要 Header: `X-Dev-User-Id`。`user_id` / `enterprise_id` 来自 CurrentIdentity，请求体不能覆盖。

`POST /api/user-submissions` → 201

只创建 `pending` 记录，不立即 ingest / analyze。

```json
{ "input_type": "url|text", "content": "string" }
```

```json
{
  "id": "uuid",
  "status": "pending",
  "input_type": "text",
  "input_preview": "string",
  "created_at": "ISO",
  "user": { "id": "uuid", "display_name": "Demo User" },
  "enterprise": { "id": "uuid", "name": "筑脉科技" }
}
```

`POST /api/user-submissions/{submission_id}/process`

同步执行 ingest → analyze，返回 Submission Detail。已成功则幂等返回现有结果。

`GET /api/user-submissions?status=failed&limit=20&offset=0`

当前企业 Submission 列表，`created_at DESC`。列表不含完整 `input_content` 或 intelligence JSON。

`GET /api/user-submissions/{submission_id}`

```json
{
  "submission": {
    "id": "uuid",
    "status": "pending|ingesting|analyzing|succeeded|failed",
    "failure_stage": "ingest|analyze|null",
    "input_type": "url|text",
    "input_content": "string",
    "input_preview": "string",
    "source_id": "uuid|null",
    "ingestion_id": "uuid|null",
    "intelligence_run_id": "uuid|null",
    "error_code": "string|null",
    "error_message": "string|null",
    "created_at": "ISO",
    "updated_at": "ISO",
    "completed_at": "ISO|null"
  },
  "submitted_by": { "id": "uuid", "display_name": "Demo User", "status": "active" },
  "enterprise": { "id": "uuid", "name": "筑脉科技" },
  "content": {
    "title": "string|null",
    "publisher": "string|null",
    "resolved_url": "string|null",
    "excerpt": "string|null",
    "fetch_status": "string|null",
    "extraction_status": "string|null",
    "warnings": ["string"]
  },
  "intelligence": {
    "run_id": "uuid",
    "status": "succeeded|failed|running",
    "result": {}
  }
}
```


