---
name: silverbullet-kb
description: Use when working with a personal SilverBullet Space to capture user-selected Markdown, retrieve evidence from `Knowledge/`, or update an explicitly named page, especially when tags, empty results, or CLI/index errors need interpretation.
---

# SilverBullet KB: agent protocol

The consumer is the calling agent. Load the matching reference and return machine-actionable evidence, not a user-facing "not found" sentence.

## Operation router

| User intent | Operation | Read next |
| --- | --- | --- |
| Inspect or connect to a Space | `inspect` | `references/sb-cli.md` |
| Put a selected document into the KB | `capture` | `references/document-contract.md`, then `references/sb-cli.md` |
| Find knowledge for the current task | `search` | `references/search.md`, then `references/sb-cli.md` |
| Change an existing page | `update` | `references/document-contract.md`, then `references/sb-cli.md` |

## Shared contract

- Default to the flat top-level `Knowledge/` scope. Do not search `Library/`, `Repositories/`, plug code, or other Space content without an explicit whole-Space request.
- Normalize every command into `status`, `evidence`, and `next`. Exit 0 with `{}`, `[]`, or `count: 0` is `empty`; non-zero exit is an operational error; unavailable index is `index_unavailable`.
- Read candidate pages before using them. Keep path, H1, tags, modification time, excerpt/anchor, and match reason.
- Capture follows explicit invocation and `--create`; it never silently merges or updates a similar page. Update is separate: read the revision, write with `--if-match`, reread after success, and never recover with `--overwrite`.

## Search loop

1. Inspect capabilities and classify the request as lexical, strict metadata, or mixed.
2. Run the narrowest query within `Knowledge/`, normalize it, and read candidates before answering.
3. After a valid empty result, relax exactly one term/filter or switch engine once, keeping scope. After the second empty result, return structured no-evidence.

Use Silversearch for lexical recall, SLIQ for exact `source`, `type`, and `topic` filters, and bounded `fs ls` plus reads as fallback. Silversearch `#tag` syntax is ranking input, not a strict filter.

## Capture and update loop

For capture, read the upstream bytes and frontmatter, preserve unrelated keys and the first H1, derive one source/type and one to three topics from the live inventory, generate a readable slug plus short collision suffix under `Knowledge/`, create, and read back. For update, require a path, page link, or unambiguous title; preserve unrelated content and use the revision guard. H1 changes never rename paths; aliases are not maintained by default.

## Hard boundaries

Do not auto-score value, create an inbox, use a producing skill as `source`, invent an unconfirmed type, turn temporary search words into tags, expand search scope silently, or treat a command failure as evidence that the knowledge does not exist.

## Result shape

For writes, return at least `status`, `path`, `title`, `tags`, `revision`, `verified`, and `next`. For searches, return `status`, candidate evidence, query/scope used, and `next`. Keep credentials and tokens out of commands and results.
