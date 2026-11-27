# SilverBullet KB document contract

The KB stores user-selected high-value documents under a flat top-level `Knowledge/` directory. The path is a stable storage address; the first H1 is the display title. The upstream document may not know this contract, so the skill applies it at capture time.

## Pre-capture probes

Read the complete upstream bytes before changing metadata. Resolve the project with `git remote get-url origin` (parse the final repository component from HTTPS or SSH scp-style syntax and remove `.git`), then fall back to `git rev-parse --show-toplevel` and its directory name, then `unknown`. When Runtime is available, inspect the live page index and reuse existing `source/`, `type/`, and `topic/` spellings; this is discovery, not a manually maintained registry. If the agent infers a type outside the known values, stop at `needs_type_confirmation` instead of inventing one.

## Frontmatter

Use a `tags` array with exactly one tag from each required role:

```yaml
---
tags:
  - source/example-project
  - type/experience
  - topic/concurrency
  - topic/optimistic-locking
---
```

`source` identifies the producing project, `type` identifies the primary knowledge shape, and `topic` identifies one to three core subjects. Tags are primarily for strict filtering; full-text search still works without them.

Preserve unrelated frontmatter keys, values, and document body. Only normalize or add the contract-controlled `tags` array. If existing tags contain metadata that cannot be represented without losing meaning, stop with a format ambiguity instead of silently deleting it.

## Source

Resolve the source in this order:

1. Git remote repository name, taking the final path component from either an HTTPS URL or an SSH scp-style remote such as `git@host:org/project.git` and removing the `.git` suffix.
2. Git root directory name.
3. `unknown` when neither can be confirmed.

The producing skill name is never a source value. Normalize only what is needed for the tag slug; do not combine multiple projects into one source tag.

## Type

Choose exactly one type from the primary evidence. Use `experience` when the document records a lived development, debugging, design, or operations process. Use `research` when its primary evidence is systematic investigation, comparison, or source analysis rather than one lived execution.

The type set is open. If the user explicitly supplies a new `type/<slug>`, accept it and discover it from the live page/tag inventory later. If the agent infers a new type, propose it and obtain confirmation before writing. Do not maintain a manual registry or silently coerce an unfamiliar type into `experience` or `research`.

## Topics

Choose one to three topics that describe the document's core subjects. Use lowercase kebab-case and prefer an existing spelling from the live inventory. Do not copy every keyword, query term, project name, or implementation detail into topics.

## Path and title

Preserve the upstream first H1 exactly as the display title. Generate a readable path slug plus a short collision suffix, for example `Knowledge/distributed-lock-pitfall--a7f3.md`. Keep the path flat and stable when the H1 changes. Do not add aliases by default.

If the generated path exists during capture, generate another short suffix and create a new page. Never turn capture into a similarity search, merge, or overwrite.

The collision loop is path-based: check or attempt the candidate path, and on a create conflict generate another short suffix and retry `--create`. Do not use a title match or similar content as an update key.

## Capture

Capture is authorized by the explicit skill invocation. Validate the source, type, topics, H1, and destination; then write a new page with:

```bash
sb fs write 'Knowledge/distributed-lock-pitfall--a7f3.md' --create --file /tmp/kb-document.md
```

Read the page and stat it after writing. Return `status`, `path`, `title`, `tags`, `revision`, `verified`, and `next`. If `--create` reports a conflict, generate a new path and retry the create operation; never use `--overwrite`.

## Update

Update only when the user explicitly identifies a page by path, page link, or unambiguous unique title. Read the current bytes and revision first, preserve unrelated content, and write with the exact quoted revision:

```bash
sb fs stat 'Knowledge/distributed-lock-pitfall--a7f3.md' --json
sb fs write 'Knowledge/distributed-lock-pitfall--a7f3.md' --if-match '"opaque-revision"' --file /tmp/updated.md
```

Exit 5 means the page changed after the read. Reread and reapply the requested change only when it is unambiguous; otherwise stop with a revision conflict for the calling agent. Never blindly retry or overwrite. Read back the final bytes and report the new revision.

## Scheduled maintainer

This section applies only to a dedicated scheduled bot that the owner has explicitly configured as the KB maintainer, for example the Orca nightly bot. An interactive coding agent is never the maintainer: it stays read-first and uses Capture or Update only on explicit user invocation, even when it finds a page that looks stale or a lesson that looks valuable. The decision record is ADR 0002 in this repository.

The maintainer's authority comes from owner configuration, not a per-write invocation, and it uses the same contract as every other writer:

- Write only flat `Knowledge/<readable-slug>--<suffix>.md` paths with exactly one `source/`, one `type/`, and one to three `topic/` tags reused from the live inventory. Do not invent a type; report a proposed type for owner confirmation instead.
- Create new pages with `--create` and the path-based collision loop. Before treating a lesson as new, search `Knowledge/` for an existing page on the same subject; a match is a merge candidate, never a silent duplicate or an overwrite target.
- Merge additively: stat the page, read the exact bytes, append or extend sections such as examples, boundaries, and verification sources, and write with `--if-match`. Never replace the full page, delete or rewrite human-authored content, or rename a path.
- On exit 5 or when the latest bytes no longer allow an unambiguous additive merge, skip the page and record `revision_conflict`. Do not retry blindly and never use `--overwrite`.
- Read back every successful write and verify path, H1, tags, and revision.

Each run ends with a post-hoc diff report for the owner: created pages, merged pages with their diffs and new revisions, skipped conflicts, and errors. A run with no changes reports an explicit no-op. Writes do not wait for approval, but none are silent.

## Do not rewrite upstream content

The KB skill adds or validates storage metadata and the first H1/path relationship. It does not rewrite a Feynman lecture or research document for style, decide whether it is valuable, create an inbox, or silently change the document's meaning.
