# ADR 0002: Separate interactive agents from a dedicated scheduled maintainer

Status: proposed

Extends: [ADR 0001](0001-agent-native-kb-boundaries.md)

## Context

ADR 0001 made every KB write an explicit, user-invoked operation and rejected automatic value scoring because it would move the user's value decision into hidden policy. That remains the right rule for coding agents working on a task: a mid-task write would bypass the user and pollute `Knowledge/` with unreviewed state. The KB is now also the single source of truth for cross-repo engineering mental models and verified bash, external-tool, and debugging methods, and keeping that corpus current by hand does not scale. The owner wants a dedicated Orca nightly bot to distill new experience into `Knowledge/` on a schedule and report what changed afterward, without weakening the guarantees ADR 0001 gives to human edits.

## Decision

Recognize exactly two writer classes and keep one storage contract for both.

Interactive coding agents keep ADR 0001 unchanged. They are read-first: they search `Knowledge/` freely, but capture and update still require an explicit user invocation. They never auto-score value, never auto-capture or auto-update mid-task, and never act as the scheduled maintainer, even when they notice a page that looks stale.

A dedicated scheduled maintainer, such as the Orca nightly bot, may perform automated incremental capture and merge under `Knowledge/` only when the owner has explicitly configured that bot for this role. Its authority comes from that configuration rather than from a per-write user invocation. It must follow every ADR 0001 invariant and these additional rules:

- Same layout and tags: write only flat `Knowledge/<readable-slug>--<suffix>.md` paths with no subfolders, and use one `source/`, one `type/`, and one to three `topic/` tags reused from the live inventory. It may not invent a type; a new type still needs owner confirmation.
- Same write guards: new pages use `--create` with the path-based collision loop; changes to existing pages read the revision first and write with `--if-match`; every successful write is read back and verified. `--overwrite` stays forbidden.
- Additive merge only: a merge appends or extends sections such as examples, boundaries, and verification sources. It never replaces the full page, never deletes or rewrites human-authored content, and never renames a path when an H1 changes.
- Abort on conflict: if `--if-match` fails or the latest bytes no longer support an unambiguous additive merge, the maintainer skips that page and records a `revision_conflict` in its report. It does not retry blindly or fall back to an overwrite.
- Human on the loop: every run ends with a post-hoc diff report listing created pages, merged pages with their diffs, skipped conflicts, and errors. A run with no changes reports an explicit no-op. Approval is not required before writing, but nothing is written silently.

Retrieval stays bounded for both classes: Silversearch for lexical recall, SLIQ for exact tag filters, and a bounded `fs` scan as fallback, all scoped to `Knowledge/`.

## Consequences

Coding agents can treat `Knowledge/` as a trustworthy cross-repo reference without gaining any new write paths, so ADR 0001's protection against hidden policy still holds for them. The automated value judgment ADR 0001 rejected for day one is now allowed only inside the dedicated maintainer. Its effect is bounded by additive merges, conditional writes, and a reviewable report, so the owner can audit and revert any change. Human edits win every race: a concurrent edit makes the maintainer abort on that page instead of overwriting it. The maintainer's own configuration, schedule, and distillation prompt live with the bot, outside this repository; this skill defines only the storage and write contract the bot must honor.

## Alternatives rejected

Letting interactive agents write automatically when they judge something valuable was rejected because it recreates hidden mid-task policy and spreads write authority across every session. Requiring pre-write human approval for the maintainer was rejected because a blocking queue is the inbox ADR 0001 already declined. Giving the maintainer its own subfolder, tag namespace, or overwrite permission was rejected because it would split the corpus and break the single layout and tag contract that retrieval relies on.
