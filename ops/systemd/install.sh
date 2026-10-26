#!/usr/bin/env bash
# Install the agent reaper as a systemd user timer. Writes two unit files and
# reloads systemd. It does NOT enable or start anything unless --enable is given.
#
#   ops/systemd/install.sh [--report-only] [--enable] [--dry-run]
#
# --report-only  install the service as `hx reap` (report only) instead of
#                `hx reap --close`; a safe first night.
# --enable       also run `systemctl --user enable --now agent-reaper.timer`.
# --dry-run      print the rendered units and the commands; change nothing.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
report_only=0; enable=0; dry=0
for arg in "$@"; do
  case "$arg" in
    --report-only) report_only=1 ;;
    --enable) enable=1 ;;
    --dry-run) dry=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

python=$(command -v python3)
# The timer runs without a login shell: keep the PATH that finds herdr, gh,
# git and docker now.
path_dirs=""
for tool in herdr gh git docker; do
  found=$(command -v "$tool" || true)
  [[ -n "$found" ]] || { echo "warning: $tool not on PATH" >&2; continue; }
  dir=$(dirname "$found")
  [[ ":$path_dirs:" == *":$dir:"* ]] || path_dirs="${path_dirs:+$path_dirs:}$dir"
done
path_dirs="${path_dirs:+$path_dirs:}/usr/local/bin:/usr/bin:/bin"

service=$(sed -e "s#@PATH@#$path_dirs#" -e "s#@PYTHON@#$python#" -e "s#@HX@#$repo/bin/hx#" \
  "$here/agent-reaper.service.in")
if (( report_only )); then
  service=${service/reap --close/reap}
fi

if (( dry )); then
  echo "# would write $unit_dir/agent-reaper.service"; echo "$service"
  echo "# would write $unit_dir/agent-reaper.timer"; cat "$here/agent-reaper.timer"
  echo "# would run: systemctl --user daemon-reload"
  (( enable )) && echo "# would run: systemctl --user enable --now agent-reaper.timer"
  exit 0
fi

mkdir -p "$unit_dir"
printf '%s\n' "$service" > "$unit_dir/agent-reaper.service"
cp "$here/agent-reaper.timer" "$unit_dir/agent-reaper.timer"
systemctl --user daemon-reload
echo "installed agent-reaper.service and agent-reaper.timer in $unit_dir"
if (( enable )); then
  systemctl --user enable --now agent-reaper.timer
  echo "enabled agent-reaper.timer"
else
  echo "not enabled; turn it on with: systemctl --user enable --now agent-reaper.timer"
fi
