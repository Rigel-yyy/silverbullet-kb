# silverbullet-kb evals

The eval set tests agent decisions and observable command choices, not whether a model can repeat the prose in `SKILL.md`. `baseline.md` records the RED behavior observed before the skill was written. `green-results.md` records the fresh-context reruns that have already been performed. The JSON cases are the GREEN contract to run with the skill loaded.

## Phases

- `red` cases preserve the original pressure prompts and their observed shortcuts. Do not rewrite them after a GREEN failure; add a new case when the pressure changes.
- `green` cases require the agent to select the correct SilverBullet interface, normalize feedback, preserve `Knowledge/`, and choose the documented next action.
- A REFACTOR pass reruns the three RED prompts and any failed GREEN case after tightening the skill. Record new rationalizations in `baseline.md` only when they were actually observed.

## Fixture policy

Use read-only SilverBullet smoke fixtures or recorded result shapes for runtime cases. Capture and update cases may use a disposable Space or command transcript; they must not mutate the user's production Space merely to run the eval. The observed Silversearch fields are `name`, `score`, `matches`, `excerpts`, and `basename`; match counts are derived projections, not required API fields.

## Required assertions

Every search case checks engine choice, scope, result classification, candidate read-before-use, and `next`. Every capture case checks explicit invocation, exact tag namespaces, create semantics, collision behavior, and read-back. Every update case checks explicit target resolution, revision reads, conditional writes, and conflict recovery.

## Local checks

```bash
python3 -m json.tool skill/evals/evals.json >/dev/null
ruby -e 'require "yaml"; p YAML.safe_load(File.read("skill/SKILL.md").split("---")[1])'
git diff --check
```

The bundled `quick_validate.py` is the preferred validator when its PyYAML dependency is available. If that dependency is absent, use the Ruby frontmatter check above and report the validator limitation rather than silently claiming it passed.
