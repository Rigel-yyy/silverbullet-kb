# Agent-native SilverBullet KB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved SilverBullet KB design into an installable agent skill that teaches the complete inspect, capture, search, update, feedback interpretation, and recovery loop.

**Architecture:** Keep `skill/SKILL.md` as the short prompt-loaded protocol and move command syntax, search routing, and document/tag rules into focused references. The skill returns structured internal outcomes (`status`, `evidence`, `next`) so an agent can distinguish empty evidence from an unavailable capability or failed operation. Eval cases model the agent's decisions and use observed SilverBullet result shapes rather than assuming a custom service wrapper.

**Tech Stack:** Markdown skill files, JSON eval cases, SilverBullet `sb` CLI, SilverBullet Runtime/SLIQ, optional Silversearch plug, shell validation.

**Spec:** `docs/superpowers/specs/2026-10-08-silverbullet-kb-design.md`

## Global Constraints

- Default storage and retrieval scope is the flat top-level `Knowledge/` directory.
- Capture is an explicit create operation; update is a separate explicit operation.
- Capture writes with `sb fs write PATH --create`; update writes with `--if-match` after reading the latest revision.
- Frontmatter tags contain exactly one `source/<project>`, exactly one `type/<kind>`, and one to three `topic/<slug>` values.
- Source resolution is Git remote repository name, then Git root directory name, then `unknown`; skill names are never source values.
- Initial types are `experience` and `research`; user-explicit new types are accepted without a registry edit, while agent-inferred new types require confirmation.
- Search uses Silversearch for lexical recall, SLIQ for strict metadata filtering, and bounded file reads as fallback.
- Empty results are valid evidence; command failures and unavailable indexes are different statuses.
- The skill must not create an inbox, score value automatically, silently update a similar page, rename paths when H1 changes, or maintain aliases by default.

## Review Focus

- A successful empty result must trigger one controlled query relaxation, not a false claim that the KB has no knowledge; covered by the search feedback eval.
- A non-zero command exit must remain an operational failure, not be converted into no evidence; covered by the command failure eval.
- `#tag` in Silversearch must not be treated as a strict filter; covered by the mixed search eval.
- A duplicate capture must create a new collision-safe path, while an explicit update must use the revision guard; covered by capture/update conflict evals.
- A new type must be discoverable from live inventory without a hand-maintained registry; covered by dynamic type and inventory evals.

### Task 1: Establish the RED baseline

**Files:**
- Create: `skill/evals/baseline.md`
- Modify: `skill/evals/evals.json`

**Interfaces:**
- Consumes: the pressure scenarios listed in the approved spec.
- Produces: recorded no-skill agent behavior and stable scenario identifiers reused by the post-skill evals.

- [ ] **Step 1: Run three fresh-context pressure scenarios without loading `skill/SKILL.md`**

  Use a capture request under time pressure, a search request with an empty result followed by a tempting whole-Space fallback, and an explicit update request with a stale revision. Record the agent's exact proposed commands, result interpretation, and any rationalization.

- [ ] **Step 2: Record the observed failures in `skill/evals/baseline.md`**

  Keep only observed behavior and the pressure that triggered it; do not write the solution into the baseline.

- [ ] **Step 3: Add scenario IDs and expected failure markers to `skill/evals/evals.json`**

  Include `baseline-capture`, `baseline-empty-search`, and `baseline-stale-update` with `phase: red`.

- [ ] **Step 4: Verify the baseline is genuinely failing**

  Run the scenario harness or review the fresh-context transcripts and confirm at least one required contract is violated in each case.

- [ ] **Step 5: Commit**

  ```bash
  git add skill/evals/baseline.md skill/evals/evals.json
  git commit -m "test: establish SilverBullet KB skill baseline"
  ```

### Task 2: Write the prompt-loaded agent protocol

**Files:**
- Modify: `skill/SKILL.md`

**Interfaces:**
- Consumes: `references/sb-cli.md`, `references/search.md`, and `references/document-contract.md` from Tasks 3-5.
- Produces: the `silverbullet-kb` discovery description and the operation/feedback protocol loaded into an agent prompt.

- [ ] **Step 1: Replace the draft frontmatter description**

  Use a third-person description beginning with `Use when...` and mention SilverBullet KB capture, retrieval, strict tag filtering, explicit updates, and empty/error result interpretation without summarizing the workflow.

- [ ] **Step 2: Add the compact operation router**

  Define the four operations (`inspect`, `capture`, `search`, `update`) and their trigger conditions, with a default `Knowledge/` scope.

- [ ] **Step 3: Add the agent result contract**

  Require every operation to normalize feedback into `status`, `evidence`, and `next`; include the distinctions for empty query, unavailable index, command failure, create conflict, and revision conflict.

- [ ] **Step 4: Add the bounded retrieval loop and hard prohibitions**

  Require candidate reads before evidence use, allow one controlled relaxation, and explicitly forbid silent scope expansion, automatic value scoring, inbox promotion, similarity-based updates, path renames, and aliases.

- [ ] **Step 5: Add quick-reference tables and links to the focused references**

  Keep the file prompt-loadable and move flags, SLIQ syntax, result examples, and tag derivation details out of the entry file.

- [ ] **Step 6: Verify structure and description limits**

  Run the skill validator and check the word count; confirm the description starts with `Use when`, is third-person, and does not encode the workflow as a shortcut.

- [ ] **Step 7: Commit**

  ```bash
  git add skill/SKILL.md
  git commit -m "feat: add agent-native SilverBullet KB protocol"
  ```

### Task 3: Document SilverBullet command and feedback interfaces

**Files:**
- Create: `skill/references/sb-cli.md`

**Interfaces:**
- Consumes: observed `sb --help`, `sb fs --help`, `sb describe`, and `sb query` behavior.
- Produces: exact command templates and normalized result mapping used by `SKILL.md` and the evals.

- [ ] **Step 1: Document capability inspection commands**

  Cover Space selection, `sb fs ls`, `sb describe page`, and live tag/value inventory discovery without exposing credentials or assuming a registry.

- [ ] **Step 2: Document create, read, and conditional update commands**

  Include `sb fs read`, `sb fs write PATH --create`, `sb fs write PATH --if-match REVISION`, conflict behavior, and read-back verification.

- [ ] **Step 3: Document SLIQ invocation and schema discovery**

  Use `sb describe` before relying on schema details and show `index.pages()` plus a `Knowledge/` path restriction.

- [ ] **Step 4: Document exit codes and JSON result normalization**

  Include successful empty collections, Silversearch result arrays, truncation exit 7, non-zero operational failures, and the corresponding `next` action.

- [ ] **Step 5: Verify every command against the documented CLI version or label it as a fallback**

  Do not invent flags or claim that `sb query` is full-text search.

- [ ] **Step 6: Commit**

  ```bash
  git add skill/references/sb-cli.md
  git commit -m "docs: document SilverBullet CLI feedback contract"
  ```

### Task 4: Document retrieval routing and bounded search

**Files:**
- Create: `skill/references/search.md`

**Interfaces:**
- Consumes: `sb-cli.md` command/result shapes and the approved retrieval loop.
- Produces: lexical, structured, mixed, and fallback search procedures.

- [ ] **Step 1: Define query classification**

  Separate lexical recall, strict tag/metadata filtering, and mixed requests; state that query words are temporary and never become tags.

- [ ] **Step 2: Define Silversearch routing**

  Show term extraction, quoted phrase handling, result candidate reading, `singleFilePath` use only for `.md`, and the fact that `#tag` boosts ranking rather than filtering.

- [ ] **Step 3: Define SLIQ routing**

  Show exact `source`, `type`, and `topic` filtering through the live page index, with `Knowledge/` path scope and schema discovery.

- [ ] **Step 4: Define fallback and feedback loop**

  Use bounded listing and page reads when indexes or plugs are unavailable; relax exactly one term or filter after a valid empty result; stop with a structured no-evidence result after the second attempt.

- [ ] **Step 5: Add candidate evidence shape**

  Require path, display title, tags, updated time, excerpt/evidence anchor, and match reason before the calling agent uses a page.

- [ ] **Step 6: Commit**

  ```bash
  git add skill/references/search.md
  git commit -m "docs: specify bounded KB search routing"
  ```

### Task 5: Document capture, tags, paths, and update safety

**Files:**
- Create: `skill/references/document-contract.md`

**Interfaces:**
- Consumes: the approved document contract and live tag inventory behavior.
- Produces: deterministic source/type/topic derivation, path generation, and capture/update conflict rules.

- [ ] **Step 1: Define the document shape**

  Show preserved first H1, frontmatter `tags` array, and the exact `source/<project>`, `type/<kind>`, and `topic/<slug>` constraints.

- [ ] **Step 2: Define source resolution**

  Resolve Git remote repository name, then Git root directory name, then `unknown`; never use the producing skill name.

- [ ] **Step 3: Define type and topic rules**

  Classify exactly one type by primary evidence, support `experience` and `research`, accept user-explicit new types, request confirmation for agent-inferred new types, and choose one to three reusable lowercase kebab-case topics.

- [ ] **Step 4: Define path and H1 separation**

  Generate a readable slug plus short collision suffix below flat `Knowledge/`; preserve the H1; do not rename paths or maintain aliases after H1 changes.

- [ ] **Step 5: Define capture and update state transitions**

  Capture always uses create semantics and a new path; update requires an explicit target, reads the latest revision, conditionally writes, and rereads after conflict.

- [ ] **Step 6: Commit**

  ```bash
  git add skill/references/document-contract.md
  git commit -m "docs: define SilverBullet KB document contract"
  ```

### Task 6: Complete evals and update repository documentation

**Files:**
- Modify: `skill/evals/evals.json`
- Modify: `README.md`
- Modify: `docs/decisions.md`
- Create: `skill/evals/README.md`

**Interfaces:**
- Consumes: all skill and reference contracts from Tasks 2-5.
- Produces: post-skill pressure scenarios, coverage metadata, installation guidance, and an append-only decision entry.

- [ ] **Step 1: Add post-skill scenarios**

  Add stable IDs for `describe-page-schema`, `describe-all-syntax`, `sliq-known-page`, `sliq-knowledge-empty`, `search-marker-hit`, `search-no-hit`, `search-knowledge-scope-empty`, `search-single-file-hit`, `search-single-file-path-mismatch`, and `runtime-invocation-error`; project raw Silversearch `matches`/`excerpts` fields and derive counts only when useful. Also cover capture, search without tags, strict source/type/topic filters, system-content exclusion, missing-plugin fallback, explicit update conflict, dynamic type addition, HTTPS/SSH source normalization, unknown source fallback, topic reuse, and read-back verification.

- [ ] **Step 2: Define scenario assertions**

  Assert the agent chooses the correct engine, preserves `Knowledge/` scope, projects only stable result fields, repairs a missing `.md` in `singleFilePath`, reports structured next actions, and never silently overwrites or treats operational errors as no evidence.

- [ ] **Step 3: Write the eval README**

  Explain RED/GREEN/REFACTOR usage, fixture assumptions, and how to run the quick validator without requiring writes to the user's live Space.

- [ ] **Step 4: Update README and decisions**

  Mark the skill as implemented, describe the installable entry and references, and append the implementation decision without rewriting v0 history.

- [ ] **Step 5: Run the validator and JSON checks**

  Validate frontmatter, JSON syntax, links, and absence of accidental credentials or whole-Space defaults.

- [ ] **Step 6: Commit**

  ```bash
  git add skill/evals/evals.json skill/evals/README.md README.md docs/decisions.md
  git commit -m "test: add SilverBullet KB workflow evals"
  ```

### Task 7: Run GREEN and REFACTOR verification

**Files:**
- Modify: `skill/SKILL.md` and relevant references only if a tested loophole is found.
- Modify: `skill/evals/evals.json` and `skill/evals/baseline.md` only if the recorded behavior needs correction.
- Create or modify: `skill/evals/green-results.md`

**Interfaces:**
- Consumes: the complete installed skill and the RED baseline.
- Produces: verified agent behavior under the same pressure scenarios and a clean final branch.

- [ ] **Step 1: Re-run the three RED scenarios with the skill loaded**

  Confirm capture creates, empty search relaxes once while staying in `Knowledge/`, and stale update rereads instead of blindly retrying.

- [ ] **Step 2: Run all post-skill eval cases**

  Record pass/fail and the observed normalized outcome for every scenario.

- [ ] **Step 3: Close any new rationalization**

  If an agent uses a loophole such as treating a successful empty SLIQ table as an outage or using a skill name as `source`, add a direct rule and rerun the affected scenario.

- [ ] **Step 4: Run repository verification**

  Run the skill quick validator, JSON parser, `git diff --check`, and the documented read-only SilverBullet smoke commands.

- [ ] **Step 5: Commit the final verification changes**

  ```bash
  git add skill/SKILL.md skill/references skill/evals README.md docs/decisions.md
  git commit -m "test: verify agent-native SilverBullet KB skill"
  ```
