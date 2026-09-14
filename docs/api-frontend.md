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
  "origin_type": "user_input",
  "origin_discovery_id": null,
  "created_at": "ISO",
  "user": { "id": "uuid", "display_name": "Demo User" },
  "enterprise": { "id": "uuid", "name": "筑脉科技" }
}
```

客户端不能指定 `origin_type` / `origin_discovery_id`。普通创建永远是 `user_input`。

`POST /api/user-submissions/{submission_id}/process`

同步执行 ingest → analyze，返回 Submission Detail。已成功则幂等返回现有结果。discovery-origin 与 user_input 走同一套 process / retry，不新建解析 Pipeline。

`GET /api/user-submissions?status=failed&limit=20&offset=0`

当前企业 Submission 库存，`created_at DESC`。列表不含完整 `input_content` 或 intelligence JSON。筑脉企服 Frontend 使用这个语义，不要改成 user-scoped。

`GET /api/user-submissions/mine?status=pending&limit=20&offset=0`

当前用户自己的解析 / 待处理工作列表。自动使用 CurrentIdentity 的 `enterprise_id` + `user_id`，客户端不能传 `user_id`。默认全部 status，`created_at DESC`。这是筑脉查查首页「为您推荐」的数据源。

列表项含 nullable `linked_service_case`。没有 ServiceCase 时为 `null`。GET 是纯读取，不会因为 succeeded 自动创建 Case。

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
    "origin_type": "user_input|discovery",
    "origin_discovery_id": "uuid|null",
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
  },
  "linked_service_case": {
    "id": "uuid",
    "status": "open|in_progress|completed|closed",
    "created_at": "ISO",
    "updated_at": "ISO",
    "completed_at": "ISO|null",
    "closed_at": "ISO|null"
  }
}
```

`POST /api/user-submissions/{submission_id}/service-case`

当前用户对自己 **succeeded** UserSubmission 发起「继续办理」。请求体不开放 title / status / identity / submission_id。第一次 201 `created=true`，重复 200 `created=false`，返回同一 ServiceCase。pending / ingesting / analyzing / failed → `409 SUBMISSION_NOT_READY_FOR_SERVICE`。同企业其他用户的 Submission → `404 SUBMISSION_NOT_FOUND`。

```text
UserSubmission = 用户正在了解 / 解析什么
ServiceCase    = 用户决定真正继续办理什么
Feishu         = 后续执行载体，不属于 D6.1
```

```text
Discovery → Accept → UserSubmission → succeeded → Continue to Service → ServiceCase(open)
用户直接输入 → UserSubmission → succeeded → Continue to Service → ServiceCase(open)
```

---

## Discovery

`DiscoveryItem` 是企业级发现 / 推荐业务对象。

```text
DiscoveryItem ≠ Notification
DiscoveryItem ≠ Opportunity
DiscoveryItem ≠ UserSubmission
DiscoveryItem ≠ IntelligenceRun
```

当前权限：`CurrentIdentity` 所属当前企业。没有 Platform Staff，不能跨企业指定目标。

创建 DiscoveryItem **不会发送通知**。客户端通过 Discovery API 主动读取 active 记录。

全部需要 Header: `X-Dev-User-Id`。`enterprise_id` / `created_by_user_id` 来自 CurrentIdentity，请求体不能覆盖。

`POST /api/discoveries` → 201

Opportunity：

```json
{
  "reference_type": "opportunity",
  "opportunity_id": "uuid",
  "reason": "string|null",
  "priority": "low|normal|high"
}
```

Source：

```json
{
  "reference_type": "source",
  "source_id": "uuid",
  "reason": "string|null",
  "priority": "low|normal|high"
}
```

Manual：

```json
{
  "reference_type": "manual",
  "title": "string",
  "summary": "string|null",
  "reason": "string|null",
  "priority": "low|normal|high"
}
```

Snapshot 由 Backend 构造。列表可直接渲染小程序「为你发现」卡片：`opportunity_type`、`deadline`、`title`、`reason`。相对时间由客户端根据 `deadline` 计算，Backend 不返回「3天后截止」。

`GET /api/discoveries?status=active&limit=20&offset=0`

当前企业列表。不传 `status` 时默认 `active`。排序：`high → normal → low`，同优先级 `created_at DESC`。

`GET /api/discoveries/{discovery_id}`

跨企业返回 `404 DISCOVERY_NOT_FOUND`。

`POST /api/discoveries/{discovery_id}/withdraw`

`active → withdrawn`，幂等返回 200。这是服务端撤回，不是用户 dismiss。

---

## Discovery User State

```text
DiscoveryItem
= enterprise-scoped content lifecycle（active / withdrawn）

DiscoveryUserState
= user-scoped interaction state
```

`DiscoveryItem.status` 不包含 seen / saved / deprioritized。

disposition：

```text
null           → 尚未判定，进入「为你发现」第一轮
saved          → 用户选择了这条 Discovery，进入 saved collection
deprioritized  → 稍后，继续留在「为你发现」后部
```

`saved` 不是筑脉查查首页「为您推荐」。首页工作列表的数据源是 `GET /api/user-submissions/mine`。

`seen_at` 独立于 disposition。第一次 mark seen 保留首次时间。设置 disposition 会自动 mark seen。

```text
GET /api/discoveries
= 企业 Discovery 库存，不受当前用户反馈影响

GET /api/discoveries/feed
= 当前用户待发现池（为你发现）

GET /api/discoveries/saved
= 当前用户 saved Discovery collection，不是首页「为您推荐」

GET /api/user-submissions/mine
= 当前用户解析 / 待处理工作列表（筑脉查查首页「为您推荐」）
```

Feed 只返回 `status=active`，排除 `saved`。排序：unseen+null → seen+null → deprioritized → priority → created_at DESC。GET /feed 是纯读取。

`GET /api/discoveries/saved` 只返回当前用户 `disposition=saved` 且 `status=active` 的卡片，字段与 Feed Item 一致。排序：`disposition_at DESC` → priority → created_at DESC。纯读取。撤回后不再出现在 /saved，但 UserState 保留。

`POST /api/discoveries/{discovery_id}/accept`

当前用户正式接受这条 Discovery，原子完成：

1. `DiscoveryUserState.disposition = saved`
2. 创建或复用 `UserSubmission(origin_type=discovery, status=pending)`

不 ingest、不调用 LLM。随后继续使用 `POST /api/user-submissions/{id}/process`。同一用户对同一 Discovery 幂等，返回原 submission，并带 `created: true|false`。第一次 201，重复 200。只允许 `status=active`。已撤回返回 `409 DISCOVERY_NOT_ACTIVE`，不改 UserState，不创建或改写 UserSubmission。跨企业仍是 `404 DISCOVERY_NOT_FOUND`。`/seen` 与 `PATCH /user-state` 对 withdrawn 的 stale-client 行为不变。

Backend 负责映射 input：

- `reference_url` 为 http/https → `input_type=url`
- 否则 text，使用 snapshot 的 title / summary（可含 issuer、region、deadline），不含 reason

`POST /api/discoveries/{discovery_id}/seen`

无 Request Body。时间由 Backend 生成。

`GET /api/discoveries/{discovery_id}/user-state`

没有状态时返回 200 空状态，不创建数据库行。

`PATCH /api/discoveries/{discovery_id}/user-state`

```json
{ "disposition": "saved|deprioritized|null" }
```

`dismissed` → 422。`extra="forbid"`。相同 disposition 幂等；可修改同一行；`null` 清除 disposition 但保留 `seen_at`。

`GET /api/discovery-user-states`

当前企业全部用户反馈的只读 Projection。支持 `discovery_id`、`user_id`、`disposition=saved|deprioritized`、`seen`、`limit`、`offset`。默认 `DiscoveryUserState.updated_at DESC`。不嵌套完整 Discovery。

```json
{
  "id": "uuid",
  "discovery": {
    "id": "uuid",
    "title": "string",
    "status": "active|withdrawn",
    "reference_type": "opportunity|source|manual"
  },
  "user": { "id": "uuid", "display_name": "Demo User" },
  "seen_at": "ISO|null",
  "disposition": "saved|deprioritized|null",
  "disposition_at": "ISO|null",
  "created_at": "ISO",
  "updated_at": "ISO",
  "linked_submission": {
    "id": "uuid",
    "status": "pending|ingesting|analyzing|succeeded|failed",
    "origin_type": "discovery",
    "created_at": "ISO",
    "completed_at": "ISO|null",
    "failure_stage": "ingest|analyze|null",
    "error_code": "string|null",
    "error_message": "string|null"
  }
}
```

```text
DiscoveryUserState
= 用户反馈事实（seen / disposition）

linked_submission
= 如果该 Discovery 已进入 UserSubmission 工作流，则提供当前工作流摘要
```

`saved != automatically accepted`。

- `saved` + `linked_submission != null` → 已进入解析工作流
- `saved` + `linked_submission == null` → 仅存在 saved UserState（例如只 PATCH saved，没有 Accept）
- `seen` / `deprioritized` 通常 `linked_submission = null`

是否进入工作流由 linked UserSubmission 这一事实表达，不另存 `is_accepted` / `accepted_at`。进入工作流时间用 `linked_submission.created_at`。

`GET /discovery-user-states` 是纯读取：不创建 UserState、不更新 Submission、不因 Submission 状态变化改写 `DiscoveryUserState.updated_at`。已撤回 Discovery 的历史 Feedback 仍然返回。

---

## Service Cases

`ServiceCase` 是企业用户基于一条 **succeeded** UserSubmission，明确决定继续推进的服务事项。

```text
UserSubmission = 内容理解 / 解析
ServiceCase    = 用户明确开始推进的服务事项
Feishu         = 后续执行载体，不属于 D6.1
```

Accept Discovery **不会**自动创建 ServiceCase。只有：

`POST /api/user-submissions/{submission_id}/service-case`

才创建。一个 UserSubmission 最多一个 ServiceCase。`origin_type=user_input` 与 `discovery` 只要 succeeded 都可以进入。

`GET /api/service-cases?status=open&user_id=uuid&limit=20&offset=0`

当前企业全部 ServiceCase。`created_at DESC`。客户端不能指定企业。轻量返回 created_by_user 与 submission 摘要，不含 Intelligence JSON / 完整 input_content。

`GET /api/service-cases/mine`

当前用户自己的 ServiceCase。scope 为 CurrentIdentity 的 enterprise_id + created_by_user_id。

`GET /api/service-cases/{service_case_id}`

当前企业 Detail。跨企业 `404 SERVICE_CASE_NOT_FOUND`。

本阶段不开放状态修改 API。内部状态机：

```text
open → in_progress → completed
open → closed
in_progress → closed
```

completed / closed 为终态。





