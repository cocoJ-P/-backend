# 接口一览

Base: `http://127.0.0.1:8000`

| 模块 | 方法 | 路径 |
|---|---|---|
| Health | GET | `/api/health` |
| Enterprises | GET | `/api/enterprises` |
| Enterprises | POST | `/api/enterprises` |
| Enterprises | GET | `/api/enterprises/{enterprise_id}` |
| Enterprises | GET | `/api/enterprises/{enterprise_id}/state` |
| Enterprises | POST | `/api/enterprises/{enterprise_id}/states` |
| Opportunities | GET | `/api/opportunities` |
| Opportunities | POST | `/api/opportunities` |
| Opportunities | GET | `/api/opportunities/{opportunity_id}` |
| Opportunities | GET | `/api/opportunities/{opportunity_id}/sources` |
| Opportunities | POST | `/api/opportunities/{opportunity_id}/sources` |
| Opportunities | POST | `/api/opportunity-sources` |
| Opportunities | GET | `/api/opportunities/{opportunity_id}/requirements` |
| Opportunities | POST | `/api/opportunities/{opportunity_id}/requirements` |
| Content | POST | `/api/content/ingest` |
| Intelligence | POST | `/api/opportunity-sources/{source_id}/analyze` |
| Intelligence | GET | `/api/intelligence-runs/{run_id}` |
| Intelligence | GET | `/api/opportunity-sources/{source_id}/intelligence-runs` |
| Identity | GET | `/api/me` |
| User Submissions | POST | `/api/user-submissions` |
| User Submissions | POST | `/api/user-submissions/{submission_id}/process` |
| User Submissions | POST | `/api/user-submissions/{submission_id}/service-case` |
| User Submissions | GET | `/api/user-submissions` |
| User Submissions | GET | `/api/user-submissions/mine` |
| User Submissions | GET | `/api/user-submissions/{submission_id}` |
| Discoveries | POST | `/api/discoveries` |
| Discoveries | GET | `/api/discoveries` |
| Discoveries | GET | `/api/discoveries/{discovery_id}` |
| Discoveries | POST | `/api/discoveries/{discovery_id}/withdraw` |
| Discoveries | POST | `/api/discoveries/{discovery_id}/accept` |
| Discoveries | GET | `/api/discoveries/feed` |
| Discoveries | GET | `/api/discoveries/saved` |
| Discoveries | POST | `/api/discoveries/{discovery_id}/seen` |
| Discoveries | GET | `/api/discoveries/{discovery_id}/user-state` |
| Discoveries | PATCH | `/api/discoveries/{discovery_id}/user-state` |
| Discovery User States | GET | `/api/discovery-user-states` |
| Service Cases | GET | `/api/service-cases` |
| Service Cases | GET | `/api/service-cases/mine` |
| Service Cases | GET | `/api/service-cases/{service_case_id}` |

D6.4 Feishu Adapter 没有公开 HTTP 接口。不要新增 `/api/feishu/*`。

