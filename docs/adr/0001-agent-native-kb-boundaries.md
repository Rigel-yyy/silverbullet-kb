# ADR 0001: Keep the KB agent-facing and scope it to Knowledge/

Status: proposed

## Context

The SilverBullet Space contains both user knowledge and the files that make SilverBullet run, while the main consumer of this skill is an agent. A search result therefore has to carry enough state for the agent to choose its next operation; a human-oriented "nothing found" message is not enough. The KB also needs an explicit value boundary because the user, rather than an automatic classifier, decides which generated documents are worth storing.

## Decision

Use a dedicated top-level `Knowledge/` directory as the default retrieval and storage boundary, with a flat layout and frontmatter tags for provenance, knowledge shape, and core topics. Make capture an explicit create operation and update a separate explicit operation with conditional writes. The skill normalizes every SilverBullet response into a status and next action, and it may perform one controlled query relaxation while keeping the `Knowledge/` scope. The initial type values are `experience` and `research`, but the type set is open to user-declared additions discovered from the live KB inventory.

## Consequences

Agents can distinguish an empty query from an unavailable index or a failed command and can continue the retrieval workflow without guessing. System pages do not pollute default results, and capture cannot silently overwrite an existing document. The flat layout keeps paths stable when a document's H1 changes, while tags carry classification. A new type can be added through the document contract without a skill edit, but agents must ask before inventing a type that the user did not provide.

## Alternatives rejected

An inbox and automatic value scoring were rejected for day one because they move the user's value decision into hidden policy. A path taxonomy and aliases were rejected because they duplicate the tag contract and create rename and synchronization work without improving agent retrieval.
