from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .models import Article, ScholarProfile
from .notion import NotionClient, date, date_value, number, plain_text, relation, rich_text, title
from .serpapi import SerpApiClient

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    skipped: bool
    total_citations: int | None = None
    papers: int = 0
    new_papers: int = 0
    warnings: tuple[str, ...] = ()


class CitationSynchronizer:
    def __init__(
        self,
        serpapi: SerpApiClient,
        notion: NotionClient,
        papers_data_source_id: str,
        snapshots_data_source_id: str,
        author_id: str,
        interval_hours: int = 72,
        feed_path: Path | None = None,
    ):
        self.serpapi = serpapi
        self.notion = notion
        self.papers_id = papers_data_source_id
        self.snapshots_id = snapshots_data_source_id
        self.author_id = author_id
        self.interval = timedelta(hours=interval_hours)
        self.feed_path = feed_path

    def run(self, *, force: bool = False, now: datetime | None = None) -> SyncResult:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        latest_total = self.notion.latest_total_snapshot(self.snapshots_id)
        if not force and not self._due(latest_total, now):
            LOGGER.info("Last successful sync is less than %s old; skipping", self.interval)
            return SyncResult(skipped=True)

        profile = self.serpapi.fetch_profile(self.author_id)
        existing_rows = self.notion.query_all(self.papers_id)
        existing = {
            plain_text(row["properties"].get("Scholar Citation ID", {})): row
            for row in existing_rows
            if plain_text(row["properties"].get("Scholar Citation ID", {}))
        }
        batch = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        seen: set[str] = set()
        warnings: list[str] = []
        new_papers = 0

        for article in profile.articles:
            seen.add(article.citation_id)
            row = existing.get(article.citation_id)
            previous = number(row["properties"].get("当前引用量", {})) if row else 0
            delta = article.citations - previous
            if row and delta < 0:
                warnings.append(f"{article.title}: citations decreased {previous} -> {article.citations}")

            props = self._paper_properties(article, now, delta, is_new=row is None)
            if row:
                self.notion.update_page(row["id"], props)
                paper_page_id = row["id"]
            else:
                created = self.notion.create_page(self.papers_id, props)
                paper_page_id = created["id"]
                new_papers += 1

            self._upsert_snapshot(
                now=now,
                kind="单篇论文",
                citation_id=article.citation_id,
                citations=article.citations,
                delta=delta,
                batch=batch,
                paper_page_id=paper_page_id,
                label=article.title,
            )

        for citation_id, row in existing.items():
            if citation_id not in seen:
                self.notion.update_page(
                    row["id"],
                    {"状态": {"select": {"name": "暂未检出"}}, "最后同步": date(now)},
                )
                warnings.append(f"Temporarily missing from Scholar: {plain_text(row['properties']['论文标题'])}")

        previous_total = (
            number(latest_total["properties"].get("引用量", {})) if latest_total else 0
        )
        total_delta = profile.total_citations - previous_total
        if latest_total and total_delta < 0:
            warnings.append(
                f"Total citations decreased {previous_total} -> {profile.total_citations}"
            )

        # Commit marker: write total last. A failed partial run therefore remains due.
        self._upsert_snapshot(
            now=now,
            kind="总引用",
            citation_id="TOTAL",
            citations=profile.total_citations,
            delta=total_delta,
            batch=batch,
            paper_page_id=None,
            label="总引用",
        )
        if self.feed_path:
            self._write_feed(profile, now)
        return SyncResult(False, profile.total_citations, len(profile.articles), new_papers, tuple(warnings))

    def _write_feed(self, profile: ScholarProfile, now: datetime) -> None:
        """Publish the stable interface consumed by the homepage in the future."""
        payload = {
            "schema_version": 1,
            "author": {
                "scholar_id": self.author_id,
                "profile_url": f"https://scholar.google.com/citations?user={self.author_id}",
            },
            "summary": {
                "total_citations": profile.total_citations,
                "publication_count": len(profile.articles),
            },
            "updated_at": now.isoformat(),
            "publications": [asdict(article) for article in profile.articles],
        }
        self.feed_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.feed_path.with_suffix(self.feed_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.feed_path)

    def _due(self, latest: dict | None, now: datetime) -> bool:
        if latest is None:
            return True
        last = date_value(latest["properties"].get("快照时间", {}))
        if last is None:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return now - last.astimezone(timezone.utc) >= self.interval

    def _paper_properties(self, article: Article, now: datetime, delta: int, *, is_new: bool) -> dict:
        props = {
            "论文标题": title(article.title),
            "Scholar Citation ID": rich_text(article.citation_id),
            "作者": rich_text(article.authors),
            "发表信息": rich_text(article.publication),
            "年份": {"number": article.year},
            "论文链接": {"url": article.article_url},
            "Scholar链接": {"url": article.scholar_url},
            "当前引用量": {"number": article.citations},
            "最近新增": {"number": delta},
            "最后同步": date(now),
            "状态": {"select": {"name": "活跃"}},
        }
        if is_new:
            props["首次发现"] = date(now)
        return props

    def _upsert_snapshot(
        self,
        *,
        now: datetime,
        kind: str,
        citation_id: str,
        citations: int,
        delta: int,
        batch: str,
        paper_page_id: str | None,
        label: str,
    ) -> None:
        day = now.date().isoformat()
        key = f"{day}:{kind}:{citation_id}"
        rows = self.notion.query_all(
            self.snapshots_id,
            {"filter": {"property": "幂等键", "rich_text": {"equals": key}}, "page_size": 1},
        )
        props = {
            "快照": title(f"{day} · {label}"),
            "快照时间": date(now),
            "类型": {"select": {"name": kind}},
            "Scholar Citation ID": rich_text(citation_id),
            "引用量": {"number": citations},
            "本次新增": {"number": delta},
            "同步批次": rich_text(batch),
            "幂等键": rich_text(key),
            "数据来源": {"select": {"name": "SerpAPI"}},
            "论文": relation(paper_page_id) if paper_page_id else {"relation": []},
        }
        if rows:
            self.notion.update_page(rows[0]["id"], props)
        else:
            self.notion.create_page(self.snapshots_id, props)
