# 本机启动（两个进程）

飞书入站和业务 API **不是同一个进程**。开发时开两个终端，共用同一目录、同一 `.env`、同一 SQLite。

先进入项目：

```bash
cd D:\北辰产业云社区\筑脉企服后端
```

每次启动前升级数据库一次即可：

```bash
uv run alembic upgrade head
```

---

## 终端 A｜业务 API

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

负责：HTTP、Swagger、创建 ServiceCase、飞书出站同步。

成功标志：`Application startup complete`，访问 http://127.0.0.1:8000/docs

`--reload` 只热重载这个进程。改代码后 **不会** 自动重启终端 B。

---

## 终端 B｜飞书 Event Worker

仅在 `.env` 里 `FEISHU_ENABLED=true` 且 Bitable / 办理状态 field_id 已配好时需要。

第一次（或权限/订阅变更后）订阅一次：

```bash
uv run python -m app.integrations.feishu.subscribe_service_case_events
```

然后常驻：

```bash
uv run python -m app.integrations.feishu.event_worker
```

负责：飞书长连接，把表格「办理状态」变更写入 Backend。

成功标志：`Feishu event worker starting`。改飞书状态后应出现 `Feishu event received` 等业务日志。

FastAPI **不会**自动拉起这个进程。关掉它，入站同步就停。

---

## 对照

| | 终端 A | 终端 B |
|---|---|---|
| 命令 | `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` | `python -m app.integrations.feishu.event_worker` |
| 作用 | API + 出站（Case → 飞书） | 入站（飞书 → Case） |
| 停掉 | Ctrl+C | Ctrl+C |

两个都要开，飞书双向同步才完整。只开 A：能创建 Case、能写出站；飞书里改状态不会回写 Backend。
