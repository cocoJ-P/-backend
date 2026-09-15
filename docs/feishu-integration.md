# Feishu Integration

飞书是外部协作执行载体，不是业务 Domain。

```text
ServiceCase = 业务事实
ServiceCaseFeishuBinding = 外部集成绑定事实
Feishu Bitable = 后续执行载体
```

## 架构

```text
ServiceCase Domain
        │
        ▼
ServiceCaseFeishuSyncService
        │
        ▼
FeishuBitableAdapter
        │
        ▼
Official lark.Client   (lark-oapi==1.7.3)
        │
        ▼
Feishu OpenAPI
```

```text
OpenAPI Transport      = lark-oapi Client
Event Transport        = lark-oapi ws.Client
Business Integration   = our Adapter / Binding / Sync Service
```

依赖固定：`lark-oapi==1.7.3`。不要使用浮动 latest，不要引入 `lark-channel-sdk`。升级 SDK 前必须跑完整 Feishu integration regression。SDK 是外部依赖；不要把 SDK 私有 API 当作本项目 Contract。

应用凭证与 token 生命周期由官方 SDK 管理。业务代码 / Adapter 不获取、不缓存、不注入 `tenant_access_token`。

D6.5.1 提供 WebSocket factory / runner，**不**在 FastAPI startup 启动长连接。D6.6 用独立进程 `event_worker` 消费 `drive.file.bitable_record_changed_v1`。

## D6.5 Outbound Sync

```text
UserSubmission succeeded
↓
POST /api/user-submissions/{id}/service-case
↓
COMMIT ServiceCase(open)
↓
若 created=true 且 FEISHU_ENABLED=true
    Binding(pending) COMMIT
    FastAPI BackgroundTask(service_case_id)
        独立 DB Session
        Case ID 对账 / create_record
        Binding synced | failed
↓
立即返回 ServiceCase API（不依赖飞书成功）
```

失败语义：

```text
Feishu failed ≠ ServiceCase failed
Binding failed = Integration problem
```

ServiceCase.status 仍是 `open / in_progress / completed / closed`。Binding.sync_status 是 `pending / synced / failed`。同步成功不会把 Case 改成 `in_progress`。

`FEISHU_ENABLED=false` 时不创建 Binding、不 enqueue、不访问飞书。重复点击「继续办理」（`created=false`）不会自动重试飞书。历史 Case 不会 startup 扫描；需要人工：

```bash
uv run python -m app.integrations.feishu.sync_service_case <SERVICE_CASE_ID>
```

CLI 只输出 ServiceCase ID、Binding 状态、Record ID。不输出 APP_SECRET / token / Authorization。

## BackgroundTask 限制

FastAPI BackgroundTask 不是 durable queue。进程在 task 执行前崩溃时，`pending` Binding 仍在数据库。D6.7 用一次性 CLI 恢复：

```bash
uv run python -m app.integrations.feishu.retry_failed_syncs --direction all --limit 50
```

没有 Celery / Redis / Kafka / APScheduler。未来可用外部 cron 调用同一命令。当前 0 automatic HTTP retry。官方 SDK OpenAPI transport 对 Bitable mutating call 也没有自动 retry。

## 字段映射

当前真实表使用字段名（D6.5.1 不改成 field_id）。日期列现场名是「创建时间」（field_id `fldS6Y04Nn`），与部分文档草稿中的「创建日期」不同；Outbound 以现场 `list_fields` 为准。

| 飞书字段 | Backend 来源 |
|---|---|
| 服务事项 | `ServiceCase.title` |
| Case ID | `str(ServiceCase.id)` |
| 企业 | `Enterprise.name` |
| 发起用户 | `User.display_name` |
| 来源 | `user_input→用户提交`，`discovery→来自发现` |
| 办理状态 | `open→待服务`，`in_progress→处理中`，`completed→已完成`，`closed→已关闭` |
| 创建时间 | `ServiceCase.created_at`，Bitable DateTime 毫秒时间戳 |
| Submission ID | `str(UserSubmission.id)` |

办理状态 field_id 留给 D6.6 Inbound。

## 幂等

创建飞书 Record 前，若 Binding.record_id 为空，先按 Case ID 查询：

- 0 条：create_record
- 1 条：mark_synced，不再 create
- >1 条：Binding failed，`FEISHU_DUPLICATE_CASE_RECORDS`

create timeout / network 后再查一次 Case ID：找到 1 条视为成功；仍为 0 则 failed，不第二次 create。

已 synced 且有 record_id：直接返回。Binding 已有 record_id 时 get_record 确认；远端不存在则 failed，不自动重建。

## 边界

- 不新增 `app/domains/feishu/`
- 不把飞书字段写入 `service_cases`
- 不新增公开 API：`/api/feishu/*`、Retry Endpoint、Webhook callback
- 不修改 Mini Program / Service Frontend 展示同步状态
- 不自建 tenant token cache，不自建 Authorization Header
- 不因 Inbound 状态变化再次 Outbound（禁止循环）

## 配置

统一走 `app.core.config.Settings`，默认关闭。

| 变量 | 默认 | 说明 |
|---|---|---|
| `FEISHU_ENABLED` | `false` | 关闭时不访问飞书，不要求 credential |
| `FEISHU_APP_ID` | 空 | Internal App ID |
| `FEISHU_APP_SECRET` | 空 | SecretStr，永不落库 / 日志 / API |
| `FEISHU_BASE_URL` | `https://open.feishu.cn` | Open API / SDK domain |
| `FEISHU_BITABLE_APP_TOKEN` | 空 | 多维表格 app_token，是资源 ID，不是 secret |
| `FEISHU_SERVICE_CASE_TABLE_ID` | 空 | 服务事项表 table_id |
| `FEISHU_SERVICE_CASE_STATUS_FIELD_ID` | 空 | 「办理状态」field_id，Inbound 过滤用；不是 Secret |
| `FEISHU_REQUEST_TIMEOUT_SECONDS` | `10` | 接入 SDK Client Builder `timeout`（秒） |
| `FEISHU_SYNC_STALE_AFTER_SECONDS` | `300` | stale pending Binding / stale received Receipt 阈值 |

永不存储：`FEISHU_APP_SECRET`、`tenant_access_token`。SDK 日志级别为 WARNING，不是 DEBUG。

## Token / Transport

`create_feishu_sdk_client()` 构造可复用的 `lark.Client`（factory + process-local cache）。SDK 负责应用凭证和 token 生命周期。Adapter 只调用 `client.bitable.v1...`。

业务层只看到：

- `FeishuBitableRecord`
- `FeishuIntegrationError`

不会看到 `CreateAppTableRecordResponse` 等 SDK raw model，也不 `except LarkException`。

SDK `response.success() == false` / SDK exception / network exception 统一映射到现有错误码；`provider_code = response.code`，可安全记录 `msg` 与 `log_id`。不记录 SDK raw response。

## 错误码

| code | retryable | 来源 |
|---|---|---|
| `FEISHU_NOT_CONFIGURED` | false | config |
| `FEISHU_AUTH_FAILED` | false | SDK / provider |
| `FEISHU_REQUEST_FAILED` | false | SDK / provider |
| `FEISHU_RATE_LIMITED` | true | SDK / provider |
| `FEISHU_TIMEOUT` | true | `requests.Timeout` |
| `FEISHU_NETWORK_ERROR` | true | `requests.ConnectionError` |
| `FEISHU_INVALID_RESPONSE` | false | SDK unmarshal / missing record_id |
| `FEISHU_DUPLICATE_CASE_RECORDS` | false | Sync orchestration |
| `FEISHU_RECORD_NOT_FOUND` | false | Sync / Bitable get |
| `FEISHU_MAPPING_FAILED` | false | Mapper / Sync |
| `FEISHU_UNSUPPORTED_SERVICE_CASE_STATUS` | false | Inbound 未知办理状态 |
| `FEISHU_BINDING_RECORD_MISMATCH` | false | Binding.record_id 指向别的 Case ID |
| `FEISHU_EVENT_PARSE_FAILED` | false | Inbound 事件解析 |

D6.5 / D6.6 只标识 retryable，不自动重试。D6.7 对 retryable 失败和 stale pending/received 提供显式单条 Retry 与一次性 Batch CLI。非法 Domain 迁移使用 `INVALID_SERVICE_CASE_TRANSITION`（Receipt=failed，Case 不变，retryable=false，不进自动 Batch）。

## Binding

表 `service_case_feishu_bindings`：UNIQUE(`service_case_id`)；UNIQUE(`bitable_app_token`, `table_id`, `record_id`)；FK CASCADE。创建时 snapshot app_token / table_id。Inbound 成功**不**改 `sync_status` / `last_synced_at`。

Retry metadata：`retry_count`（默认 0）、`last_retry_at`、`last_error_retryable`。`sync_status` 仍只有 `pending / synced / failed`。成功 synced 后清空 `last_error_code` / `last_error_message`，并把 `last_error_retryable=false`。普通 D6.5 初次同步不增加 `retry_count`。

## Bitable

Public Integration Interface 不变：

- `create_record(fields)` → Bitable v1 AppTableRecord create
- `get_record(record_id)` → Bitable v1 AppTableRecord get
- `update_record(record_id, fields)` → Bitable v1 AppTableRecord update
- `search_records(filter=...)` → Bitable v1 AppTableRecord search（filter 在 request body；page_size 是 query）

`search_records` 仍是 generic，不硬编码 Case ID。Outbound 对账传入 Case ID filter。

## D6.6 Inbound Status Sync

```text
飞书多维表格「办理状态」编辑
↓
drive.file.bitable_record_changed_v1
↓
独立进程 event_worker（lark.ws.Client）
↓
EventDispatcherHandler typed register
↓
FeishuEventReceipt UNIQUE(event_id)
↓
record_id → Binding → ServiceCase
↓
get_record() 读取当前办理状态
↓
transition_service_case_status()
```

两个进程：

```text
Terminal A: uv run uvicorn app.main:app --reload     # 业务 API
Terminal B: uv run python -m app.integrations.feishu.event_worker  # 长连接
```

共用同一本地 DB 与 Settings。FastAPI startup **不会**启动 WebSocket。

人工飞书开放平台：

1. 事件与回调 → 使用长连接接收事件
2. 添加 `drive.file.bitable_record_changed_v1`（多维表格记录变更）
3. 若权限/事件变更需要发布，完成发布
4. 配置 `FEISHU_SERVICE_CASE_STATUS_FIELD_ID`（`uv run python -m app.integrations.feishu.list_fields` 中「办理状态」）
5. `uv run python -m app.integrations.feishu.subscribe_service_case_events`
6. 启动 `event_worker`

一致性：

```text
Feishu status edit → Domain transition
Domain rule wins
非法飞书操作不会修改 Backend
D6.6 不自动把飞书值改回去
```

事件只是变化提示。当前办理状态以 `get_record()` 为准，不直接信 after_value。只处理 `record_edited`；`record_added` / `record_deleted` ignored。找不到 Binding → ignored（`FEISHU_UNMANAGED_RECORD`）。重复 `event_id` 不处理。`failed` 可被 D6.7 显式 Retry；processed / ignored 不重试。

反向映射：待服务→open，处理中→in_progress，已完成→completed，已关闭→closed。

## D6.7 Sync Failure & Retry

Retry 是重新执行失败 / 中断的同步。Reconciliation 是比较 Backend ↔ Binding ↔ Feishu Record 后修复结构或状态漂移。

Authority：

```text
Normal inbound (D6.6):
Feishu 人工改办理状态 → ServiceCase Domain transition

Reconciliation (D6.7):
ServiceCase → repair Feishu
Backend wins
```

Reconciliation **不会**用异常远端状态改 Domain，也不会自动补 `open→in_progress→completed`。

Outbound retry 禁止直接 `create_record()`。必须先 get / Case ID search：

- `record_id` 存在且 Case ID 匹配 → `update_record` 回到 Backend snapshot
- Case ID 不匹配 → `FEISHU_BINDING_RECORD_MISMATCH`，不写远端
- record 不存在或 `record_id` 为空 → Case ID search：0 create / 1 adopt / >1 duplicate
- 旧 record 确认不存在且 search=0 才 recreate

Inbound receipt retry 不依赖 raw event payload。按 Receipt 的 `app_token / table_id / record_id` 重新 `get_record()`，以**当前**飞书状态为输入。

自动 Batch 只选：

- outbound：`failed AND last_error_retryable=true`，以及 stale pending
- inbound：`failed AND retryable=true`，以及 stale received

`processed` / `ignored` / non-retryable failed 不进 Batch。顺序处理，有 `limit`，oldest first，单项失败不终止。

EventReceipt retry metadata：`retry_count`、`last_retry_at`、`retryable`。

运维命令：

```bash
uv run python -m app.integrations.feishu.retry_service_case <SERVICE_CASE_ID>
uv run python -m app.integrations.feishu.retry_event_receipt <RECEIPT_ID>
uv run python -m app.integrations.feishu.retry_failed_syncs --direction outbound|inbound|all --limit 50
uv run python -m app.integrations.feishu.reconcile_service_case <SERVICE_CASE_ID>
uv run python -m app.integrations.feishu.reconcile_service_cases --limit 50
```

`reconcile_service_cases` 只检查已有 Binding，不做历史无限 backfill。不新增公开 Retry API。

## 冒烟

```bash
uv run python -m app.integrations.feishu.smoke
uv run python -m app.integrations.feishu.smoke_bitable
uv run python -m app.integrations.feishu.list_fields
uv run python -m app.integrations.feishu.subscribe_service_case_events
uv run python -m app.integrations.feishu.sync_service_case <SERVICE_CASE_ID>
uv run python -m app.integrations.feishu.retry_service_case <SERVICE_CASE_ID>
uv run python -m app.integrations.feishu.retry_event_receipt <RECEIPT_ID>
uv run python -m app.integrations.feishu.retry_failed_syncs --direction all --limit 20
uv run python -m app.integrations.feishu.reconcile_service_case <SERVICE_CASE_ID>
uv run python -m app.integrations.feishu.ws_smoke
uv run python -m app.integrations.feishu.event_worker
```

`smoke` / `smoke_bitable` / `list_fields` 只读，不创建记录。outbound CLI 会写记录，同一 Case 再跑必须幂等。`event_worker` 默认 SDK WARNING，自己只打印 `Feishu event worker starting`。
