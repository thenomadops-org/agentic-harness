# Merge-gate rules for Phase 1

The PreToolUse hook at `plugin/hooks/merge-gate/` was removed in OPS-333.
Phase 1 ports these rules into the qa-verdict check. The hook source is
recoverable from tag `pre-harness-rewrite` (`c114b2e`).

A merge to `main` was refused unless every condition held. The hook failed
closed. An owner override recorded on the story let the merge through.

1. **The builder is not the reviewer.** QA verification had to be a passing
   verification record from an actor that is not the builder (the recorded
   builder actor id, or the recorded builder agent). The merging actor was
   refused when it was the builder.
2. **The verifier uses a different model.** The verifier model had to differ
   from the builder model. If the builder model was unrecorded, the hook
   refused, because a different model could not be shown.
3. **CI is green on the pull request head.** GitHub status-check conclusions
   had to be SUCCESS, NEUTRAL, or SKIPPED, and the recorded CI result had to
   be a success for that same head commit.

The hook also required a passing council verdict, and it refused a pull
request that changed anything under `plugin/` (the owner merges `plugin/`).

Port the rules. Do not copy the hook's command matcher or its board client
into the qa-verdict check.
