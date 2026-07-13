#!/usr/bin/env bash
set -uo pipefail

repo_root="${1:-}"
package_id="${2:-}"
artifact_root="${3:-}"

if [ -z "$repo_root" ] || [ -z "$package_id" ] || [ -z "$artifact_root" ]; then
  echo "Usage: run-unity-validation.sh <repo-root> <package-id> <artifact-root>" >&2
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

runner_path="$repo_root/Packages/com.actionfit.ai-ci/Tools~/run_unity_package_tests.py"
preflight_path="$repo_root/Tools/AI/unity-package-ci/preflight-runner.sh"
package_access_path="$repo_root/Tools/AI/unity-package-ci/prepare-readonly-package-access.sh"
result_dir="$artifact_root/result"
mkdir -p "$artifact_root"

job_env_path="$artifact_root/package-access.env"
original_github_env="${GITHUB_ENV:-}"
trap 'rm -f "$job_env_path"' EXIT

write_infrastructure_result() {
  local code="$1"
  local message="$2"
  local source_log="$3"
  mkdir -p "$result_dir"
  if [ -f "$source_log" ]; then
    cp "$source_log" "$result_dir/unity.log"
  else
    printf '%s\n' "$message" > "$result_dir/unity.log"
  fi
  "$python_command" - "$runner_path" "$result_dir/result.json" "$result_dir" "$package_id" "$code" "$message" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

runner_path, output_path, result_dir, package_id, code, message = sys.argv[1:]
runner = Path(runner_path)
sys.path.insert(0, str(runner.parent))
spec = importlib.util.spec_from_file_location("actionfit_ci_workflow_runner", runner)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.failure_result(module.RunnerError(code, message))
result["packageId"] = package_id
result["resultDirectory"] = result_dir
result["artifacts"] = {
    "resultJson": output_path,
    "unityLog": str(Path(result_dir) / "unity.log"),
    "nunitXml": "",
    "shellLog": "",
}
Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

set +e
bash "$preflight_path" > "$artifact_root/preflight.log" 2>&1
preflight_status="$?"
set -e
cat "$artifact_root/preflight.log"
if [ "$preflight_status" -ne 0 ]; then
  write_infrastructure_result \
    "PACKAGE_CI_PREFLIGHT_FAILED" \
    "The unity-package-ci runner preflight failed." \
    "$artifact_root/preflight.log"
  exit 2
fi

set +e
GITHUB_ENV="$job_env_path" bash "$package_access_path" > "$artifact_root/package-access.log" 2>&1
package_access_status="$?"
set -e
cat "$artifact_root/package-access.log"
if [ "$package_access_status" -ne 0 ]; then
  write_infrastructure_result \
    "PACKAGE_CI_READ_ACCESS_FAILED" \
    "Read-only private package access preparation failed." \
    "$artifact_root/package-access.log"
  exit 2
fi

while IFS='=' read -r key value; do
  [ -n "$key" ] || continue
  export "$key=$value"
done < "$job_env_path"
if [ -n "$original_github_env" ]; then
  cat "$job_env_path" >> "$original_github_env"
fi

safe_package="$(printf '%s' "$package_id" | tr -c 'A-Za-z0-9._-' '_')"
run_id="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}-${safe_package}"
runner_temp="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
fixture_root_log="$artifact_root/fixture-root.log"
if ! fixture_root="$(mktemp -d "$runner_temp/afci.XXXXXX" 2> "$fixture_root_log")"; then
  write_infrastructure_result \
    "PACKAGE_CI_TEMP_ROOT_FAILED" \
    "Could not create the short Unity package CI temporary root." \
    "$fixture_root_log"
  exit 2
fi
export TMPDIR="$fixture_root"
export PACKAGE_CI_FIXTURE_ROOT="$fixture_root"
if [ -n "$original_github_env" ]; then
  printf 'PACKAGE_CI_FIXTURE_ROOT=%s\n' "$fixture_root" >> "$original_github_env"
fi

set +e
"$python_command" "$runner_path" \
  --package "$package_id" \
  --repo-root "$repo_root" \
  --run-id "$run_id" \
  --result-dir "$result_dir" \
  > "$artifact_root/runner-stdout.json" \
  2> "$artifact_root/runner-stderr.log"
runner_status="$?"
set -e
cat "$artifact_root/runner-stdout.json"
cat "$artifact_root/runner-stderr.log" >&2

if [ ! -f "$result_dir/result.json" ]; then
  write_infrastructure_result \
    "UNITY_RUNNER_RESULT_MISSING" \
    "The isolated Unity runner did not produce result.json." \
    "$artifact_root/runner-stderr.log"
  exit 2
fi

exit "$runner_status"
