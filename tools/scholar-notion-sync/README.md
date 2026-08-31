# Google Scholar → Notion sync

This background job tracks Google Scholar author `9RAuZ4YAAAAJ` every 72 hours.
It updates the two databases in the Notion **Google Scholar 引用看板** and
publishes a stable, versioned data interface at:

`/static/data/scholar-citations.json`

The homepage does not consume or display this feed yet. A future UI can read:

- `summary.total_citations`
- `summary.publication_count`
- `updated_at`
- `publications[]`, keyed by stable `citation_id`, including each paper's
  title, metadata, links, and citation count

## Required GitHub Actions secrets

| Secret | Value |
|---|---|
| `SERPAPI_KEY` | SerpAPI key |
| `NOTION_TOKEN` | Notion internal integration token |
| `PAPERS_DATABASE_ID` | `5ae0192e-670f-4b07-a153-6ee14dc61e29` |
| `SNAPSHOTS_DATABASE_ID` | `75cd42af-8d5c-4dfd-acfa-b20c3964c022` |

The Notion integration must have read, insert, and update access to both
databases. The total snapshot is written last, so partial failures do not move
the 72-hour success clock. Manual workflow runs can bypass the interval gate.
