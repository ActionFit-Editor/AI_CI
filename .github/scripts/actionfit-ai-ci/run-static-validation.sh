#!/usr/bin/env bash
set -uo pipefail

repo_root="${1:-}"
package_id="${2:-}"
base_ref="${3:-}"
result_dir="${4:-}"

if [ -z "$repo_root" ] || [ -z "$package_id" ] || [ -z "$result_dir" ]; then
  echo "Usage: run-static-validation.sh <repo-root> <package-id> <base-ref> <result-dir>" >&2
  exit 2
fi

resolve_python() {
  local candidate
  for candidate in "${PACKAGE_CI_PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if ! python_command="$(resolve_python)"; then
  echo "A working Python 3 executable was not found." >&2
  exit 2
fi

mkdir -p "$result_dir"
cli_path="$repo_root/Packages/com.actionfit.ai-ci/Tools~/ai_ci.py"
arguments=(
  "$cli_path"
  --package "$package_id"
  --repo-root "$repo_root"
  --format summary
  --output "$result_dir/result.json"
)
if [ -n "$base_ref" ]; then
  arguments+=(--base-ref "$base_ref")
fi

set +e
"$python_command" "${arguments[@]}" 2>&1 | tee "$result_dir/console.log"
status="${PIPESTATUS[0]}"
set -e
exit "$status"
