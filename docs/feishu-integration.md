# Feishu Integration

飞书是外部协作执行载体，不是业务 Domain。

```text
ServiceCase = 业务事实
ServiceCaseFeishuBinding = 外部集成绑定事实
Feishu Bitable = 后续执行载体
```

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

FastAPI BackgroundTask 不是 durable queue。进程在 task 执行前崩溃时，`pending` Binding 仍在数据库，D6.7 再做可靠恢复 / Retry Endpoint。当前 0 automatic HTTP retry。

## 字段映射

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
- 不新增公开 API：`/api/feishu/*`、Retry Endpoint
- 不做 Feishu → Backend / Webhook（D6.6）
- 不修改 Mini Program / Service Frontend 展示同步状态

## 配置

统一走 `app.core.config.Settings`，默认关闭。

| 变量 | 默认 | 说明 |
|---|---|---|
| `FEISHU_ENABLED` | `false` | 关闭时不访问飞书，不要求 credential |
| `FEISHU_APP_ID` | 空 | Internal App ID |
| `FEISHU_APP_SECRET` | 空 | SecretStr，永不落库 / 日志 / API |
| `FEISHU_BASE_URL` | `https://open.feishu.cn` | Open API Base URL |
| `FEISHU_BITABLE_APP_TOKEN` | 空 | 多维表格 app_token，是资源 ID，不是 secret |
| `FEISHU_SERVICE_CASE_TABLE_ID` | 空 | 服务事项表 table_id |
| `FEISHU_REQUEST_TIMEOUT_SECONDS` | `10` | HTTP timeout |

永不存储：`FEISHU_APP_SECRET`、`tenant_access_token`。

## Token / HTTP Client

`FeishuTenantTokenProvider` 进程内存缓存 token，提前 60 秒刷新，`threading.Lock`。所有飞书 HTTP 经过 `app/integrations/feishu/`。HTTP 200 且业务 `code != 0` 仍视为失败。

## 错误码

| code | retryable | 来源 |
|---|---|---|
| `FEISHU_NOT_CONFIGURED` | false | HTTP / config |
| `FEISHU_AUTH_FAILED` | false | HTTP |
| `FEISHU_REQUEST_FAILED` | false | HTTP |
| `FEISHU_RATE_LIMITED` | true | HTTP |
| `FEISHU_TIMEOUT` | true | HTTP |
| `FEISHU_NETWORK_ERROR` | true | HTTP |
| `FEISHU_INVALID_RESPONSE` | false | HTTP |
| `FEISHU_DUPLICATE_CASE_RECORDS` | false | Sync orchestration |
| `FEISHU_RECORD_NOT_FOUND` | false | Sync / Bitable get |
| `FEISHU_MAPPING_FAILED` | false | Mapper / Sync |

D6.5 只标识 retryable，不自动重试。

## Bitable

- `create_record(fields)`
- `get_record(record_id)`
- `update_record(record_id, fields)`
- `search_records(filter=...)`（generic，不硬编码 Case ID）

## Binding

表 `service_case_feishu_bindings`：UNIQUE(`service_case_id`)；UNIQUE(`bitable_app_token`, `table_id`, `record_id`)；FK CASCADE。创建时 snapshot app_token / table_id。

## 冒烟

```bash
uv run python -m app.integrations.feishu.smoke
uv run python -m app.integrations.feishu.sync_service_case <SERVICE_CASE_ID>
```

token smoke 不写 Bitable。outbound CLI 会写记录，同一 Case 再跑必须幂等。
