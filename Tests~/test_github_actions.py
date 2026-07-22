#!/usr/bin/env python3
"""Regression tests for the GitHub Actions package-validation workflow."""

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
PLAN_SCRIPT = PACKAGE_SCRIPTS / "plan-package-validation.py"


class GitHubActionsWorkflowTests(unittest.TestCase):
    def test_project_assets_match_package_sources(self) -> None:
        self.assertEqual(PACKAGE_WORKFLOW.read_bytes(), PROJECT_WORKFLOW.read_bytes())
        for name in (
            "plan-package-validation.py",
            "run-static-validation.sh",
            "run-unity-validation.sh",
            "write-step-summary.py",
        ):
            self.assertEqual((PACKAGE_SCRIPTS / name).read_bytes(), (PROJECT_SCRIPTS / name).read_bytes())

    def test_workflow_is_read_only_advisory_and_uses_dedicated_self_hosted_runner_only(self) -> None:
        workflow = PACKAGE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("paths:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("runs-on: ubuntu-latest", workflow)
        self.assertNotIn("self_hosted_allowed", workflow)
        self.assertNotIn("actions/setup-python", workflow)
        self.assertEqual(5, workflow.count("runs-on: [self-hosted, macOS, unity-package-ci]"))
        self.assertNotIn("unity-mobile", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("github.event.pull_request.base.sha", workflow)
        self.assertIn("github.event.pull_request.head.sha", workflow)
        self.assertEqual(5, workflow.count("github.event.pull_request.head.repo.full_name == github.repository"))
        self.assertIn(
            "plan-validation:\n"
            "    name: Plan package validation\n"
            "    if: >-\n"
            "      github.event_name == 'workflow_dispatch' ||\n"
            "      github.event.pull_request.head.repo.full_name == github.repository",
            workflow,
        )
        self.assertIn(
            "advisory-result:\n"
            "    name: Advisory package validation result\n"
            "    if: >-\n"
            "      always() &&\n"
            "      (github.event_name == 'workflow_dispatch' ||\n"
            "      github.event.pull_request.head.repo.full_name == github.repository)",
            workflow,
        )
        self.assertEqual(2, workflow.count("fromJSON(needs.plan-validation.outputs.packages)"))
        self.assertEqual(2, workflow.count("fail-fast: false"))
        self.assertEqual(2, workflow.count("max-parallel: 4"))
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", workflow)
        self.assertIn("advisory-result:\n    name: Advisory package validation result", workflow)
        self.assertEqual(1, workflow.count("name: Advisory package validation result"))
        self.assertIn("if: always()", workflow)
        self.assertIn("ai-doc-validation:", workflow)
        self.assertIn("name: AI documentation contract", workflow)
        self.assertIn("AI_PACKAGE_VERSION_BASE_REF: ${{ needs.plan-validation.outputs.base_ref }}", workflow)
        self.assertIn("run: python3 Tools/AI/validate_ai_docs.py", workflow)
        self.assertIn(
            "needs: [plan-validation, ai-doc-validation, static-validation, unity-validation]",
            workflow,
        )
        self.assertIn("AI_DOC_RESULT: ${{ needs.ai-doc-validation.result }}", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertEqual(3, workflow.count("continue-on-error: true"))
        self.assertIn(
            "- name: Upload package plan artifact\n"
            "        if: always()\n"
            "        continue-on-error: true\n"
            "        uses: actions/upload-artifact@v4",
            workflow,
        )
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

    def test_pull_request_plan_detects_only_changed_actionfit_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            base = self.create_planner_repository(repo)
            (repo / "Packages/com.actionfit.alpha/README.md").write_text("alpha changed\n", encoding="utf-8")
            (repo / "Packages/com.actionfit.beta/README.md").write_text("beta changed\n", encoding="utf-8")
            (repo / "Docs/notes.md").write_text("not a package\n", encoding="utf-8")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "change two packages")

            completed, result, github_outputs = self.run_planner(repo, "pull_request", base_ref=base)

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertEqual(["com.actionfit.alpha", "com.actionfit.beta"], result["packages"])
            self.assertIn('packages=["com.actionfit.alpha","com.actionfit.beta"]', github_outputs)
            self.assertIn("package_count=2", github_outputs)
            self.assertIn(f"base_ref={base}", github_outputs)

    def test_pull_request_plan_fast_succeeds_without_package_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            base = self.create_planner_repository(repo)
            (repo / "Docs/notes.md").write_text("docs only\n", encoding="utf-8")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "docs only")

            completed, result, github_outputs = self.run_planner(repo, "pull_request", base_ref=base)

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertEqual([], result["packages"])
            self.assertEqual("NO_ACTIONFIT_PACKAGE_CHANGES", result["code"])
            self.assertIn("packages=[]", github_outputs)
            self.assertIn("package_count=0", github_outputs)

    def test_pull_request_plan_skips_deleted_package_without_head_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            base = self.create_planner_repository(repo)
            for path in (repo / "Packages/com.actionfit.alpha").iterdir():
                path.unlink()
            (repo / "Packages/com.actionfit.alpha").rmdir()
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-m", "delete package")

            completed, result, _ = self.run_planner(repo, "pull_request", base_ref=base)

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertEqual([], result["packages"])
            self.assertEqual("NO_ACTIONFIT_PACKAGE_CHANGES", result["code"])

    def test_pull_request_plan_maps_package_folder_meta_to_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            base = self.create_planner_repository(repo)
            (repo / "Packages/com.actionfit.alpha.meta").write_text(
                "fileFormatVersion: 2\nguid: 1234567890abcdef1234567890abcdef\n",
                encoding="utf-8",
            )
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "add package folder meta")

            completed, result, _ = self.run_planner(repo, "pull_request", base_ref=base)

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertEqual(["com.actionfit.alpha"], result["packages"])

    def test_manual_plan_keeps_selected_package_and_optional_base_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            base = self.create_planner_repository(repo)

            completed, result, github_outputs = self.run_planner(
                repo,
                "workflow_dispatch",
                package_id="com.actionfit.beta",
                base_ref=base,
            )

            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertEqual("manual", result["mode"])
            self.assertEqual(["com.actionfit.beta"], result["packages"])
            self.assertIn("package_count=1", github_outputs)

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
                            "nunit": {
                                "total": 2,
                                "passed": 1,
                                "failed": 1,
                                "skipped": 0,
                                "failedTests": [
                                    {"name": "Target.Tests.fails", "message": "Expected true but was false"}
                                ],
                            },
                        },
                        "phases": [{"name": "unity", "status": "failed", "durationSeconds": 1.2}],
                        "diagnostics": [
                            {"severity": "error", "code": "PACKAGE_TESTS_FAILED", "message": "one failed"}
                        ],
                        "logTail": ["[nunit] Target.Tests.fails: Expected true but was false"],
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
            self.assertIn("Target.Tests.fails", summary)
            self.assertIn("Failure log tail", summary)

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

    @staticmethod
    def git(repo: Path, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stdout + completed.stderr)
        return completed.stdout.strip()

    @classmethod
    def create_planner_repository(cls, repo: Path) -> str:
        repo.mkdir(parents=True)
        cls.git(repo, "init")
        cls.git(repo, "config", "user.email", "ai-ci@example.invalid")
        cls.git(repo, "config", "user.name", "AI CI Tests")
        for package_id in ("com.actionfit.alpha", "com.actionfit.beta"):
            package_root = repo / "Packages" / package_id
            package_root.mkdir(parents=True)
            (package_root / "package.json").write_text(
                json.dumps({"name": package_id, "version": "1.0.0"}) + "\n",
                encoding="utf-8",
            )
            (package_root / "README.md").write_text(f"{package_id}\n", encoding="utf-8")
        (repo / "Docs").mkdir()
        (repo / "Docs/notes.md").write_text("base\n", encoding="utf-8")
        cls.git(repo, "add", ".")
        cls.git(repo, "commit", "-m", "base")
        return cls.git(repo, "rev-parse", "HEAD")

    @staticmethod
    def run_planner(
        repo: Path,
        event: str,
        *,
        package_id: str = "",
        base_ref: str = "",
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object], str]:
        result_path = repo.parent / "plan-result.json"
        github_output = repo.parent / "github-output"
        completed = subprocess.run(
            [
                sys.executable,
                str(PLAN_SCRIPT),
                "--event",
                event,
                "--repo-root",
                str(repo),
                "--package",
                package_id,
                "--base-ref",
                base_ref,
                "--output",
                str(result_path),
                "--github-output",
                str(github_output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        outputs = github_output.read_text(encoding="utf-8") if github_output.exists() else ""
        return completed, result, outputs


if __name__ == "__main__":
    unittest.main()
