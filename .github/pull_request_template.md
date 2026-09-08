<!--
Thanks for the pull request! Fill in the sections below, then complete the
checklist. CodeRabbit's "Checklist complete" pre-merge check fails if any
unticked ("- [ ]") task-list item remains in this description, so tick each
box as you go (or mark inapplicable items with "[~]").
-->

## Summary

<!-- What does this change do, and why? Reference the issue or work item
     this closes. -->

Closes #

## Changes

<!-- Bullet list of the meaningful changes. Group by area if the PR spans
     more than one (e.g. transport, models, docs). -->

-

## Testing

<!-- How did you verify this? Which commands did you run? Paste a short,
     redacted transcript if useful. Never paste a live TP_TOKEN. -->

-

## Context

<!-- Anything a reviewer should know: alternatives considered, follow-ups,
     risk, migration notes, or "none". -->

-

## Checklist

- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run mypy --strict src` passes
- [ ] `uv run pytest -q` passes and coverage stays at or above 90%
- [ ] `uv run pre-commit run --all-files --hook-stage pre-commit` passes
- [ ] `uv run pre-commit run --all-files --hook-stage pre-push` passes
- [ ] New public functions, methods, and classes have docstrings
- [ ] No real credentials, tokens, or PII are added to the diff
- [ ] `TODO`/`FIXME`/`HACK`/`XXX` markers name an issue (e.g. `TODO(#123)`)

<!--
Post-merge verification does not belong in this description. It lives on the
linked work item under its own "## Post-merge verification" heading, where it
gates that item's Verify -> Done transition. Keeping it there leaves this
checklist purely pre-merge, so "all boxes ticked" and "ready to merge" mean the
same thing.
-->

<!--
Implicit merge gates — CI passing, the CodeRabbit review, human approval — are
deliberately absent from the checklist above. Branch protection already
enforces them, and rendering them as boxes invites a tick before the gate has
actually cleared.
-->
