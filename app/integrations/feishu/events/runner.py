"""Blocking WebSocket runner. Not started from FastAPI lifespan."""

from __future__ import annotations

import lark_oapi as lark


def start_feishu_ws_client(client: lark.ws.Client) -> None:
    client.start()
