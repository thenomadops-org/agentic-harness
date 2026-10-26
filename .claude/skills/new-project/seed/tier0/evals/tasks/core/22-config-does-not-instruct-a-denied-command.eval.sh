#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# The instructions must not hand an agent a command the harness denies.
#
# `.claude/settings.json` carries a deny list — force-push, history rewriting,
# reading a service-account key. It is the hard stop; the config is the briefing.
# See `.claude/settings.README.md` for why that file is owner-maintained.
# When the briefing contains a runnable command the deny list blocks, the agent
# does not simply stop. The recorded behaviour is that it treats the denial as an
# obstacle to route around: twice, an agent blocked at spawn built a workaround,
# and both times the workaround wore an engineering costume convincing enough to
# survive review.
#
# The cheapest place to stop that is upstream of the refusal: do not put the
# command in the briefing. A denied command in a fenced block is an instruction
# to do the thing, and the fact that the harness will refuse it is not a reason
# to leave it there — it is the reason it is worth catching.
#
# GROUND TRUTH IS THE DENY LIST ITSELF, parsed from settings.json rather than
# restated here. A copy of a rule is a rule that drifts, and this suite exists
# because of rules that drifted from what they described. If the deny list cannot
# be parsed, or is empty, this check reports zero subjects and the runner errors
# — it does not quietly pass over a policy it could not read.
# shellcheck source=../../lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

ID="config-does-not-instruct-a-denied-command"
TITLE="No runnable block in the config runs a command the permission deny list blocks"
PROVENANCE="an agent blocked by a deny rule built a workaround twice; the workaround looked like engineering both times (seen on one project, repeatedly)"

check() {
  local v n scan f rel pat rc denied
  v="$(mktemp)"; scan="$(mktemp)"; denied="$(mktemp)"

  if ! command -v python3 >/dev/null 2>&1; then
    echo "SUBJECTS=0"
    echo "python3 is unavailable, so the deny list could not be parsed — not a pass"
    rm -f "$v" "$scan" "$denied"
    return 1
  fi

  python3 - "$CORPUS/.claude/settings.json" >"$denied" <<'PY'
import json, re, sys
try:
    with open(sys.argv[1]) as fh:
        cfg = json.load(fh)
except Exception:
    sys.exit(0)
for rule in cfg.get("permissions", {}).get("deny", []):
    m = re.match(r"Bash\((.*?)(:\*)?\)$", rule)
    if m and m.group(1).strip():
        print(m.group(1).strip())
PY

  n="$(grep -c . "$denied")"
  if [ "$n" -eq 0 ]; then
    echo "SUBJECTS=0"
    echo "no Bash deny rules could be read out of .claude/settings.json — the ground truth for this rule is missing"
    rm -f "$v" "$scan" "$denied"
    return 1
  fi

  while IFS= read -r f; do
    [ -n "$f" ] || continue
    rel="${f#"$CORPUS"/}"
    fenced_lines "$f" | sed "s|^|$rel: |" >>"$scan"
  done < <(config_files)

  while IFS= read -r pat; do
    [ -n "$pat" ] || continue
    grep -F -- "$pat" "$scan" | sed "s|^|instructs the denied command '$pat': |" >>"$v"
  done <"$denied"

  report_violations "Bash deny rules checked against every runnable line" "$n" "$v"
  rc=$?
  rm -f "$v" "$scan" "$denied"
  return $rc
}

break_it() {
  cat >>"$CORPUS/CLAUDE.md" <<'PROBE'

If the rebase gets messy, reset and republish the branch:

```bash
git push --force origin HEAD
```
PROBE
}
