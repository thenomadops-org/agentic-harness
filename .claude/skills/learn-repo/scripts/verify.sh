#!/usr/bin/env bash
# verify.sh <folder> [stray-name]
# Validate a vault folder ingested by learn-repo: dangling wiki-links, the
# 8-field frontmatter contract, the ↑ Up footer convention, graph-JSON validity,
# and (optionally) stray references to an old name after a rename.
set -uo pipefail
# Vault root: $VAULT env wins; else self-locate — this script lives at
# <vault>/.claude/skills/learn-repo/scripts/, so four levels up is the vault.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
VAULT="${VAULT:-$(cd "$SCRIPT_DIR/../../../.." && pwd -P)}"
FOLDER="${1:?usage: verify.sh <folder> [stray-name]}"
STRAY="${2:-}"
cd "$VAULT" 2>/dev/null || { echo "vault not found: $VAULT"; exit 2; }
[ -d "$FOLDER" ] || { echo "folder not found: $FOLDER"; exit 2; }
fail=0

# 1. Dangling wiki-links from the folder.
# Strip fenced code blocks first (```...```), so shell `[[ ... ]]` tests and other
# code inside fences aren't mistaken for Obsidian wiki-links (Obsidian doesn't
# linkify inside code fences anyway).
find "$FOLDER" -name '*.md' -exec awk '/^[[:space:]>]*```/{f=!f; next} !f' {} + 2>/dev/null \
  | sed 's/`[^`]*`//g' \
  | grep -oE '\[\[[^]]+\]\]' \
  | sed -E 's/\[\[//; s/\]\]//; s/\\?\|.*$//; s/#.*$//; s/\.(md|canvas)$//' | grep -v '^[[:space:]]*$' | sort -u > /tmp/lr_targets.txt
# Note list includes .canvas files, and both extensions are stripped, so links
# written with an explicit extension ([[CLAUDE.md]], [[X.canvas|alias]]) resolve.
find . \( -name '*.md' -o -name '*.canvas' \) | sed -E 's#.*/##; s/\.(md|canvas)$//' | sort -u > /tmp/lr_notes.txt
dangling="$(comm -23 /tmp/lr_targets.txt /tmp/lr_notes.txt)"
if [ -n "$dangling" ]; then
  echo "✗ DANGLING LINKS:"; echo "$dangling" | sed 's/^/    /'; fail=1
else echo "✓ no dangling links"; fi

# 2. 8-field frontmatter on every note
missing=""
while IFS= read -r f; do
  n=$(awk 'BEGIN{c=0} /^---$/{c++; next} c==1' "$f" \
      | grep -cE '^(title|tags|type|domain|repo|status|color|created):')
  [ "$n" -ge 8 ] || missing="${missing}
    ${f} (fields=${n})"
done < <(find "$FOLDER" -name '*.md')
if [ -n "$missing" ]; then echo "✗ INCOMPLETE FRONTMATTER:${missing}"; fail=1
else echo "✓ all notes have 8 frontmatter fields"; fi

# 3. Footer convention (warn only; only if the folder uses ↑ Up footers)
if grep -rq "↑ Up:" "$FOLDER"/ 2>/dev/null; then
  nofoot=""
  while IFS= read -r f; do
    grep -q "↑ Up:" "$f" || nofoot="${nofoot}
    ${f}"
  done < <(find "$FOLDER" -name '*.md' ! -name '*-MOC.md')
  [ -n "$nofoot" ] && echo "⚠ notes missing ↑ Up footer:${nofoot}" || echo "✓ footers present"
fi

# 4. graph JSON valid, IF present. A fresh vault has no live .obsidian/graph.json
# until Obsidian runs, and no scripts/graph.default.json until set-graph-colors.py
# runs — absence is fine, only malformed JSON fails.
for gj in scripts/graph.default.json .obsidian/graph.json; do
  [ -f "$gj" ] || continue
  if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$gj" 2>/dev/null; then
    echo "✓ $gj valid JSON"
  else echo "✗ $gj invalid JSON"; fail=1; fi
done

# 5. stray old-name references (optional; pass a name after a rename)
if [ -n "$STRAY" ]; then
  hits="$(grep -rn "$STRAY" . --include='*.md' --include='*.canvas' 2>/dev/null)"
  if [ -n "$hits" ]; then echo "✗ STRAY '$STRAY' refs:"; echo "$hits" | sed 's/^/    /'; fail=1
  else echo "✓ no stray '$STRAY' refs"; fi
fi

# 6. Canvas file-paths referencing this folder resolve
python3 - "$FOLDER" <<'PY'
import json, os, sys, glob
folder = sys.argv[1]
miss = []
for c in glob.glob('**/*.canvas', recursive=True):
    try: d = json.load(open(c))
    except Exception: continue
    for n in d.get('nodes', []):
        fp = n.get('file', '')
        if fp.startswith(folder + '/') and not os.path.exists(fp):
            miss.append(fp)
print("✗ CANVAS MISSING: " + ", ".join(miss) if miss else "✓ canvas paths resolve")
sys.exit(1 if miss else 0)
PY
[ $? -ne 0 ] && fail=1

echo
[ "$fail" -eq 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $fail
