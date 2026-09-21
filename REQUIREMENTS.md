# Internship Application Tracker Requirements

## Core record

Each application stores:

| Field | Rule |
| --- | --- |
| ID | Unique, stable, uppercase, exactly 8 characters |
| Company | Required |
| Position | Required |
| Start At | ISO date or `N/A`; defaults to `summer` of next calendar year |
| Date Applied | Defaults to the local current date; `add` accepts an MM/DD/YYYY override |
| Status | Required; defaults to `applied`; accepts registered custom values |
| Status Updated At | UTC timestamp maintained automatically |
| Application Season | Defaults to `summer` and is not entered manually |
| Application Year | Defaults to next calendar year and is not entered manually |
| Company Size/Type | Optional |
| Career/Application Page URL | Required HTTP(S) URL |
| Notes | Optional |

Status transitions are retained in a separate audit table.

Applications must be unique by the exact company, position, career/application
page URL, application season, and application year. `add` rejects a duplicate
and reports the existing application ID. Other fields do not distinguish an
otherwise identical application.

## Commands

- `add COMPANY POSITION URL` requires exactly three positional values and saves
  a confirmed record. It must not perform fuzzy matching, embeddings, or vector
  lookup.
- `update ID --status ...` changes status using the fixed-length public ID and
  automatically records the update time. It may also fill or clear optional
  size/type and notes.
- `list`/`ls`, `show`, and `history` read core application data without vector
  access.
- `remove ID` deletes one application and its status history after confirmation;
  `--yes` supports non-interactive use.
- `search QUERY --mode text|vector|hybrid` owns all similarity retrieval.
  `text` does not touch vector storage; `vector` performs semantic retrieval;
  `hybrid` combines text and vector ranks.
- `vectors setup|rebuild|status` explicitly manages optional local semantic
  search resources.
- `statuses list|add|rename|remove` manages custom statuses. The protected
  built-ins are `applied`, `OA`, `interview`, `offer`, `rejected`, and
  `withdrawn`; custom statuses in use cannot be removed.

## Architecture constraints

- SQLite is the authoritative local store.
- Core database initialization must not require or create vector storage.
- Embedding dependencies load lazily and are optional installation extras.
- Adding or updating a record marks an existing embedding stale implicitly by
  changing its indexed content. It never creates an embedding inline.
- Services return structured domain records and are independent of the CLI so
  a future local GUI can reuse them.

## Planned URL extraction

A future adapter may fetch a supplied job URL and use an LLM to extract a draft.
The extractor returns only `ApplicationDraft`; it has no repository access. The
presentation layer must display the proposed values and obtain explicit user
confirmation before calling the add service. Manual correction remains possible
before persistence.
