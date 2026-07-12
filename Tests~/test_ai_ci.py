#!/usr/bin/env python3
"""Regression tests for the AI CI local wrapper."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_PATH = PACKAGE_ROOT / "Tools~" / "ai_ci.py"
SPEC = importlib.util.spec_from_file_location("actionfit_ai_ci", CLI_PATH)
assert SPEC is not None and SPEC.loader is not None
AI_CI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AI_CI)


class AiCiTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI_PATH), *arguments, "--repo-root", str(REPO_ROOT)],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_infrastructure_result_uses_shared_schema(self) -> None:
        result = AI_CI.infrastructure_result("TEST_ERROR", "failure", "origin/dev")
        self.assertEqual("1.0", result["schemaVersion"])
        self.assertEqual("actionfit-package-contract-validator", result["tool"])
        self.assertEqual(2, result["exitCode"])
        self.assertEqual("TEST_ERROR", result["diagnostics"][0]["code"])

    def test_summary_is_human_readable(self) -> None:
        result = AI_CI.infrastructure_result("TEST_ERROR", "failure")
        summary = AI_CI.render_summary(result)
        self.assertIn("Package contract validation: INFRASTRUCTURE ERROR", summary)
        self.assertIn("[error] TEST_ERROR", summary)
        self.assertIn("Fix:", summary)

    def test_json_passthrough_validates_this_package(self) -> None:
        completed = self.run_cli("--package", "com.actionfit.ai-ci")
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["success"])
        self.assertEqual("actionfit-package-contract-validator", result["tool"])
        self.assertEqual("com.actionfit.ai-ci", result["packages"][0]["packageId"])

    def test_summary_mode_reports_pass(self) -> None:
        completed = self.run_cli("--package", "com.actionfit.ai-ci", "--format", "summary")
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("Package contract validation: PASS", completed.stdout)

    def test_summary_mode_can_write_json_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "result.json"
            completed = self.run_cli(
                "--package",
                "com.actionfit.ai-ci",
                "--format",
                "summary",
                "--output",
                str(output_path),
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertIn("Package contract validation: PASS", completed.stdout)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(result["success"])
            self.assertEqual("actionfit-package-contract-validator", result["tool"])


if __name__ == "__main__":
    unittest.main()
