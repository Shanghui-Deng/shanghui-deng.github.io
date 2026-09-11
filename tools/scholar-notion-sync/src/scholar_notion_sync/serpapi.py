from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Article, ScholarProfile


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class SerpApiClient:
    endpoint = "https://serpapi.com/search.json"

    def __init__(self, api_key: str, session: requests.Session | None = None):
        self.api_key = api_key
        self.session = session or _session()

    def fetch_profile(self, author_id: str) -> ScholarProfile:
        articles: dict[str, Article] = {}
        total_citations: int | None = None
        metrics: dict[str, Any] | None = None
        start = 0

        while True:
            response = self.session.get(
                self.endpoint,
                params={
                    "engine": "google_scholar_author",
                    "author_id": author_id,
                    "hl": "en",
                    "sort": "pubdate",
                    "num": 100,
                    "start": start,
                    "api_key": self.api_key,
                },
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(f"SerpAPI error: {payload['error']}")

            if total_citations is None:
                total_citations = self._total_citations(payload)
                metrics = self._citation_metrics(payload)

            page = payload.get("articles") or []
            for raw in page:
                article = self._article(raw, author_id)
                articles[article.citation_id] = article

            if len(page) < 100:
                break
            start += 100

        if total_citations is None:
            raise RuntimeError("SerpAPI response did not contain a citation total")
        metrics = metrics or {}
        return ScholarProfile(
            total_citations=total_citations,
            articles=list(articles.values()),
            citations_since=metrics.get("citations_since", 0),
            h_index=metrics.get("h_index", 0),
            h_index_since=metrics.get("h_index_since", 0),
            i10_index=metrics.get("i10_index", 0),
            i10_index_since=metrics.get("i10_index_since", 0),
            since_year=metrics.get("since_year"),
            citations_by_year=metrics.get("citations_by_year", []),
        )

    @staticmethod
    def _citation_metrics(payload: dict[str, Any]) -> dict[str, Any]:
        cited_by = payload.get("cited_by") or {}
        table = cited_by.get("table") or []

        def row_values(name: str) -> dict[str, Any]:
            for row in table:
                values = row.get(name)
                if isinstance(values, dict):
                    return values
            return {}

        citations = row_values("citations")
        h_index = row_values("h_index")
        i10_index = row_values("i10_index")
        since_key = next((key for key in citations if key.startswith("since_")), None)
        since_year = None
        if since_key:
            try:
                since_year = int(since_key.removeprefix("since_"))
            except ValueError:
                since_year = None

        graph: list[dict[str, int]] = []
        for point in cited_by.get("graph") or []:
            try:
                graph.append({
                    "year": int(point["year"]),
                    "citations": int(point.get("citations") or 0),
                })
            except (KeyError, TypeError, ValueError):
                continue

        return {
            "citations_since": int(citations.get(since_key, 0)) if since_key else 0,
            "h_index": int(h_index.get("all", 0)),
            "h_index_since": int(h_index.get(since_key, 0)) if since_key else 0,
            "i10_index": int(i10_index.get("all", 0)),
            "i10_index_since": int(i10_index.get(since_key, 0)) if since_key else 0,
            "since_year": since_year,
            "citations_by_year": graph,
        }

    @staticmethod
    def _total_citations(payload: dict[str, Any]) -> int:
        table = (payload.get("cited_by") or {}).get("table") or []
        for row in table:
            citations = row.get("citations") or {}
            if "all" in citations:
                return int(citations["all"])
        summary = payload.get("author") or {}
        if "cited_by" in summary:
            return int(summary["cited_by"])
        raise RuntimeError("Unable to parse total citations from SerpAPI response")

    @staticmethod
    def _article(raw: dict[str, Any], author_id: str) -> Article:
        citation_id = str(raw.get("citation_id") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not citation_id:
            raise RuntimeError(f"Article has no citation_id: {title or '<untitled>'}")
        cited_by = raw.get("cited_by") or {}
        year_raw = raw.get("year")
        try:
            year = int(year_raw) if year_raw not in (None, "") else None
        except (TypeError, ValueError):
            year = None
        return Article(
            citation_id=citation_id,
            title=title or citation_id,
            authors=str(raw.get("authors") or ""),
            publication=str(raw.get("publication") or ""),
            year=year,
            article_url=raw.get("link"),
            scholar_url=(
                f"https://scholar.google.com/citations?view_op=view_citation&user={author_id}"
                f"&citation_for_view={citation_id}"
            ),
            citations=int(cited_by.get("value") or 0),
        )

