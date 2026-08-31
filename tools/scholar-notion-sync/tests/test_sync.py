from datetime import datetime, timedelta, timezone

from scholar_notion_sync.models import Article, ScholarProfile
from scholar_notion_sync.sync import CitationSynchronizer


NOW = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)


def text_prop(value):
    return {"rich_text": [{"plain_text": value}]}


def title_prop(value):
    return {"title": [{"plain_text": value}]}


class Serp:
    def __init__(self, profile):
        self.profile = profile
        self.calls = 0

    def fetch_profile(self, _author_id):
        self.calls += 1
        return self.profile


class Notion:
    def __init__(self, latest=None, papers=None):
        self.latest = latest
        self.papers = papers or []
        self.created = []
        self.updated = []
        self.next_id = 1

    def latest_total_snapshot(self, _id):
        return self.latest

    def query_all(self, data_source_id, body=None):
        if data_source_id == "papers":
            return self.papers
        if body and body.get("filter", {}).get("property") == "幂等键":
            return []
        return []

    def create_page(self, data_source_id, properties):
        page = {"id": f"new-{self.next_id}", "properties": properties}
        self.next_id += 1
        self.created.append((data_source_id, properties))
        return page

    def update_page(self, page_id, properties):
        self.updated.append((page_id, properties))
        return {"id": page_id}


def article(citations=5):
    return Article("author:paper", "Paper", "A", "Venue", 2026, None, "https://scholar", citations)


def synchronizer(serp, notion):
    return CitationSynchronizer(serp, notion, "papers", "snapshots", "author", 72)


def test_skips_before_72_hours_unless_forced():
    latest = {"properties": {"快照时间": {"date": {"start": (NOW - timedelta(hours=71)).isoformat()}}}}
    serp = Serp(ScholarProfile(5, [article()]))
    notion = Notion(latest=latest)
    result = synchronizer(serp, notion).run(now=NOW)
    assert result.skipped is True
    assert serp.calls == 0

    result = synchronizer(serp, notion).run(now=NOW, force=True)
    assert result.skipped is False
    assert serp.calls == 1


def test_new_paper_and_total_snapshot_are_created_total_last():
    serp = Serp(ScholarProfile(5, [article()]))
    notion = Notion()
    result = synchronizer(serp, notion).run(now=NOW)
    assert result.new_papers == 1
    assert [item[0] for item in notion.created] == ["papers", "snapshots", "snapshots"]
    assert notion.created[-1][1]["类型"]["select"]["name"] == "总引用"


def test_existing_paper_updates_and_decrease_warns():
    row = {
        "id": "paper-page",
        "properties": {
            "Scholar Citation ID": text_prop("author:paper"),
            "论文标题": title_prop("Paper"),
            "当前引用量": {"number": 8},
        },
    }
    notion = Notion(papers=[row])
    result = synchronizer(Serp(ScholarProfile(5, [article(5)])), notion).run(now=NOW)
    assert result.new_papers == 0
    assert any("decreased" in warning for warning in result.warnings)
    assert notion.updated[0][1]["最近新增"]["number"] == -3


def test_missing_paper_is_not_deleted():
    row = {
        "id": "old-paper",
        "properties": {
            "Scholar Citation ID": text_prop("author:old"),
            "论文标题": title_prop("Old paper"),
            "当前引用量": {"number": 2},
        },
    }
    notion = Notion(papers=[row])
    result = synchronizer(Serp(ScholarProfile(0, [])), notion).run(now=NOW)
    assert notion.updated[0][0] == "old-paper"
    assert notion.updated[0][1]["状态"]["select"]["name"] == "暂未检出"
    assert any("Temporarily missing" in warning for warning in result.warnings)


def test_writes_stable_homepage_feed(tmp_path):
    feed = tmp_path / "scholar-citations.json"
    serp = Serp(ScholarProfile(5, [article()]))
    notion = Notion()
    sync = CitationSynchronizer(serp, notion, "papers", "snapshots", "author", 72, feed)
    sync.run(now=NOW)

    import json

    payload = json.loads(feed.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["author"]["scholar_id"] == "author"
    assert payload["summary"] == {"total_citations": 5, "publication_count": 1}
    assert payload["publications"][0]["citation_id"] == "author:paper"
