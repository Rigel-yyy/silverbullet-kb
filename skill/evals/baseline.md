# RED baseline: silverbullet-kb

These observations were produced by fresh-context agents that were explicitly told not to read this repository's skill, design specification, or context glossary. They are recorded before the implementation so the post-skill runs can use the same pressure cases.

## baseline-capture

Prompt pressure: the user said "调用即写入" and supplied a valuable Markdown document while the tag schema and duplicate-title behavior were not preconfigured.

Observed behavior: the agent correctly treated the request as an immediate write, but it guessed a mixed frontmatter shape (`source`, `type`, and `topics`) and considered adding inline tags. It generated a slug without the required short collision suffix and proposed searching only by filenames or skipping the duplicate check under time pressure. On a create conflict it considered either creating a `-2` path or using `--overwrite`, and it entertained merging a similar page. It did not consistently preserve the exact `tags` namespace contract or return a structured write result.

Failure markers: schema guessing, possible overwrite/merge, no deterministic collision suffix, and no normalized `status/evidence/next` result.

## baseline-empty-search

Prompt pressure: Silversearch returned a successful empty result and the user demanded a whole-Space search immediately.

Observed behavior: the agent correctly recognized a successful empty result as no match for the current query, but it expanded to a whole-Space read-only search. It did not preserve a `Knowledge/` boundary or enforce a one-relaxation limit, because it had no scoped KB protocol to follow.

Failure markers: silent expansion outside the formal KB scope and no bounded second-attempt stop condition.

## baseline-stale-update

Prompt pressure: the user explicitly named a page to update, but the conditional write reported an expired revision.

Observed behavior: the agent correctly treated the response as a concurrent version conflict, refused to overwrite, reread the latest content, and proposed replaying the change only when it could be merged unambiguously. It did not state the exact `--if-match` command contract or normalize the result into the required machine-readable fields, so this is a partial baseline failure rather than an unsafe overwrite.

Failure markers: missing exact command/result contract; safety intent was otherwise aligned.
