#!/usr/bin/env bash
# from factory-seed@UNSTAMPED — vendored; upstream is the new-project skill's seed/tier0.
# Tests for .claude/hooks/block-test-weakening.sh.
#
# WHY THIS EXISTS. A hook that fails open is a guard that examined nothing,
# which is the defect an overnight audit on the source project found four of at
# once. So the suite is
# built around MUST-BLOCK cases: for every shape the hook is supposed to refuse,
# there is an assertion that it exits 2, and for every shape it must leave alone
# there is an assertion that it exits 0. A change that makes the hook permissive
# turns the first group red; a change that makes it over-broad turns the second
# red. Neither can pass by accident.
#
# Usage: .claude/hooks/block-test-weakening.test.sh   (exit 0 = all cases pass)

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/block-test-weakening.sh"
[ -x "$HOOK" ] || { echo "not executable: $HOOK"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t
git -C "$REPO" config user.name t

passed=0
failed=0
OUT=""
RC=0

# --- fixtures ---------------------------------------------------------------
mkdir -p "$REPO/pkg" "$REPO/scripts" "$REPO/src/test/kotlin" "$REPO/lib" "$REPO/.factory"

# The hook reads its vocabulary from gate config rather than carrying it inline,
# so the fixture repo needs the same file a real install lays down. Copied from
# the seed rather than retyped: a test with its own private copy of the config
# proves the hook works against a config nobody ships.
SEED_CONFIG="$HERE/../../.factory/test-vocabulary.conf"
[ -f "$SEED_CONFIG" ] || { echo "missing seed config: $SEED_CONFIG"; exit 1; }
cp "$SEED_CONFIG" "$REPO/.factory/test-vocabulary.conf"

cat >"$REPO/pkg/thing_test.go" <<'EOF'
package pkg

import "testing"

func TestThing(t *testing.T) {
	if got := Thing(); got != 1 {
		t.Fatalf("want 1, got %d", got)
	}
	if other := Other(); other != 2 {
		t.Errorf("want 2, got %d", other)
	}
}
EOF

cat >"$REPO/src/test/kotlin/ThingTest.kt" <<'EOF'
class ThingTest {
    @Test fun works() {
        assertEquals(1, thing())
        assertTrue(other())
    }
}
EOF

cat >"$REPO/scripts/gate.test.sh" <<'EOF'
#!/usr/bin/env bash
run "$SCRIPT" --flag
check "the flag is honoured" 0
contains "and says so" "honoured"
EOF

cat >"$REPO/lib/thing.go" <<'EOF'
package lib

func Thing() int { return 1 }
EOF

# --- harness ----------------------------------------------------------------
# The payload is built by python3 so that source text containing quotes,
# backticks and `$` cannot corrupt the JSON — the reason payload.py exists at
# all applies just as much to the test that drives it.
payload() { # payload <tool> <cwd> <json-tool_input-fragment...>
	python3 - "$@" <<'PY'
import json, sys
tool, cwd = sys.argv[1], sys.argv[2]
ti = {}
for pair in sys.argv[3:]:
    k, _, v = pair.partition("=")
    ti[k] = v
print(json.dumps({
    "hook_event_name": "PreToolUse",
    "tool_name": tool,
    "cwd": cwd,
    "transcript_path": "",
    "tool_input": ti,
}))
PY
}

run_hook() { # run_hook <payload-json> [ENV=VAL ...]
	local body="$1"; shift
	OUT="$(printf '%s' "$body" | env "$@" "$HOOK" 2>&1)"
	RC=$?
}

check() { # check <desc> <expected-rc>
	local desc="$1" want="$2"
	if [ "$RC" = "$want" ]; then
		passed=$((passed + 1)); printf 'PASS  %s (exit %s)\n' "$desc" "$RC"
	else
		failed=$((failed + 1)); printf 'FAIL  %s — wanted exit %s, got %s\n' "$desc" "$want" "$RC"
		printf '%s\n' "$OUT" | sed 's/^/        | /'
	fi
}

contains() { # contains <desc> <needle>
	case "$OUT" in
	*"$2"*) passed=$((passed + 1)); printf 'PASS  %s\n' "$1" ;;
	*) failed=$((failed + 1)); printf 'FAIL  %s — output lacked %s\n' "$1" "$2"
	   printf '%s\n' "$OUT" | sed 's/^/        | /' ;;
	esac
}

echo "=== block-test-weakening.sh — MUST-BLOCK cases first ==="

# 1. the whole point: an Edit that deletes an assertion from an existing test.
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=	if other := Other(); other != 2 {
		t.Errorf("want 2, got %d", other)
	}' \
	'new_string=	_ = Other()')"
check "MUST-BLOCK: Edit removes an assertion from an existing _test.go" 2
contains "and names the file" "pkg/thing_test.go"
contains "and states the route to approval, not just the refusal" "ALLOW_TEST_WEAKENING"
contains "and offers fixing the code as route 1" "Fix the code under test instead"

# 2. disabling a test is deleting it with extra steps.
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=func TestThing(t *testing.T) {' \
	'new_string=func TestThing(t *testing.T) {
	t.Skip("flaky")')"
check "MUST-BLOCK: Edit introduces t.Skip into an existing test" 2
contains "and says which marker count moved" "skip markers before"

run_hook "$(payload Edit "$REPO" \
	file_path=src/test/kotlin/ThingTest.kt \
	'old_string=    @Test fun works() {' \
	'new_string=    @Ignore @Test fun works() {')"
check "MUST-BLOCK: Edit introduces @Ignore into a Kotlin test" 2

# 3. Write is the same defect through a different tool: its old side is disk.
run_hook "$(payload Write "$REPO" \
	file_path=pkg/thing_test.go \
	'content=package pkg

import "testing"

func TestThing(t *testing.T) {
	_ = Thing()
}')"
check "MUST-BLOCK: Write over an existing test file with fewer assertions" 2

# 4. this repo's own shell suites use check/contains as the assertion vocabulary.
run_hook "$(payload Edit "$REPO" \
	file_path=scripts/gate.test.sh \
	'old_string=check "the flag is honoured" 0
contains "and says so" "honoured"' \
	'new_string=true')"
check "MUST-BLOCK: Edit removes check/contains lines from a .test.sh" 2

# 5. Bash is the evasion route an agent is actively nudged toward.
run_hook "$(payload Bash "$REPO" 'command=rm -f pkg/thing_test.go')"
check "MUST-BLOCK: Bash rm of an existing test file" 2
contains "and quotes the command back" "rm -f pkg/thing_test.go"

run_hook "$(payload Bash "$REPO" "command=sed -i 's/t.Fatalf/_ = fmt.Sprintf/' pkg/thing_test.go")"
check "MUST-BLOCK: Bash sed -i on an existing test file" 2

run_hook "$(payload Bash "$REPO" 'command=: > pkg/thing_test.go')"
check "MUST-BLOCK: Bash truncating redirect onto an existing test file" 2

run_hook "$(payload Bash "$REPO" 'command=git rm pkg/thing_test.go')"
check "MUST-BLOCK: Bash git rm of an existing test file" 2

# 6. anti-vacuity: a payload the hook cannot read must REFUSE, never allow.
OUT="$(printf 'this is not json' | "$HOOK" 2>&1)"; RC=$?
check "MUST-BLOCK: an unparseable payload refuses rather than passing" 2
contains "and says why it refused" "not JSON"

# 7. a bypass that is not a real ticket key is not a bypass.
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=		t.Errorf("want 2, got %d", other)' \
	'new_string=		_ = other')" ALLOW_TEST_WEAKENING=yes-please
check "MUST-BLOCK: ALLOW_TEST_WEAKENING=<not a ticket> does not open the gate" 2

echo
echo "=== cases the hook must LEAVE ALONE (over-blocking is the other failure) ==="

run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=	if got := Thing(); got != 1 {' \
	'new_string=	t.Helper()
	if got := Thing(); got != 1 {')"
check "ALLOW: an Edit that adds to an existing test" 0

run_hook "$(payload Write "$REPO" \
	file_path=pkg/brand_new_test.go \
	'content=package pkg
func TestNew(t *testing.T) { t.Fatal("x") }')"
check "ALLOW: writing a test file that does not exist yet" 0

run_hook "$(payload Edit "$REPO" \
	file_path=lib/thing.go \
	'old_string=func Thing() int { return 1 }' \
	'new_string=func Thing() int { return 2 }')"
check "ALLOW: an Edit to a non-test file, even one that drops assertions" 0

run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=	if got := Thing(); got != 1 {
		t.Fatalf("want 1, got %d", got)
	}' \
	'new_string=	if actual := Thing(); actual != 1 {
		t.Fatalf("want 1, got %d", actual)
	}')"
check "ALLOW: a rename inside a test that keeps the assertion count" 0

run_hook "$(payload Bash "$REPO" 'command=grep -n assert pkg/thing_test.go > /tmp/out.txt')"
check "ALLOW: a Bash read of a test file that happens to redirect elsewhere" 0

run_hook "$(payload Bash "$REPO" 'command=rm -rf build/test-results/iosSimulatorArm64Test')"
check "ALLOW: a Bash rm of build artefacts that are not tracked test sources" 0

run_hook "$(payload Bash "$REPO" 'command=go test ./... -count=1')"
check "ALLOW: running the tests is not weakening them" 0

run_hook "$(payload Edit "$REPO" file_path=pkg/thing_test.go)"
check "ALLOW: a payload with no old/new text has nothing to compare" 0

echo
echo "=== the bypass, and the accountability it carries ==="

run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=		t.Errorf("want 2, got %d", other)' \
	'new_string=		_ = other')" ALLOW_TEST_WEAKENING=PROJ-123
check "ALLOW: a real ticket key in ALLOW_TEST_WEAKENING opens the gate" 0
contains "and the bypass is not silent — it names the ticket" "PROJ-123"
contains "and it tells the model what it now owes the PR body" "OWE the PR body"

run_hook "$(payload Bash "$REPO" 'command=rm -f pkg/thing_test.go')" ALLOW_TEST_WEAKENING=#456
check "ALLOW: the bypass works for the Bash route too" 0

echo
echo "=== the vocabulary is READ from .factory/test-vocabulary.conf, not baked in ==="

# The point of the config extraction: change the config, change the verdict.
# Without this case the config file could be ignored entirely and every other
# assertion above would still pass, which is the shape of a knob that does
# nothing.
cat >"$REPO/pkg/spec_thing.rb" <<'EOF'
describe "thing" do
  assert_equal 1, thing
  assert_equal 2, other
end
EOF
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/spec_thing.rb \
	'old_string=  assert_equal 2, other' \
	'new_string=  other')"
check "ALLOW: a language the vocabulary does not name is not a test file" 0

printf "TEST_NAME_RE='_spec\\.rb\$'\n" >>"$REPO/.factory/test-vocabulary.conf"
mv "$REPO/pkg/spec_thing.rb" "$REPO/pkg/thing_spec.rb"
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_spec.rb \
	'old_string=  assert_equal 2, other' \
	'new_string=  other')"
check "MUST-BLOCK: adding the pattern to the config makes the same edit a violation" 2
cp "$SEED_CONFIG" "$REPO/.factory/test-vocabulary.conf"

echo
echo "=== cannot-check REFUSES: a broken config is not an unconfigured repo ==="

# This is the anti-vacuity case for the config itself. Every assertion above
# would still pass if a missing config silently disabled the hook — the suite
# would be green and the guard would be off.
mv "$REPO/.factory/test-vocabulary.conf" "$TMP/stashed.conf"
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=		t.Errorf("want 2, got %d", other)' \
	'new_string=		_ = other')"
check "MUST-BLOCK: the config is missing, so the hook cannot check and refuses" 2
contains "and names the file it wanted" ".factory/test-vocabulary.conf"
contains "and states a route to approval" "ROUTE TO APPROVAL"
contains "and says why refusing beats allowing" "BROKEN INSTALL"
mv "$TMP/stashed.conf" "$REPO/.factory/test-vocabulary.conf"

# A config present but emptied out is the same defect wearing a disguise: the
# file exists, the install looks complete, and no file counts as a test.
cp "$REPO/.factory/test-vocabulary.conf" "$TMP/stashed.conf"
printf "TEST_NAME_RE=''\nTEST_BASENAME_RE=''\nTEST_DIR_RE=''\n" >>"$REPO/.factory/test-vocabulary.conf"
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=		t.Errorf("want 2, got %d", other)' \
	'new_string=		_ = other')"
check "MUST-BLOCK: a config with no test-path patterns is vacuous, not permissive" 2
contains "and says NO file would count as a test" "NO file counts as a test"
cp "$TMP/stashed.conf" "$REPO/.factory/test-vocabulary.conf"

printf "ASSERT_RE=''\nSHELL_ASSERT_RE=''\n" >>"$REPO/.factory/test-vocabulary.conf"
run_hook "$(payload Edit "$REPO" \
	file_path=pkg/thing_test.go \
	'old_string=		t.Errorf("want 2, got %d", other)' \
	'new_string=		_ = other')"
check "MUST-BLOCK: a config with no assertion vocabulary is vacuous too" 2
cp "$TMP/stashed.conf" "$REPO/.factory/test-vocabulary.conf"

# Not-configured must not print the same as broken: outside a git worktree there
# is no repo root to key on, and the hook allows silently rather than demanding
# a config that has no home.
OUT="$(payload Edit "$TMP" file_path=pkg/thing_test.go 'old_string=assert(1)' 'new_string=x' | "$HOOK" 2>&1)"; RC=$?
check "ALLOW: outside a git worktree there is nothing to key on" 0

echo
printf '=== %s passed, %s failed ===\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
