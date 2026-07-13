#!/usr/bin/env python3
"""Regression tests for the isolated Unity package test runner."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = PACKAGE_ROOT / "Tools~"
CLI_PATH = TOOLS_ROOT / "run_unity_package_tests.py"
sys.path.insert(0, str(TOOLS_ROOT))
SPEC = importlib.util.spec_from_file_location("actionfit_run_unity_package_tests", CLI_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class UnityPackageTestRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "repo"
        self.package = self.repo / "Packages/com.actionfit.target"
        self.package.mkdir(parents=True)
        (self.repo / "ProjectSettings").mkdir()
        (self.repo / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.2.6f2\n"
            "m_EditorVersionWithRevision: 6000.2.6f2 (4a4dcaec6541)\n",
            encoding="utf-8",
        )
        (self.repo / "Packages/manifest.json").write_text(
            json.dumps({"dependencies": {"com.unity.test-framework": "1.6.0"}}),
            encoding="utf-8",
        )
        (self.package / "package.json").write_text(
            json.dumps({"name": "com.actionfit.target", "version": "1.0.0", "dependencies": {}}),
            encoding="utf-8",
        )
        self.unity = self.root / ("Unity.exe" if os.name == "nt" else "Unity")
        self.unity.write_text("placeholder", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def arguments(self, **overrides: object) -> argparse.Namespace:
        values = {
            "package": "com.actionfit.target",
            "repo_root": str(self.repo),
            "unity_executable": str(self.unity),
            "run_id": "test-run",
            "result_dir": str(self.root / "results"),
            "timeout_seconds": 30,
            "keep_project": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def write_test_assembly(self, name: str = "com.actionfit.target.Tests.Editor") -> Path:
        path = self.package / "Tests/Editor/com.actionfit.target.Tests.Editor.asmdef"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name}), encoding="utf-8")
        return path

    def test_discovers_only_editor_test_assembly_names(self) -> None:
        self.write_test_assembly("Target.EditorTests")
        runtime = self.package / "Tests/Runtime/RuntimeTests.asmdef"
        runtime.parent.mkdir(parents=True)
        runtime.write_text(json.dumps({"name": "Target.RuntimeTests"}), encoding="utf-8")

        self.assertEqual(["Target.EditorTests"], RUNNER.discover_test_assemblies(self.package))

    def test_invalid_editor_asmdef_is_a_package_failure(self) -> None:
        path = self.write_test_assembly()
        path.write_text("not json", encoding="utf-8")

        with self.assertRaises(RUNNER.RunnerError) as context:
            RUNNER.discover_test_assemblies(self.package)

        self.assertEqual("PACKAGE_TEST_ASMDEF_INVALID", context.exception.code)
        self.assertEqual(1, context.exception.exit_code)

    def test_unity_command_switches_between_compile_only_and_editmode(self) -> None:
        compile_command = RUNNER.build_unity_command(
            self.unity, self.root / "fixture", self.root / "unity.log", [], self.root / "results.xml"
        )
        test_command = RUNNER.build_unity_command(
            self.unity,
            self.root / "fixture",
            self.root / "unity.log",
            ["B.Tests", "A.Tests"],
            self.root / "results.xml",
        )

        self.assertIn("-quit", compile_command)
        self.assertNotIn("-runTests", compile_command)
        self.assertNotIn("-quit", test_command)
        self.assertIn("-runTests", test_command)
        self.assertEqual("B.Tests;A.Tests", test_command[test_command.index("-assemblyNames") + 1])

    def test_fixture_configuration_adds_test_framework_only_for_editmode(self) -> None:
        editmode_fixture = self.root / "editmode-fixture"
        compile_fixture = self.root / "compile-fixture"
        for fixture in (editmode_fixture, compile_fixture):
            (fixture / "Packages").mkdir(parents=True)
            (fixture / "Packages/manifest.json").write_text(
                json.dumps({"dependencies": {"com.actionfit.target": "file:target"}, "testables": ["com.actionfit.target"]}),
                encoding="utf-8",
            )

        RUNNER.configure_fixture_for_tests(editmode_fixture, self.repo, ["Target.Tests"])
        RUNNER.configure_fixture_for_tests(compile_fixture, self.repo, [])

        editmode_manifest = json.loads((editmode_fixture / "Packages/manifest.json").read_text(encoding="utf-8"))
        compile_manifest = json.loads((compile_fixture / "Packages/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("1.6.0", editmode_manifest["dependencies"]["com.unity.test-framework"])
        self.assertEqual(["com.actionfit.target"], editmode_manifest["testables"])
        self.assertNotIn("testables", compile_manifest)

    def test_unity_failures_distinguish_validation_and_infrastructure(self) -> None:
        cases = (
            (RUNNER.ProcessOutcome(1, "", "", 1.0), "error CS1002: ; expected", "PACKAGE_COMPILE_FAILED", 1),
            (RUNNER.ProcessOutcome(1, "", "", 1.0), "Failed to resolve packages", "DEPENDENCY_RESOLUTION_FAILED", 2),
            (RUNNER.ProcessOutcome(1, "", "", 1.0), "No valid Unity Editor license", "UNITY_LICENSE_ERROR", 2),
            (RUNNER.ProcessOutcome(-1, "", "", 1.0, True), "", "UNITY_TIMEOUT", 2),
            (RUNNER.ProcessOutcome(7, "", "", 1.0), "unknown", "UNITY_RUNNER_FAILED", 2),
        )
        for outcome, log, code, exit_code in cases:
            with self.subTest(code=code):
                error = RUNNER.classify_unity_failure(outcome, log)
                self.assertIsNotNone(error)
                self.assertEqual(code, error.code)
                self.assertEqual(exit_code, error.exit_code)

    def test_reads_exact_unity_patch_from_editor_log(self) -> None:
        log = "Initialize engine version: 6000.2.6f2 (4a4dcaec6541)\n"

        self.assertEqual("6000.2.6f2", RUNNER.observed_unity_version(log))

    def test_parse_nunit_reports_counts_and_failure(self) -> None:
        result_path = self.root / "nunit.xml"
        result_path.write_text(
            '<test-run result="Failed" total="3" passed="2" failed="1" skipped="0" inconclusive="0">'
            '<test-suite><test-case name="fails" fullname="Target.Tests.fails" result="Failed">'
            '<failure><message>Expected true but was false</message></failure>'
            '</test-case></test-suite></test-run>',
            encoding="utf-8",
        )

        summary = RUNNER.parse_nunit(result_path)

        self.assertFalse(summary["success"])
        self.assertEqual(3, summary["total"])
        self.assertEqual(1, summary["failed"])
        self.assertEqual(
            [{"name": "Target.Tests.fails", "message": "Expected true but was false"}],
            summary["failedTests"],
        )

    def test_execute_without_tests_compiles_and_cleans_fixture(self) -> None:
        def fake_process(command: list[str], cwd: Path, timeout: int) -> object:
            log_path = Path(command[command.index("-logFile") + 1])
            log_path.write_text("Compilation completed successfully", encoding="utf-8")
            return RUNNER.ProcessOutcome(0, "", "", 1.25)

        with mock.patch.object(RUNNER, "run_process", side_effect=fake_process):
            result = RUNNER.execute(self.arguments())

        self.assertTrue(result["success"])
        self.assertEqual("compile-only", result["summary"]["mode"])
        self.assertEqual("skipped", next(item for item in result["phases"] if item["name"] == "shell")["status"])
        self.assertFalse(Path(result["projectPath"]).exists())
        written = json.loads((self.root / "results/result.json").read_text(encoding="utf-8"))
        self.assertEqual("test-run", written["runId"])

    def test_failed_nunit_overrides_unity_test_exit_code_as_package_failure(self) -> None:
        self.write_test_assembly()

        def fake_process(command: list[str], cwd: Path, timeout: int) -> object:
            Path(command[command.index("-logFile") + 1]).write_text("Test run finished", encoding="utf-8")
            Path(command[command.index("-testResults") + 1]).write_text(
                '<test-run result="Failed" total="1" passed="0" failed="1" skipped="0">'
                '<test-case name="fails" fullname="Target.Tests.fails" result="Failed">'
                '<failure><message>Expected true but was false</message></failure>'
                '</test-case></test-run>',
                encoding="utf-8",
            )
            return RUNNER.ProcessOutcome(2, "", "", 2.0)

        with mock.patch.object(RUNNER, "run_process", side_effect=fake_process):
            result = RUNNER.execute(self.arguments())

        self.assertFalse(result["success"])
        self.assertEqual(1, result["exitCode"])
        self.assertEqual("PACKAGE_TESTS_FAILED", result["code"])
        self.assertEqual(1, result["summary"]["nunit"]["failed"])
        self.assertIn("[nunit]", result["logTail"][0])

    def test_shell_failure_is_a_package_failure_and_writes_log(self) -> None:
        script = self.package / "Tests/Shell/run-tests.sh"
        script.parent.mkdir(parents=True)
        script.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        calls = 0

        def fake_process(command: list[str], cwd: Path, timeout: int) -> object:
            nonlocal calls
            calls += 1
            if calls == 1:
                Path(command[command.index("-logFile") + 1]).write_text("compiled", encoding="utf-8")
                return RUNNER.ProcessOutcome(0, "", "", 1.0)
            return RUNNER.ProcessOutcome(1, "shell output", "shell error", 0.5)

        with mock.patch.object(RUNNER, "run_process", side_effect=fake_process), mock.patch.object(
            RUNNER, "discover_bash", return_value=self.unity
        ):
            result = RUNNER.execute(self.arguments())

        self.assertEqual("PACKAGE_SHELL_TESTS_FAILED", result["code"])
        self.assertEqual(1, result["exitCode"])
        self.assertIn("shell output", (self.root / "results/shell.log").read_text(encoding="utf-8"))
        self.assertIn("[shell.log]", result["logTail"][0])
        self.assertTrue(any("shell error" in line for line in result["logTail"]))


if __name__ == "__main__":
    unittest.main()
