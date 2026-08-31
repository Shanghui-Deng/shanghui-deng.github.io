from dataclasses import dataclass


@dataclass(frozen=True)
class Article:
    citation_id: str
    title: str
    authors: str
    publication: str
    year: int | None
    article_url: str | None
    scholar_url: str | None
    citations: int


@dataclass(frozen=True)
class ScholarProfile:
    total_citations: int
    articles: list[Article]

