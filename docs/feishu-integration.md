# Feishu Integration Foundation (D6.4)

飞书是外部协作执行载体，不是业务 Domain。本阶段只建立 Integration Foundation，不做 ServiceCase 自动同步。

```text
ServiceCase = 业务事实
ServiceCaseFeishuBinding = 外部集成绑定事实
Feishu Bitable = 后续执行载体
```

未来关系：

```text
ServiceCase
    │
    │ D6.5
    ▼
Feishu Adapter
    │
    ▼
Feishu Bitable Record
    │
    ▼
ServiceCaseFeishuBinding
```

D6.4 只准备：

- `FeishuTenantTokenProvider`
- `FeishuClient`
- `FeishuBitableAdapter`
- `ServiceCaseFeishuBinding`

不把现有 ServiceCase 发送到飞书，不扫描历史数据，不在 startup 连接飞书，不在 ServiceCase 创建时建立 Binding。

## 边界

- 不新增 `app/domains/feishu/`
- 不把 `feishu_record_id` / `feishu_table_id` / `feishu_url` / `sync_status` / `last_synced_at` 写入 `service_cases`
- 不新增公开 API：`/api/feishu/*`、`/api/service-cases/{id}/feishu`
- 不修改 ServiceCase API Contract
- 第一版只使用一套筑脉企服服务侧 Feishu Internal App，没有多租户 OAuth
- 不自动 Retry（标识 `retryable` 即可，Retry Policy 留到 D6.7）

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

`FEISHU_ENABLED=false` 时 Backend 正常启动。`FEISHU_ENABLED=true` 但缺 APP_ID / APP_SECRET / BITABLE_APP_TOKEN / TABLE_ID 时，Adapter 被调用返回 `FEISHU_NOT_CONFIGURED`，不会导致 FastAPI 无法启动。

永不存储：

- `FEISHU_APP_SECRET`
- `tenant_access_token`

## Token

`FeishuTenantTokenProvider` 用 APP_ID + APP_SECRET 换取 `tenant_access_token`。

- 进程内内存缓存：`token` + `expires_at`
- 提前 60 秒视为不可用
- `threading.Lock` 避免并发重复刷新
- 不使用 Redis / 数据库缓存
- 不在 Binding 表中保存 token

## HTTP Client

所有飞书 HTTP 必须经过 `app/integrations/feishu/`。`FeishuClient` 自动加 `Authorization: Bearer <tenant_access_token>`（token 获取请求除外）。

不能只判断 HTTP 状态：飞书可能 HTTP 200 但业务 `code != 0`。超时、网络、限流、非法响应统一转成 `FeishuIntegrationError`。

## 错误码

| code | retryable |
|---|---|
| `FEISHU_NOT_CONFIGURED` | false |
| `FEISHU_AUTH_FAILED` | false |
| `FEISHU_REQUEST_FAILED` | false |
| `FEISHU_RATE_LIMITED` | true |
| `FEISHU_TIMEOUT` | true |
| `FEISHU_NETWORK_ERROR` | true |
| `FEISHU_INVALID_RESPONSE` | false |

真实飞书错误码可保存在 `provider_code`。不持久化完整 raw body。

## Bitable

`FeishuBitableAdapter` 只提供通用：

- `create_record(fields)`
- `get_record(record_id)`
- `update_record(record_id, fields)`

输入是 generic field mapping。ServiceCase → 飞书字段映射属于 D6.5。

## Binding

表 `service_case_feishu_bindings`：

- `UNIQUE(service_case_id)`：一个 ServiceCase 一个 Binding
- `UNIQUE(bitable_app_token, table_id, record_id)`：一个飞书 Record 不被两个 Binding 占用；`record_id` 允许 NULL
- FK `service_case_id → service_cases.id` ON DELETE CASCADE
- 创建 Binding 时 snapshot `bitable_app_token` / `table_id`

`sync_status`：

- `pending`：已建立 Binding，等待或正在同步
- `synced`：已成功绑定一个飞书 Record
- `failed`：最近一次同步失败

没有 Binding 行表示尚未进入飞书同步，因此没有 `not_synced`。当前没有 worker，因此没有 `syncing`。

`mark_synced` 写入 `record_id`、`last_synced_at`，清空 error fields。`mark_failed` 保存安全的 error code/message；已有 `record_id` 不清空。

D6.4 运行时不会创建真实 Binding 行。Repository / Service 只供后续 D6.5 使用。

## 冒烟

```bash
uv run python -m app.integrations.feishu.smoke
```

只测试 tenant_access_token。成功输出 `Feishu connection OK`。不打印 token。没有真实 credential 时不算验收失败。
