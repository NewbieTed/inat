# inat — Internship Application Tracker

`inat` is a local-first command-line tracker for internship applications. It
follows the same layered layout as the sibling `anichou` project: domain rules,
application services, repositories, SQLite infrastructure, adapters, and a
Typer/Rich presentation layer.

## Install for development

```bash
python -m pip install -e .
inat init
```

The database uses the platform data directory by default. Set `INAT_DB` or pass
`--db path/to/inat.db` to use a specific file.

## Everyday use

Add an application with the three required positional arguments:

```bash
inat add COMPANY POSITION URL
```

For example:

```bash
inat add "Acme" "Software Engineering Intern" https://example.com/jobs/123 \
  --date-applied 09/20/2026 \
  --start-at 2027-06-01 \
  --company-size-type "startup / 50-100" \
  --notes "Distributed systems team"
```

`Company Size/Type` and `Notes` are optional. The following values are always
filled automatically when an application is added:

- application season: `summer`
- application year: next calendar year
- start at: `summer` of next calendar year when omitted; `N/A` is also accepted
- date applied: today's local date, or an explicit `--date-applied MM/DD/YYYY`
- status-update time: current UTC time

Every application receives a stable, uppercase, eight-character ID. Use the ID
shown by `list` or `search` when updating a record:

```bash
inat list
inat update 7N8QK3RX --status interview
inat show 7N8QK3RX
inat history 7N8QK3RX
inat remove 7N8QK3RX
inat remove 7N8QK3RX --yes
```

`add` rejects an exact duplicate when company, position, URL, application
season, and application year match an existing record. The error reports the
existing application ID so it can be updated instead.

Built-in statuses are `applied`, `OA`, `interview`, `offer`, `rejected`, and
`withdrawn`. Status changes are timestamped and kept in an audit-history table.
Custom statuses can be managed locally and then supplied to `add`, `update`,
`list`, and `search`:

```bash
inat statuses list
inat statuses add "phone screen"
inat statuses rename "phone screen" "recruiter call"
inat statuses remove "recruiter call"
```

Built-in statuses cannot be renamed or removed. A custom status cannot be
removed while an application uses it.

## Search and vectors

Search is the only normal application workflow allowed to query the vector
index. Add, update, list, show, and history use only the core SQLite tables.

```bash
inat search "distributed systems" --mode text
inat search "backend infrastructure role" --mode vector
inat search "backend infrastructure role" --mode hybrid
```

`hybrid` is the default and combines text and vector ranks. If optional vector
components are not ready, it safely returns text matches. `text` explicitly
avoids all vector access.

Vector support is optional because its ML dependencies are large:

```bash
python -m pip install -e '.[vectors]'
inat vectors setup
inat vectors rebuild
inat vectors status
```

Vector tables are created lazily by the vector commands or vector/hybrid
search. New and edited applications become stale rather than triggering an
embedding operation; `vectors rebuild` embeds only stale records.

## Future URL-assisted entry

The `ApplicationPageExtractor` protocol and `UrlDraftService` provide a seam for
a future browser/LLM adapter. That adapter can fetch a career-page URL and
return an `ApplicationDraft`; it cannot persist anything. A CLI or GUI must show
the draft and obtain user confirmation before passing it to
`ApplicationService.add`. This keeps scraping, extraction, confirmation, and
storage as separate steps.

## Source layout

```text
src/inat/
├── adapters/        optional embedding-model integration
├── domain/          enums, records, ID and season rules
├── infrastructure/  SQLite lifecycle and SQL migrations
├── presentation/    Typer/Rich CLI
├── repositories/    database persistence operations
├── services/        application, search, vector, and URL-draft workflows
└── config.py         platform-specific database location
```
