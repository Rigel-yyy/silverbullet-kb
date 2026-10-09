# SilverBullet CLI and feedback reference

This reference records the interfaces used by the `silverbullet-kb` protocol. The CLI operates on paths relative to the selected Space. Select a saved Space with `-s NAME`, or use the configured default when there is only one; never print or paste tokens.

## Capability inspection

```bash
sb space ls
sb fs ls Knowledge --recursive --glob '*.md' --json
sb describe page --json
sb describe --json
```

`sb fs` uses the file system HTTP API and does not require Runtime. `sb query`, `sb eval`, and `sb describe` require Runtime. `sb describe page` discovers the live page schema; `sb describe` without a type returns available schemas and query syntax. Treat the live schema and the values in the page index as authoritative; do not maintain a separate registry.

## Read and write

```bash
sb fs read 'Knowledge/example.md'
sb fs stat 'Knowledge/example.md' --json
sb fs write 'Knowledge/example--a7f3.md' --create --file /tmp/document.md
sb fs write 'Knowledge/example--a7f3.md' --if-match '"opaque-revision"' --file /tmp/document.md
```

`fs read` emits exact bytes by default. `fs stat --json` returns an opaque quoted revision; preserve that string unchanged for `--if-match`. Choose exactly one write policy: `--create`, `--if-match REVISION`, or `--overwrite`. The KB protocol uses `--create` for capture and `--if-match` for update; `--overwrite` is not a conflict recovery path. Read the page back after a successful write and verify the H1 and tags.

## Structured query

Discover syntax before relying on fields, then keep the page variable bound in the expression:

```bash
sb describe --json
sb query 'from p = index.pages() where p.name:startsWith("Knowledge/") select p.name, p.tags, p.lastModified' --json
```

Use SLIQ for exact metadata or tag conditions. A query can successfully return an empty table represented as `{}` or a zero count. That is `empty`, not a Runtime outage. The `Knowledge/` path predicate is a retrieval boundary, not a statement about whether other Space content exists.

## Full-text search

Silversearch is an optional plug called from Runtime, for example:

```bash
sb eval 'silversearch.search("distinctive phrase", {silent=true})' --json
sb eval 'silversearch.search("distinctive phrase", {silent=true, singleFilePath="Knowledge/example.md"})' --json
```

Successful hits currently contain fields such as `name`, `score`, `matches`, `excerpts`, and `basename`; a caller may compute match/excerpt counts as a projection. This is the observed plug shape, so inspect live results when the plug version changes. Project only stable fields before returning evidence and read the page before using `content` as evidence. `singleFilePath` needs the Space-relative Markdown filename including `.md`; an empty result with a path missing `.md` is a path-format miss worth correcting once.

Do not call an undocumented `syscall` entry point and do not assume a standalone `sb search` command. An exit 1 such as a nil `syscall` call is `query_error`; repair the invocation or use SLIQ/file fallback.

## Exit status mapping

| Exit | Meaning | Agent next action |
| ---: | --- | --- |
| 0 with hits | Query or write succeeded | Read/project evidence or verify the write |
| 0 with `{}`, `[]`, or `count: 0` | Valid empty result | Relax one term/filter or switch engine once |
| 2 | Invalid input | Correct the command; do not report missing knowledge |
| 3 | Missing target | Confirm the path or classify as an empty candidate set |
| 4 | Access denied | Report the capability/permission gap |
| 5 | Revision conflict | Reread and reapply the explicit update; never overwrite |
| 6 | Edit mismatch or ambiguity | Reread the exact content and stop if the target is unclear |
| 7 | Listing truncated by `--limit` | Continue pagination or remove the limit |
| 8 | Operational failure | Repair connection/runtime and retry only when justified |

## Official references

- [SilverBullet fundamentals](https://github.com/silverbulletmd/silverbullet/blob/main/docs/SilverBullet.md)
- [HTTP API](https://github.com/silverbulletmd/silverbullet/blob/main/docs/HTTP%20API.md)
- [Integrated Query](https://github.com/silverbulletmd/silverbullet/blob/main/docs/Space%20Lua/Integrated%20Query.md)
- [Runtime API](https://github.com/silverbulletmd/silverbullet/blob/main/docs/Runtime%20API.md)
- [Full Text Search](https://github.com/silverbulletmd/silverbullet/blob/main/docs/Full%20Text%20Search.md)
- [Silversearch plug](https://github.com/MrMugame/silversearch)
