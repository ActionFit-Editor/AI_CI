#!/usr/bin/env python3
"""Regression tests for disposable Unity project preparation."""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = PACKAGE_ROOT / "Tools~"
CLI_PATH = TOOLS_ROOT / "prepare_unity_project.py"
sys.path.insert(0, str(TOOLS_ROOT))
SPEC = importlib.util.spec_from_file_location("actionfit_prepare_unity_project", CLI_PATH)
assert SPEC is not None and SPEC.loader is not None
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class PrepareUnityProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "repo"
        (self.repo / "Assets/_Data/_CustomPackageManager").mkdir(parents=True)
        (self.repo / "Packages").mkdir()
        (self.repo / "ProjectSettings").mkdir()
        (self.repo / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.2.6f2\n"
            "m_EditorVersionWithRevision: 6000.2.6f2 (4a4dcaec6541)\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_package(self, package_id: str, version: str, dependencies: dict[str, str] | None = None) -> Path:
        package_root = self.repo / "Packages" / package_id
        package_root.mkdir()
        (package_root / "package.json").write_text(
            json.dumps(
                {
                    "name": package_id,
                    "version": version,
                    "displayName": package_id,
                    "description": "fixture",
                    "unity": "6000.2",
                    "dependencies": dependencies or {},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return package_root

    def write_catalog(self, rows: list[dict[str, str]]) -> Path:
        path = self.repo / "Assets/_Data/_CustomPackageManager/package_catalog.csv"
        headers = ["package_id", "repo_url", "version", "dependencies"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI_PATH), *arguments],
            cwd=self.repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_prepare_uses_local_packages_and_registry_versions(self) -> None:
        source_manifest = self.repo / "Packages/manifest.json"
        source_manifest.write_text(
            '{"dependencies":{"com.unity.nuget.newtonsoft-json":"3.2.2","keep":"1.0.0"}}\n',
            encoding="utf-8",
        )
        source_library = self.repo / "Library"
        source_library.mkdir()
        (source_library / "keep.txt").write_text("keep", encoding="utf-8")
        dependency = self.write_package("com.actionfit.local", "2.0.0")
        target = self.write_package(
            "com.actionfit.target",
            "1.0.0",
            {
                "com.actionfit.local": "1.0.0",
                "com.unity.nuget.newtonsoft-json": "3.2.1",
            },
        )
        output = self.root / "fixture"

        result = PREPARE.prepare_project(self.repo, "com.actionfit.target", output)

        self.assertTrue(result["success"])
        manifest = json.loads((output / "Packages/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(PREPARE.file_dependency(target), manifest["dependencies"]["com.actionfit.target"])
        self.assertEqual(PREPARE.file_dependency(dependency), manifest["dependencies"]["com.actionfit.local"])
        self.assertEqual("3.2.1", manifest["dependencies"]["com.unity.nuget.newtonsoft-json"])
        self.assertEqual(["com.actionfit.target"], manifest["testables"])
        self.assertTrue((output / "Assets").is_dir())
        self.assertTrue((output / "Library").is_dir())
        self.assertIn("6000.2.6f2 (4a4dcaec6541)", (output / "ProjectSettings/ProjectVersion.txt").read_text())
        self.assertEqual(
            '{"dependencies":{"com.unity.nuget.newtonsoft-json":"3.2.2","keep":"1.0.0"}}\n',
            source_manifest.read_text(encoding="utf-8"),
        )
        self.assertEqual("keep", (source_library / "keep.txt").read_text(encoding="utf-8"))

    def test_catalog_resolves_exact_git_url_and_transitive_dependencies(self) -> None:
        self.write_package("com.actionfit.target", "1.0.0", {"com.actionfit.remote": "2.3.4"})
        catalog = self.write_catalog(
            [
                {
                    "package_id": "com.actionfit.remote",
                    "repo_url": "https://github.com/ActionFit/Remote.git",
                    "version": "2.3.4",
                    "dependencies": "com.actionfit.leaf@1.2.0, com.unity.modules.jsonserialize@1.0.0",
                },
                {
                    "package_id": "com.actionfit.leaf",
                    "repo_url": "https://github.com/ActionFit/Leaf.git#old",
                    "version": "1.2.0",
                    "dependencies": "",
                },
            ]
        )
        output = self.root / "fixture"

        PREPARE.prepare_project(self.repo, "com.actionfit.target", output, catalog)

        dependencies = json.loads((output / "Packages/manifest.json").read_text())["dependencies"]
        self.assertEqual("https://github.com/ActionFit/Remote.git#2.3.4", dependencies["com.actionfit.remote"])
        self.assertEqual("https://github.com/ActionFit/Leaf.git#1.2.0", dependencies["com.actionfit.leaf"])
        self.assertEqual("1.0.0", dependencies["com.unity.modules.jsonserialize"])

    def test_external_dependency_uses_project_git_source_and_lock_hash(self) -> None:
        package_id = "com.example.git-package"
        source = "https://github.com/example/package.git?path=Packages/Runtime#main"
        commit_hash = "ABCDEF0123456789ABCDEF0123456789ABCDEF01"
        self.write_package("com.actionfit.target", "1.0.0", {package_id: "2.5.10"})
        (self.repo / "Packages/manifest.json").write_text(
            json.dumps({"dependencies": {package_id: source}}),
            encoding="utf-8",
        )
        (self.repo / "Packages/packages-lock.json").write_text(
            json.dumps(
                {
                    "dependencies": {
                        package_id: {
                            "version": source,
                            "depth": 0,
                            "source": "git",
                            "dependencies": {},
                            "hash": commit_hash,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        output = self.root / "fixture"

        PREPARE.prepare_project(self.repo, "com.actionfit.target", output)

        dependencies = json.loads((output / "Packages/manifest.json").read_text())["dependencies"]
        self.assertEqual(
            "https://github.com/example/package.git?path=Packages/Runtime#abcdef0123456789abcdef0123456789abcdef01",
            dependencies[package_id],
        )

    def test_external_project_git_source_requires_matching_lock_hash(self) -> None:
        package_id = "com.example.git-package"
        source = "https://github.com/example/package.git"
        self.write_package("com.actionfit.target", "1.0.0", {package_id: "2.5.10"})
        (self.repo / "Packages/manifest.json").write_text(
            json.dumps({"dependencies": {package_id: source}}),
            encoding="utf-8",
        )
        (self.repo / "Packages/packages-lock.json").write_text(
            json.dumps(
                {
                    "dependencies": {
                        package_id: {
                            "version": source,
                            "depth": 0,
                            "source": "git",
                            "dependencies": {},
                            "hash": "not-a-commit",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(PREPARE.PreparationError) as context:
            PREPARE.prepare_project(self.repo, "com.actionfit.target", self.root / "fixture")

        self.assertEqual("DEPENDENCY_SOURCE_UNRESOLVED", context.exception.code)
        self.assertIn("40-character packages-lock hash", str(context.exception))

    def test_unresolved_actionfit_dependency_returns_stable_error(self) -> None:
        self.write_package("com.actionfit.target", "1.0.0", {"com.actionfit.missing": "9.9.9"})
        output = self.root / "fixture"

        completed = self.run_cli(
            "--package",
            "com.actionfit.target",
            "--output",
            str(output),
            "--repo-root",
            str(self.repo),
        )

        self.assertEqual(2, completed.returncode)
        result = json.loads(completed.stdout)
        self.assertEqual("DEPENDENCY_SOURCE_UNRESOLVED", result["code"])
        self.assertFalse(output.exists())

    def test_existing_output_is_not_overwritten(self) -> None:
        self.write_package("com.actionfit.target", "1.0.0")
        output = self.root / "fixture"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")

        with self.assertRaises(PREPARE.PreparationError) as context:
            PREPARE.prepare_project(self.repo, "com.actionfit.target", output)

        self.assertEqual("OUTPUT_ALREADY_EXISTS", context.exception.code)
        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))

    def test_output_inside_source_project_is_limited_to_fixture_temp(self) -> None:
        self.write_package("com.actionfit.target", "1.0.0")

        for relative in ("Assets/generated-fixture", "Library/generated-fixture", "Packages/generated-fixture"):
            with self.subTest(relative=relative):
                output = self.repo / relative
                with self.assertRaises(PREPARE.PreparationError) as context:
                    PREPARE.prepare_project(self.repo, "com.actionfit.target", output)
                self.assertEqual("OUTPUT_PATH_UNSAFE", context.exception.code)
                self.assertFalse(output.exists())

        allowed = self.repo / "Temp/ActionFitAiCi/fixture"
        PREPARE.prepare_project(self.repo, "com.actionfit.target", allowed)
        self.assertTrue(allowed.is_dir())

    def test_cleanup_requires_owned_marker(self) -> None:
        unsafe = self.root / "unsafe"
        unsafe.mkdir()
        (unsafe / "keep.txt").write_text("keep", encoding="utf-8")

        with self.assertRaises(PREPARE.PreparationError) as context:
            PREPARE.cleanup_project(unsafe)

        self.assertEqual("FIXTURE_MARKER_MISSING", context.exception.code)
        self.assertTrue(unsafe.exists())

        self.write_package("com.actionfit.target", "1.0.0")
        fixture = self.root / "fixture"
        PREPARE.prepare_project(self.repo, "com.actionfit.target", fixture)
        marker_path = fixture / PREPARE.MARKER_FILE
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["projectPath"] = str(self.root / "different")
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        with self.assertRaises(PREPARE.PreparationError) as marker_context:
            PREPARE.cleanup_project(fixture)
        self.assertEqual("FIXTURE_MARKER_INVALID", marker_context.exception.code)
        self.assertTrue(fixture.exists())

        marker["projectPath"] = str(fixture)
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        read_only_file = fixture / "Library/read-only.txt"
        read_only_file.write_text("read only", encoding="utf-8")
        read_only_file.chmod(stat.S_IREAD)
        result = PREPARE.cleanup_project(fixture)
        self.assertEqual("UNITY_PROJECT_CLEANED", result["code"])
        self.assertFalse(fixture.exists())

    @unittest.skipIf(os.name == "nt", "Directory symlink creation is not reliably available on Windows CI")
    def test_cleanup_rejects_symbolic_link_output(self) -> None:
        target = self.root / "target"
        target.mkdir()
        link = self.root / "fixture-link"
        link.symlink_to(target, target_is_directory=True)

        with self.assertRaises(PREPARE.PreparationError) as context:
            PREPARE.cleanup_project(link)

        self.assertEqual("CLEANUP_PATH_UNSAFE", context.exception.code)
        self.assertTrue(target.exists())

    @unittest.skipIf(os.name == "nt", "Directory symlink creation is not reliably available on Windows CI")
    def test_local_package_realpath_escape_is_rejected(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "package.json").write_text(
            json.dumps({"name": "com.actionfit.escape", "dependencies": {}}),
            encoding="utf-8",
        )
        os.symlink(outside, self.repo / "Packages/com.actionfit.escape", target_is_directory=True)
        self.write_package("com.actionfit.target", "1.0.0", {"com.actionfit.escape": "1.0.0"})

        with self.assertRaises(PREPARE.PreparationError) as context:
            PREPARE.prepare_project(self.repo, "com.actionfit.target", self.root / "fixture")

        self.assertEqual("PACKAGE_PATH_ESCAPE", context.exception.code)


if __name__ == "__main__":
    unittest.main()
