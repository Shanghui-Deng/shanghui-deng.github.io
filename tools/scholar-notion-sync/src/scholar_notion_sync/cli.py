import logging
import os
from pathlib import Path

from .config import Settings
from .notion import NotionClient
from .serpapi import SerpApiClient
from .sync import CitationSynchronizer


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings.from_env()
    result = CitationSynchronizer(
        SerpApiClient(settings.serpapi_key),
        NotionClient(settings.notion_token),
        settings.papers_data_source_id,
        settings.snapshots_data_source_id,
        settings.scholar_author_id,
        settings.sync_interval_hours,
        Path(os.getenv("SCHOLAR_FEED_PATH", "static/data/scholar-citations.json")),
    ).run(force=settings.force_sync)

    if result.skipped:
        print("Sync skipped: the last successful snapshot is less than 72 hours old.")
        return
    print(
        f"Sync complete: total={result.total_citations}, papers={result.papers}, "
        f"new_papers={result.new_papers}, warnings={len(result.warnings)}"
    )
    for warning in result.warnings:
        logging.warning(warning)


if __name__ == "__main__":
    main()
