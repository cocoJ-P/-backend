# 如何启动筑脉企服后端

日常开发两个进程怎么开，见 **[start.md](./start.md)**。

本文说明本机如何启动「筑脉企服统一后端」。日常命令一律用 `uv run`，不要用系统 `pip` / 全局 Python。

## 1. 环境要求

- Windows 10/11
- Python 3.12
- [uv](https://docs.astral.sh/uv/)

如果本机还没有 Python 3.12：

```bash
uv python install 3.12
```

如果 PowerShell 里输入 `uv` 提示找不到命令，先确认 uv 已安装，或使用完整路径：

```text
C:\Users\<你的用户名>\.local\bin\uv.exe
```

也可把该目录加入系统 PATH。

## 2. 进入项目目录

```bash
cd D:\北辰产业云社区\筑脉企服后端
```

## 3. 第一次准备（只需做一次）

复制环境变量模板（如果还没有 `.env`）：

```bash
copy .env.example .env
```

然后安装依赖：

```bash
uv sync
```

Cursor / VS Code 解释器选择：

```text
.venv\Scripts\python.exe
```

当前默认使用本地 SQLite：

```text
data/zumaix_enterprise_service.db
```

**不要**把真实 `LLM_API_KEY` 或 `FEISHU_APP_SECRET` 提交进 Git。`.env` 已在 `.gitignore` 中。

## 4. 启动后端

每次启动前先升级数据库，再跑服务：

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

`--reload` 表示改代码后自动重启，适合开发。

启动成功后，终端会出现类似：

```text
Application startup complete
Uvicorn running on http://127.0.0.1:8000
```

## 5. 访问地址

| 用途 | 地址 |
|---|---|
| 服务根路径 | http://127.0.0.1:8000 |
| Swagger 文档 | http://127.0.0.1:8000/docs |
| 健康检查 | http://127.0.0.1:8000/api/health |
| 内容接入 | http://127.0.0.1:8000/api/content/ingest |

健康检查正常时返回：

```json
{
  "status": "ok",
  "service": "筑脉企服 Backend",
  "environment": "development",
  "database": "ok"
}
```

## 6. 可选：写入 Demo 数据

如果要在 Swagger 里看到示例企业和机会：

```bash
uv run python scripts/seed_demo_enterprise.py
uv run python scripts/seed_demo_opportunities.py
```

`seed_demo_enterprise.py` 会同时写入 Demo User 和 owner Membership。这两个脚本不是启动所必需。空库也可以先启动，再用 `POST /api/content/ingest` 接入文本。

开发身份（仅本地）：

```bash
curl -H "X-Dev-User-Id: 2d7c1f4a-8b3e-4a91-9c2d-6e5f4a3b2c10" http://127.0.0.1:8000/api/me
```

`X-Dev-User-Id` 只用于本地/开发联调，不是生产认证机制。`DEV_IDENTITY_ENABLED=false` 时该 Header 无效。

## 7. 可选：接入真实 LLM

不配置 `LLM_API_KEY` 时：

- 后端**可以正常启动**
- 企业 / 机会 / 内容接入 API 可用
- `POST /api/opportunity-sources/{source_id}/analyze` 会返回 `503 LLM_NOT_CONFIGURED`

若要在本机真正跑内容分析，编辑 `.env`：

```text
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=你的密钥
LLM_BASE_URL=
```

如果用 DeepSeek 等 OpenAI 兼容接口，再填写对应的 `LLM_BASE_URL` 和模型名。

手工冒烟（pytest 不会跑这条）：

```bash
uv run python scripts/test_intelligence_llm.py
```

## 8. 可选：飞书（默认关闭）

`FEISHU_ENABLED=false` 时：

- 后端**可以正常启动**
- D0–D6.7 功能不受影响
- 不会在 startup 请求飞书 OpenAPI 或启动 WebSocket
- Adapter 被调用时返回 `FEISHU_NOT_CONFIGURED`

不要把真实 `FEISHU_APP_SECRET` 写入仓库。应用凭证与 token 由官方 SDK（`lark-oapi==1.7.3`）管理，业务代码不接触 token。

可选、非破坏性连通性冒烟（官方 SDK 只读调用，不创建/更新/删除 Bitable 记录，不打印 token）：

```bash
uv run python -m app.integrations.feishu.smoke
uv run python -m app.integrations.feishu.smoke_bitable
```

显式同步某个 ServiceCase（可能写入多维表格）：

```bash
uv run python -m app.integrations.feishu.sync_service_case <SERVICE_CASE_ID>
```

失败恢复 / 对账（一次性命令，无 Celery / Redis / Kafka）：

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

飞书入站是**第二个进程**，与 API Server 解耦：

```bash
uv run python -m app.integrations.feishu.subscribe_service_case_events
uv run python -m app.integrations.feishu.event_worker
```

开放平台需人工：长连接接收事件，并订阅 `drive.file.bitable_record_changed_v1`。`FEISHU_SERVICE_CASE_STATUS_FIELD_ID` 来自 `list_fields` 的「办理状态」。

详见 `docs/feishu-integration.md`。

## 9. 常用 API（启动后）

1. 接入一段文本：`POST /api/content/ingest`
2. 用返回的 `source.id` 做分析：`POST /api/opportunity-sources/{source_id}/analyze`
3. 查看某次运行：`GET /api/intelligence-runs/{run_id}`
4. 看来源分析历史：`GET /api/opportunity-sources/{source_id}/intelligence-runs`

分析成功只表示流水线跑完，不代表机会已经过真实性验证。

## 10. 停止服务

在运行 `uvicorn` 的终端里按 `Ctrl + C`。

## 11. 常见问题

**端口被占用**

说明 `8000` 上已经有服务。关掉旧的 uvicorn，或改端口：

```bash
uv run uvicorn app.main:app --reload --port 8001
```

**`uv` 不是内部或外部命令**

使用完整路径调用 uv，或把 `C:\Users\<用户名>\.local\bin` 加入 PATH。

**数据库不是最新**

```bash
uv run alembic upgrade head
```

**健康检查 database 不是 ok**

确认 `.env` 里的 `DATABASE_URL` 正确，且 `data/` 目录可写。

**想确认测试是否通过**

```bash
uv run pytest
```

测试使用内存 SQLite，不会改本机 `data/zumaix_enterprise_service.db`，也不会调用真实 LLM / 飞书 / 公网。
