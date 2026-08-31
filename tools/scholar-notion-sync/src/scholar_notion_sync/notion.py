from __future__ import annotations

from datetime import datetime
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST", "PATCH"),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class NotionClient:
    base_url = "https://api.notion.com/v1"

    def __init__(self, token: str, session: requests.Session | None = None):
        self.session = session or _session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(method, f"{self.base_url}{path}", timeout=45, **kwargs)
        response.raise_for_status()
        return response.json()

    def query_all(self, data_source_id: str, body: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = dict(body or {})
        results: list[dict[str, Any]] = []
        while True:
            data = self._request("POST", f"/data_sources/{data_source_id}/query", json=payload)
            results.extend(data.get("results") or [])
            if not data.get("has_more"):
                return results
            payload["start_cursor"] = data["next_cursor"]

    def latest_total_snapshot(self, data_source_id: str) -> dict[str, Any] | None:
        rows = self.query_all(
            data_source_id,
            {
                "filter": {"property": "类型", "select": {"equals": "总引用"}},
                "sorts": [{"property": "快照时间", "direction": "descending"}],
                "page_size": 1,
            },
        )
        return rows[0] if rows else None

    def create_page(self, data_source_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/pages",
            json={"parent": {"type": "data_source_id", "data_source_id": data_source_id}, "properties": properties},
        )

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/pages/{page_id}", json={"properties": properties})


def plain_text(prop: dict[str, Any]) -> str:
    values = prop.get("rich_text") or prop.get("title") or []
    return "".join(item.get("plain_text", "") for item in values)


def number(prop: dict[str, Any]) -> int:
    return int(prop.get("number") or 0)


def date_value(prop: dict[str, Any]) -> datetime | None:
    start = (prop.get("date") or {}).get("start")
    if not start:
        return None
    return datetime.fromisoformat(start.replace("Z", "+00:00"))


def title(value: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value[:2000]}}]}


def rich_text(value: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]}


def date(value: datetime) -> dict[str, Any]:
    return {"date": {"start": value.isoformat()}}


def relation(page_id: str) -> dict[str, Any]:
    return {"relation": [{"id": page_id}]}

