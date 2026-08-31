import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    serpapi_key: str
    notion_token: str
    papers_data_source_id: str
    snapshots_data_source_id: str
    scholar_author_id: str = "9RAuZ4YAAAAJ"
    sync_interval_hours: int = 72
    force_sync: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        hours = int(os.getenv("SYNC_INTERVAL_HOURS", "72"))
        if hours < 1:
            raise ValueError("SYNC_INTERVAL_HOURS must be positive")
        return cls(
            serpapi_key=_required("SERPAPI_KEY"),
            notion_token=_required("NOTION_TOKEN"),
            papers_data_source_id=_required("PAPERS_DATABASE_ID"),
            snapshots_data_source_id=_required("SNAPSHOTS_DATABASE_ID"),
            scholar_author_id=os.getenv("SCHOLAR_AUTHOR_ID", "9RAuZ4YAAAAJ").strip(),
            sync_interval_hours=hours,
            force_sync=_bool("FORCE_SYNC"),
        )

