#!/usr/bin/env python3
"""Regression tests for the manual GitHub Actions package-validation workflow."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_WORKFLOW = PACKAGE_ROOT / "WorkflowTemplates/actionfit-package-validation.yml"
PROJECT_WORKFLOW = REPO_ROOT / ".github/workflows/actionfit-package-validation.yml"
PACKAGE_SCRIPTS = PACKAGE_ROOT / ".github/scripts/actionfit-ai-ci"
PROJECT_SCRIPTS = REPO_ROOT / ".github/scripts/actionfit-ai-ci"


class GitHubActionsWorkflowTests(unittest.TestCase):
    def test_project_assets_match_package_sources(self) -> None:
        self.assertEqual(PACKAGE_WORKFLOW.read_bytes(), PROJECT_WORKFLOW.read_bytes())
        for name in ("run-static-validation.sh", "run-unity-validation.sh", "write-step-summary.py"):
            self.assertEqual((PACKAGE_SCRIPTS / name).read_bytes(), (PROJECT_SCRIPTS / name).read_bytes())

    def test_workflow_is_manual_read_only_and_uses_separate_runners(self) -> None:
        workflow = PACKAGE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("runs-on: [self-hosted, macOS, unity-package-ci]", workflow)
        self.assertNotIn("unity-mobile", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertEqual(2, workflow.count("continue-on-error: true"))
        self.assertIn(
            "- name: Upload static validation artifacts\n"
            "        if: always()\n"
            "        continue-on-error: true\n"
            "        uses: actions/upload-artifact@v4",
            workflow,
        )
        self.assertIn(
            "- name: Upload Unity validation artifacts\n"
            "        if: always()\n"
            "        continue-on-error: true\n"
            "        uses: actions/upload-artifact@v4",
            workflow,
        )

    def test_step_summary_renders_unity_counts_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            summary_path = root / "summary.md"
            result_path.write_text(
                json.dumps(
                    {
                        "success": False,
                        "packageId": "com.actionfit.target",
                        "code": "PACKAGE_TESTS_FAILED",
                        "message": "tests failed",
                        "summary": {
                            "mode": "editmode",
                            "nunit": {"total": 2, "passed": 1, "failed": 1, "skipped": 0},
                        },
                        "phases": [{"name": "unity", "status": "failed", "durationSeconds": 1.2}],
                        "diagnostics": [
                            {"severity": "error", "code": "PACKAGE_TESTS_FAILED", "message": "one failed"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_SCRIPTS / "write-step-summary.py"),
                    "--title",
                    "Unity validation",
                    "--result",
                    str(result_path),
                    "--summary-file",
                    str(summary_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("❌ failed", summary)
            self.assertIn("1/2 passed", summary)
            self.assertIn("PACKAGE_TESTS_FAILED", summary)

    def test_unity_wrapper_writes_shared_shape_when_preflight_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            artifacts = Path(directory) / "artifacts"
            self.write_fake_runner(repo)
            self.write_script(repo / "Tools/AI/unity-package-ci/preflight-runner.sh", "exit 7\n")
            self.write_script(repo / "Tools/AI/unity-package-ci/prepare-readonly-package-access.sh", "exit 0\n")

            completed = subprocess.run(
                [
                    "bash",
                    str(PACKAGE_SCRIPTS / "run-unity-validation.sh"),
                    str(repo),
                    "com.actionfit.target",
                    str(artifacts),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PACKAGE_CI_PYTHON": sys.executable},
            )

            self.assertEqual(2, completed.returncode)
            result = json.loads((artifacts / "result/result.json").read_text(encoding="utf-8"))
            self.assertEqual("PACKAGE_CI_PREFLIGHT_FAILED", result["code"])
            self.assertEqual("com.actionfit.target", result["packageId"])
            self.assertTrue((artifacts / "result/unity.log").is_file())

    def test_unity_wrapper_exports_controlled_fixture_root_for_always_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            artifacts = root / "artifacts"
            runner_temp = root / "runner-temp"
            github_env = root / "github-env"
            runner_temp.mkdir()
            self.write_success_runner(repo)
            self.write_script(repo / "Tools/AI/unity-package-ci/preflight-runner.sh", "exit 0\n")
            self.write_script(
                repo / "Tools/AI/unity-package-ci/prepare-readonly-package-access.sh",
                'printf "PACKAGE_CI_TOKEN_FILE=/tmp/read-only-token\\n" >> "$GITHUB_ENV"\n',
            )

            completed = subprocess.run(
                [
                    "bash",
                    str(PACKAGE_SCRIPTS / "run-unity-validation.sh"),
                    str(repo),
                    "com.actionfit.target",
                    str(artifacts),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PACKAGE_CI_PYTHON": sys.executable,
                    "GITHUB_ENV": str(github_env),
                    "RUNNER_TEMP": str(runner_temp),
                    "GITHUB_RUN_ID": "123",
                    "GITHUB_RUN_ATTEMPT": "2",
                },
            )

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            fixture_lines = [
                line.split("=", 1)[1]
                for line in github_env.read_text(encoding="utf-8").splitlines()
                if line.startswith("PACKAGE_CI_FIXTURE_ROOT=")
            ]
            self.assertEqual(1, len(fixture_lines))
            fixture_root = Path(fixture_lines[0])
            self.assertEqual(runner_temp, fixture_root.parent)
            self.assertTrue(fixture_root.name.startswith("afci."), fixture_root)
            legacy_fixture_root = runner_temp / "actionfit-unity-package-ci-123-2-com.actionfit.target"
            self.assertLess(len(str(fixture_root)), len(str(legacy_fixture_root)))
            self.assertIn(f"PACKAGE_CI_FIXTURE_ROOT={fixture_root}", github_env.read_text(encoding="utf-8"))
            captured = json.loads((artifacts / "captured-environment.json").read_text(encoding="utf-8"))
            self.assertEqual(str(fixture_root), captured["TMPDIR"])
            self.assertEqual(str(fixture_root), captured["PACKAGE_CI_FIXTURE_ROOT"])

    @staticmethod
    def write_script(path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")

    @staticmethod
    def write_fake_runner(repo: Path) -> None:
        path = repo / "Packages/com.actionfit.ai-ci/Tools~/run_unity_package_tests.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """
class RunnerError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.exit_code = 2

def failure_result(error):
    return {
        "schemaVersion": "1.0",
        "tool": "actionfit-ai-ci-unity-package-tests",
        "runId": "",
        "packageId": "",
        "success": False,
        "exitCode": error.exit_code,
        "code": error.code,
        "message": str(error),
        "phases": [],
        "summary": {},
        "artifacts": {},
        "diagnostics": [],
        "logTail": [],
    }
""".lstrip(),
            encoding="utf-8",
        )

    @staticmethod
    def write_success_runner(repo: Path) -> None:
        path = repo / "Packages/com.actionfit.ai-ci/Tools~/run_unity_package_tests.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """
import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--package")
parser.add_argument("--repo-root")
parser.add_argument("--run-id")
parser.add_argument("--result-dir")
arguments = parser.parse_args()
result_dir = Path(arguments.result_dir)
result_dir.mkdir(parents=True, exist_ok=True)
result = {
    "schemaVersion": "1.0",
    "tool": "actionfit-ai-ci-unity-package-tests",
    "runId": arguments.run_id,
    "packageId": arguments.package,
    "success": True,
    "exitCode": 0,
    "code": "PACKAGE_VALIDATION_PASSED",
    "message": "passed",
    "phases": [],
    "summary": {},
    "artifacts": {},
    "diagnostics": [],
    "logTail": [],
}
(result_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
artifact_root = result_dir.parent
(artifact_root / "captured-environment.json").write_text(
    json.dumps({"TMPDIR": os.environ.get("TMPDIR"), "PACKAGE_CI_FIXTURE_ROOT": os.environ.get("PACKAGE_CI_FIXTURE_ROOT")}),
    encoding="utf-8",
)
print(json.dumps(result))
""".lstrip(),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
