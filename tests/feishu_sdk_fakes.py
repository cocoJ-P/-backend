"""Fake lark-oapi Bitable client for unit tests. No network."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable


class FakeSdkRecord:
    def __init__(self, record_id: str, fields: dict | None = None) -> None:
        self.record_id = record_id
        self.fields = fields or {}


class FakeSdkResponse:
    def __init__(
        self,
        *,
        code: int = 0,
        msg: str = "ok",
        record: FakeSdkRecord | None = None,
        items: list[FakeSdkRecord] | None = None,
        log_id: str | None = None,
        field_items: list[object] | None = None,
        has_more: bool = False,
        page_token: str | None = None,
    ) -> None:
        self.code = code
        self.msg = msg
        self.data = SimpleNamespace(
            record=record,
            items=items,
            has_more=has_more,
            page_token=page_token,
        )
        if field_items is not None:
            self.data.items = field_items
        self._log_id = log_id

    def success(self) -> bool:
        return self.code == 0

    def get_log_id(self) -> str | None:
        return self._log_id


SdkHandler = Callable[[str, Any], FakeSdkResponse | Any]


class FakeRecordApi:
    def __init__(self, handler: SdkHandler, calls: list[tuple[str, Any]]) -> None:
        self._handler = handler
        self.calls = calls

    def create(self, request: Any) -> Any:
        return self._invoke("create", request)

    def get(self, request: Any) -> Any:
        return self._invoke("get", request)

    def update(self, request: Any) -> Any:
        return self._invoke("update", request)

    def search(self, request: Any) -> Any:
        return self._invoke("search", request)

    def list(self, request: Any) -> Any:
        return self._invoke("list_fields", request)

    def _invoke(self, operation: str, request: Any) -> Any:
        self.calls.append((operation, request))
        return self._handler(operation, request)


def make_fake_sdk(handler: SdkHandler) -> tuple[SimpleNamespace, list[tuple[str, Any]]]:
    calls: list[tuple[str, Any]] = []
    record_api = FakeRecordApi(handler, calls)
    field_api = FakeRecordApi(handler, calls)
    sdk = SimpleNamespace(
        bitable=SimpleNamespace(
            v1=SimpleNamespace(
                app_table_record=record_api,
                app_table_field=field_api,
            )
        )
    )
    return sdk, calls
