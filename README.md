# 筑脉企服 Backend

本项目是**筑脉企服统一业务后端**。

未来服务：

- 筑脉查查微信小程序
- 企业飞书工作空间
- 筑脉企服 Service Web

当前工程采用模块化单体（Modular Monolith），使用 `uv` 管理 Python 环境与依赖。

本机两个进程怎么开：`docs/start.md`。

## 当前阶段

Backend D6.6：Feishu → Backend Status Sync。

## 当前已实现

- Enterprise Domain
- Opportunity Domain
- Content Ingestion
- Safe URL Fetch
- HTML Extraction
- Text Normalization
- Opportunity Intelligence Contract
- Rule Layer（确定性信号，不是最终 Intelligence 判断）
- LLM Structured Extraction（声称抽取，不是真实性验证）
- Opportunity Intelligence Orchestrator（可持久化分析运行与 API）
- Development Identity
- User Submission Domain
- Discovery Domain（企业级发现 / 推荐业务对象）
- Discovery User State（按用户区分的 seen / disposition）
- Discovery → UserSubmission Accept Bridge
- Discovery Feedback Projection（`GET /api/discovery-user-states.linked_submission`）
- ServiceCase Domain（用户明确开始推进的服务事项，与飞书解耦）
- Feishu Adapter Foundation（ServiceCaseFeishuBinding + Bitable Adapter）
- ServiceCase → Feishu Outbound Sync（创建 Case 后 BackgroundTask 同步多维表格；飞书失败不回滚业务）
- Feishu Official SDK Full Migration（OpenAPI = `lark-oapi` Client；Event Transport = `lark.ws.Client`；业务 Adapter / Binding / Sync 不变）
- Feishu → Backend Status Sync（独立 Event Worker 长连接；飞书「办理状态」经 Domain `transition_service_case_status` 写入 ServiceCase）

## Discovery

DiscoveryItem 是 enterprise-scoped recommendation / discovery business object。
DiscoveryUserState 是 user-scoped interaction state。

`	ext
DiscoveryItem ≠ Notification
DiscoveryItem ≠ Opportunity
DiscoveryItem ≠ UserSubmission
DiscoveryItem ≠ IntelligenceRun
`

当前权限：CurrentIdentity scoped，current enterprise only。没有 Platform Staff，不能跨企业 Targeting。

Creating a DiscoveryItem does not send a notification. Clients retrieve active discoveries through the Discovery API.

`	ext
GET /api/discoveries
= enterprise inventory

GET /api/discoveries/feed
= current-user feed
`

disposition: null / saved / deprioritized。seen_at 独立于 disposition。
saved 不是自动 accepted。只有 `linked_submission` 存在才能确定该 Discovery 已进入解析工作流。
GET /api/discovery-user-states 是企业反馈 Projection：DiscoveryUserState 是用户反馈事实；linked_submission 是关联工作流摘要。
筑脉查查首页「为您推荐」数据源是 GET /api/user-submissions/mine，不是 /saved。没有 dismissed。

## ServiceCase

UserSubmission 是内容理解 / 解析。ServiceCase 是用户明确开始推进的服务事项。

```text
ServiceCase = 业务事实
ServiceCaseFeishuBinding = 外部集成绑定事实
Feishu Bitable = 后续执行载体
```

`service_cases` 不保存 `feishu_record_id` / `feishu_table_id` / `sync_status`。绑定存在独立表 `service_case_feishu_bindings`。

创建 ServiceCase 时：先 COMMIT 业务事实；若 `FEISHU_ENABLED=true` 且是首次创建，再写 Binding(pending) 并用 FastAPI BackgroundTask 同步飞书。飞书失败只把 Binding 标为 `failed`，ServiceCase 仍为 `open`。

显式补同步历史 Case（不会 startup 扫描）：

```bash
uv run python -m app.integrations.feishu.sync_service_case <SERVICE_CASE_ID>
```

失败恢复与对账（一次性命令，不是常驻 worker，没有 Celery / Redis / Kafka）：

```bash
uv run python -m app.integrations.feishu.retry_service_case <SERVICE_CASE_ID>
uv run python -m app.integrations.feishu.retry_event_receipt <RECEIPT_ID>
uv run python -m app.integrations.feishu.retry_failed_syncs --direction all --limit 50
uv run python -m app.integrations.feishu.reconcile_service_case <SERVICE_CASE_ID>
```

详见 `docs/feishu-integration.md`。

Accept Discovery 不会自动创建 ServiceCase。只有 POST /api/user-submissions/{id}/service-case 才创建。一个 Submission 最多一个 Case。

`	ext
POST /api/discoveries
GET  /api/discoveries
GET  /api/discoveries/feed
GET  /api/discoveries/saved
GET  /api/discoveries/{discovery_id}
POST /api/discoveries/{discovery_id}/withdraw
POST /api/discoveries/{discovery_id}/accept
POST /api/discoveries/{discovery_id}/seen
GET  /api/discoveries/{discovery_id}/user-state
PATCH /api/discoveries/{discovery_id}/user-state
GET  /api/discovery-user-states
POST /api/user-submissions/{submission_id}/service-case
GET  /api/service-cases
GET  /api/service-cases/mine
GET  /api/service-cases/{service_case_id}
`

## 当前未实现

- Source Verification
- Official Source Search
- Web Search
- Provenance
- Deduplication
- Opportunity Resolution
- Matching
- Enterprise Lead
- Search
- Feishu retry UI / Feishu dashboard
- D6.8 Mini Program Case Status
- D6.9 Final E2E
- WeChat Auth
- Notify

## Opportunity Intelligence

B4 已形成完整 Content Intelligence Pipeline：

```text
Content Ingestion
↓
Rule Analysis
↓
LLM Structured Extraction
↓
Persisted Intelligence Run
```

```text
POST /api/opportunity-sources/{source_id}/analyze
GET  /api/intelligence-runs/{run_id}
GET  /api/opportunity-sources/{source_id}/intelligence-runs
```

`IntelligenceRun.status = succeeded` 只表示分析流水线完成，不表示 Opportunity 已验证。

明确边界：

```text
No Search
No Verification
No Provenance
```

详见 `docs/intelligence-contract.md`。

手工真实模型测试（pytest 不会调用）：

```bash
uv run python scripts/test_intelligence_llm.py
```

需要在 `.env` 中配置 `LLM_API_KEY`。不要把真实 Key 写入仓库。

## 内容接入 Pipeline

```text
URL / Text
↓
Content Ingestion
↓
Normalized Content
↓
OpportunitySource + IngestedContent
```

Ingestion 成功不代表内容可信或真实，也不代表已经对应某个 Opportunity。

日期解析时，若原文没有时区，按 UTC 解释；无法可靠解析则为空。

## 首次开发环境准备

需要 Python 3.12。如果本机没有，可以先安装：

```bash
uv python install 3.12
```

然后同步项目环境：

```bash
uv sync
```

Cursor / VS Code 可选择解释器：

```text
.venv\Scripts\python.exe
```

日常开发统一使用 `uv run`。

## 运行

```bash
uv run alembic upgrade head
uv run python scripts/seed_demo_enterprise.py
uv run python scripts/seed_demo_opportunities.py
uv run uvicorn app.main:app --reload
```

飞书入站需要**第二个进程**（不要挂在 FastAPI startup）：

```bash
uv run python -m app.integrations.feishu.subscribe_service_case_events
uv run python -m app.integrations.feishu.event_worker
```

然后访问：

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/api/content/ingest

## 数据库迁移

```bash
uv run alembic upgrade head
```

## Demo Seed

```bash
uv run python scripts/seed_demo_enterprise.py
uv run python scripts/seed_demo_opportunities.py
```

`seed_demo_enterprise.py` 同时写入 Demo User 与 owner Membership，可重复执行。

## Development Identity

`DEV_IDENTITY_ENABLED=true` 时，开发请求可用：

```http
X-Dev-User-Id: 2d7c1f4a-8b3e-4a91-9c2d-6e5f4a3b2c10
```

X-Dev-User-Id is for local/development integration only and is not a production authentication mechanism.

```bash
curl \
  -H "X-Dev-User-Id: 2d7c1f4a-8b3e-4a91-9c2d-6e5f4a3b2c10" \
  http://127.0.0.1:8000/api/me
```

`DEV_IDENTITY_ENABLED=false` 时该 Header 无效，`GET /api/me` 返回 `401 AUTHENTICATION_REQUIRED`。现有 ingest / analyze 等接口不要求此 Header。

## 测试

```bash
uv run pytest
```

测试使用内存 SQLite，并且不访问真实公网。pytest 不会请求飞书。

可选、非破坏性飞书连通性冒烟（官方 SDK 只读 OpenAPI，不创建或修改 Bitable 记录，不打印 token / APP_SECRET）：

```bash
uv run python -m app.integrations.feishu.smoke
uv run python -m app.integrations.feishu.smoke_bitable
```

`FEISHU_ENABLED=false` 时输出 `Feishu disabled`。没有真实 credential 不阻塞验收。

显式同步某个 ServiceCase（会创建或复用 Binding，可能写入 Bitable）：

```bash
uv run python -m app.integrations.feishu.sync_service_case <SERVICE_CASE_ID>
```

失败恢复 / 对账（一次性命令，无 durable queue）：

```bash
uv run python -m app.integrations.feishu.retry_service_case <SERVICE_CASE_ID>
uv run python -m app.integrations.feishu.retry_event_receipt <RECEIPT_ID>
uv run python -m app.integrations.feishu.retry_failed_syncs --direction all --limit 20
uv run python -m app.integrations.feishu.reconcile_service_case <SERVICE_CASE_ID>
```

开发用 WebSocket 连通性冒烟（不处理业务事件，Ctrl+C 停止）：

```bash
uv run python -m app.integrations.feishu.ws_smoke
```

飞书入站（独立进程，WARNING 日志，不打印 WS URL）：

```bash
uv run python -m app.integrations.feishu.subscribe_service_case_events
uv run python -m app.integrations.feishu.event_worker
```

不要打印 token。同一 Case 再跑一次不应新增第二条飞书记录。

## Feishu 配置

默认关闭。缺 credential 时 Backend 仍可启动，不会在 startup 请求 OpenAPI 或 WebSocket。

依赖固定：`lark-oapi==1.7.3`。不要随意升级；升级前必须跑完整 Feishu integration regression。SDK 是外部依赖，不要把 SDK 私有 API 当作本项目 Contract。

```text
OpenAPI Transport  = lark-oapi Client
Event Transport    = lark-oapi ws.Client
Business Integration = our Adapter / Binding / Sync Service
```

```text
FEISHU_ENABLED=false
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BASE_URL=https://open.feishu.cn
FEISHU_BITABLE_APP_TOKEN=
FEISHU_SERVICE_CASE_TABLE_ID=
FEISHU_SERVICE_CASE_STATUS_FIELD_ID=
FEISHU_REQUEST_TIMEOUT_SECONDS=10
FEISHU_SYNC_STALE_AFTER_SECONDS=300
```

`FEISHU_APP_SECRET` 是 Secret，使用 `SecretStr`。永不写入数据库、日志、API 响应或 Exception message。应用凭证与 `tenant_access_token` 生命周期由官方 SDK 管理，业务代码不接触 token。`FEISHU_BITABLE_APP_TOKEN` 是多维表格资源 ID，不是 APP_SECRET。`FEISHU_SYNC_STALE_AFTER_SECONDS` 只用于识别 stale pending Binding / stale received Receipt，默认 300。
