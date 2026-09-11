from dataclasses import dataclass, field


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
    citations_since: int = 0
    h_index: int = 0
    h_index_since: int = 0
    i10_index: int = 0
    i10_index_since: int = 0
    since_year: int | None = None
    citations_by_year: list[dict[str, int]] = field(default_factory=list)

