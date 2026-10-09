# SilverBullet KB search reference

Search is a bounded retrieval loop for the calling agent. It produces evidence and a next action; it does not promise that a valid empty query proves the absence of knowledge.

## Classify the request

| Request shape | Engine | First action |
| --- | --- | --- |
| A phrase, mechanism, event, or project name | Silversearch | Search distinctive lexical terms within `Knowledge/` |
| Exact source, type, topic, or metadata condition | SLIQ | Query `index.pages()` with a `Knowledge/` path predicate |
| Both a phrase and exact tags | SLIQ then page reads, or Silversearch with `singleFilePath` | Narrow by metadata, then verify body evidence |
| Runtime or plug unavailable | `fs ls` and `fs read` | Enumerate bounded Markdown files under `Knowledge/` and inspect candidates |

Search terms are temporary. Never add a query word to frontmatter merely because it appeared in the question.

## Lexical recall

Extract a small query from the main entity, mechanism/event, and one distinctive phrase or project name. Use a quoted phrase when exact wording matters. Call the documented `silversearch.search` API and keep the result projection small: `name`, `score`, `matches`, `excerpts`, and `basename` are enough to choose candidates; compute counts only as derived fields. Read the corresponding Markdown page before treating a match, excerpt, or returned content as evidence.

Silversearch `#tag` input can boost ranking but does not enforce an exact tag filter. If the request says "only" or names an exact type/topic/source, route that part through SLIQ.

## Strict filtering

Use live schema discovery before assuming fields, then query `index.pages()` with a path restriction such as `p.name:startsWith("Knowledge/")`. Filter the `tags` array for exact namespace values like `source/project`, `type/experience`, or `topic/concurrency`. Inspect the actual inventory to reuse spellings; schema names alone do not define the value set.

When the query returns `{}`, `[]`, or `count: 0` with exit 0, classify it as `empty` for that scope and query. It may mean the directory is empty, the term is too narrow, or a path expression is wrong. It is not an index failure.

## Mixed queries and fallback

For mixed requests, use SLIQ to narrow candidates and read them, or use Silversearch's `singleFilePath` with the exact `.md` filename for content confirmation. If `singleFilePath` omits `.md` and returns empty, correct the path once before trying another strategy.

If Runtime or Silversearch is unavailable, use `sb fs ls Knowledge --recursive --glob '*.md'` and read a bounded set of candidate files. If `fs ls --limit` exits 7, continue pagination or remove the limit before drawing conclusions. A command exit 2, 4, 5, 6, or 8 is an operational condition, not an empty knowledge result.

If the caller explicitly requests whole-Space search, record the scope change in the result and label any `Library/`, `Repositories/`, or plug matches as outside the formal KB. An empty `Knowledge/` query never authorizes this expansion by itself.

## One controlled relaxation

After a valid empty result, change one thing: remove one strict filter, replace an exact phrase with a distinctive term, add a known alias, or switch engines. Keep the `Knowledge/` boundary and record the changed query. Do not silently search the whole Space. If the second attempt is also empty, return:

```yaml
status: no_evidence
scope: Knowledge/
attempts: 2
evidence: []
next: ask_for_a_better_term_or_explicit_scope
```

## Candidate evidence

Before answering from a page, return or retain this evidence shape:

```yaml
path: Knowledge/example--a7f3.md
title: The first H1
tags:
  - source/example-project
  - type/experience
  - topic/concurrency
updated: 2026-10-09T00:00:00Z
anchor: "the paragraph or heading that supports the answer"
reason: "matched the distinctive mechanism and exact topic filter"
```
