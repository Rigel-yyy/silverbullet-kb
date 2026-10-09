# GREEN verification results

These are the fresh-context reruns performed after the skill and references were written. They use the same three pressure prompts recorded in `baseline.md`, plus a source/path capture check. The results below are observations from the agents, not claims that every declarative JSON case has been executed against a live Space.

## capture pressure

The agent loaded `SKILL.md` and the document/CLI references. It preserved the upstream H1 and unrelated frontmatter, derived `source/project` from an SSH remote, selected exactly one type and one to three topics, wrote a `tags` array, generated a flat slug plus short collision suffix, used `sb fs write ... --create`, and read back bytes and revision. It rejected `topics`/inline tag guesses, similarity merge, `-2` title semantics, and `--overwrite`. It returned a structured capture result with `status`, `path`, `title`, `tags`, `revision`, `verified`, and `next`.

## empty-search pressure

The agent classified successful `[]`, `{}`, or zero-count responses as `empty`, not a service failure. Without an explicit whole-Space request it kept `Knowledge/`, changed one term/filter or engine once, and stopped with `no_evidence` after the second empty result. When the prompt explicitly requested whole-Space search, it recorded the scope change and labeled non-KB matches rather than silently treating them as formal knowledge.

## stale-update pressure

The agent read the exact quoted revision, used `--if-match`, classified exit 5 as `revision_conflict`, reread the latest bytes and revision, and replayed the change only when unambiguous. It never used `--overwrite`; an ambiguous merge returned a decision-needed result, and a successful retry required read-back verification.

## additional runtime checks

Read-only smoke checks against `bohrium-hindsight` confirmed `sb describe page` and `sb describe` exit 0, a `Knowledge/` SLIQ scope can return `{}`, Silversearch no-hit and a missing `.md` `singleFilePath` return `[]`, and an invalid `syscall` entry point exits non-zero. The skill maps these shapes to `empty` or `query_error` as appropriate.

## Environment note

The system Python lacks PyYAML, so the validator must run as `/Users/dp/.local/bin/uv run --with pyyaml python /Users/dp/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill`. That command returned `Skill is valid!`; Ruby frontmatter parsing, JSON parsing, and `git diff --check` also passed.
