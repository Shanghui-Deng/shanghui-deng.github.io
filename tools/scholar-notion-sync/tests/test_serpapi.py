from scholar_notion_sync.serpapi import SerpApiClient


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Session:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append(kwargs["params"])
        return Response(next(self.pages))


def test_parses_profile_and_article():
    session = Session(
        [{
            "cited_by": {"table": [{"citations": {"all": 123}}]},
            "articles": [{
                "citation_id": "9RAuZ4YAAAAJ:abc",
                "title": "A paper",
                "authors": "A, B",
                "publication": "Journal, 2026",
                "year": "2026",
                "link": "https://example.test/paper",
                "cited_by": {"value": 7},
            }],
        }]
    )
    profile = SerpApiClient("secret", session).fetch_profile("9RAuZ4YAAAAJ")
    assert profile.total_citations == 123
    assert profile.articles[0].citations == 7
    assert profile.articles[0].year == 2026


def test_paginates_at_one_hundred_results():
    first = {
        "cited_by": {"table": [{"citations": {"all": 100}}]},
        "articles": [
            {"citation_id": f"id:{i}", "title": str(i), "cited_by": {"value": i}}
            for i in range(100)
        ],
    }
    second = {"articles": []}
    session = Session([first, second])
    profile = SerpApiClient("secret", session).fetch_profile("author")
    assert len(profile.articles) == 100
    assert [call["start"] for call in session.calls] == [0, 100]

