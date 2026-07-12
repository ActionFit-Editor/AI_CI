#!/usr/bin/env python3
"""Create or clean a disposable Unity project for one local ActionFit package."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import stat
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urldefrag

from ai_ci import find_repo_root


SCHEMA_VERSION = "1.0"
TOOL_NAME = "actionfit-ai-ci-unity-project"
MARKER_FILE = ".actionfit-ai-ci-fixture.json"
PACKAGE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
DEFAULT_CATALOG_PATHS = (
    Path("Assets/_Data/_CustomPackageManager/package_catalog.csv"),
    Path("Packages/com.actionfit.custompackagemanager/Editor/Catalog/package_catalog.csv"),
)


class PreparationError(RuntimeError):
    def __init__(self, code: str, message: str, path: str = ".", suggested_fix: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.suggested_fix = suggested_fix or "Fix the package dependency metadata and prepare the fixture again."


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(f"Invalid arguments: {message}")


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--package", metavar="PACKAGE_ID", help="Prepare a fixture for one local package")
    mode.add_argument("--cleanup", action="store_true", help="Remove a marker-owned fixture")
    parser.add_argument("--output", required=True, help="Disposable Unity project path")
    parser.add_argument("--repo-root", help="Unity project root containing Packages")
    parser.add_argument("--catalog", help="Package catalog CSV override")
    parser.add_argument("--unity-version", help="Exact Unity editor version override")
    return parser.parse_args(argv)


def normalize_path(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_package_id(package_id: str) -> str:
    package_id = (package_id or "").strip()
    if not PACKAGE_ID_PATTERN.fullmatch(package_id):
        raise PreparationError("INVALID_PACKAGE_ID", f"Invalid package ID: {package_id}")
    return package_id


def read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreparationError(code, f"Could not read JSON from {path}: {exc}", str(path)) from exc
    if not isinstance(value, dict):
        raise PreparationError(code, f"Expected a JSON object in {path}.", str(path))
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remove_tree(path: Path) -> None:
    def make_writable(function: Any, blocked_path: str, _: Any) -> None:
        os.chmod(blocked_path, stat.S_IWRITE)
        function(blocked_path)

    shutil.rmtree(path, onerror=make_writable)


def local_package_path(repo_root: Path, package_id: str) -> Path | None:
    packages_root = (repo_root / "Packages").resolve()
    logical_path = packages_root / validate_package_id(package_id)
    if not logical_path.is_dir():
        return None
    resolved = logical_path.resolve()
    if not is_within(resolved, packages_root):
        raise PreparationError(
            "PACKAGE_PATH_ESCAPE",
            f"Local package resolves outside the project Packages directory: {package_id} -> {resolved}",
            str(logical_path),
            "Use a physical package folder inside the current worktree Packages directory.",
        )
    manifest_path = resolved / "package.json"
    manifest = read_json(manifest_path, "LOCAL_PACKAGE_INVALID")
    if manifest.get("name") != package_id:
        raise PreparationError(
            "LOCAL_PACKAGE_ID_MISMATCH",
            f"Local package name {manifest.get('name')!r} does not match {package_id!r}.",
            str(manifest_path),
        )
    return resolved


def file_dependency(path: Path) -> str:
    return "file:" + path.resolve().as_posix()


def find_catalog(repo_root: Path, explicit_path: str | None) -> Path | None:
    candidates = [Path(explicit_path)] if explicit_path else [repo_root / relative for relative in DEFAULT_CATALOG_PATHS]
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else repo_root / candidate
        if resolved.is_file():
            return resolved.resolve()
    return None


def load_catalog(catalog_path: Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if catalog_path is None:
        return {}
    try:
        with catalog_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise PreparationError("CATALOG_READ_FAILED", f"Could not read package catalog: {exc}", str(catalog_path)) from exc

    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        package_id = (row.get("package_id") or "").strip()
        version = (row.get("version") or "").strip()
        if not package_id or not version or "(string)" in package_id:
            continue
        result[(package_id, version)] = {key: (value or "").strip() for key, value in row.items() if key}
    return result


def parse_catalog_dependencies(value: str, owner: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        package_id, separator, version = item.rpartition("@")
        if not separator or not package_id.strip() or not version.strip():
            raise PreparationError(
                "CATALOG_DEPENDENCY_INVALID",
                f"Catalog dependency {item!r} for {owner} must use package@version.",
            )
        result[validate_package_id(package_id.strip())] = version.strip()
    return result


def registry_version(value: str, package_id: str) -> str:
    value = (value or "").strip()
    lowered = value.lower()
    if not value or lowered.startswith(("file:", "git:", "git+", "http:", "https:", "ssh:")):
        raise PreparationError(
            "DEPENDENCY_SOURCE_UNRESOLVED",
            f"Non-ActionFit dependency {package_id} must declare a Unity Registry version, got {value!r}.",
        )
    return value


class DependencyResolver:
    def __init__(self, repo_root: Path, catalog_path: Path | None) -> None:
        self.repo_root = repo_root.resolve()
        self.catalog_path = catalog_path
        self.catalog = load_catalog(catalog_path)
        self.sources: dict[str, str] = {}
        self.requests: dict[str, str] = {}
        self._resolving: set[str] = set()

    def resolve(self, target_package_id: str) -> dict[str, str]:
        target_package_id = validate_package_id(target_package_id)
        target_path = local_package_path(self.repo_root, target_package_id)
        if target_path is None:
            raise PreparationError(
                "TARGET_PACKAGE_NOT_LOCAL",
                f"Target package must exist under the current worktree Packages directory: {target_package_id}",
            )
        self._add_local(target_package_id, target_path, "target")
        return dict(sorted(self.sources.items()))

    def _add(self, package_id: str, requested_version: str, owner: str) -> None:
        package_id = validate_package_id(package_id)
        requested_version = (requested_version or "").strip()
        local_path = local_package_path(self.repo_root, package_id)
        if local_path is not None:
            if package_id not in self.sources:
                self._add_local(package_id, local_path, owner)
            return

        previous = self.requests.get(package_id)
        if previous is not None and previous != requested_version:
            raise PreparationError(
                "DEPENDENCY_VERSION_CONFLICT",
                f"Dependency {package_id} is requested as both {previous} and {requested_version}.",
            )
        if package_id in self.sources:
            return
        self.requests[package_id] = requested_version

        if package_id.startswith("com.actionfit."):
            self._add_catalog(package_id, requested_version, owner)
            return
        self.sources[package_id] = registry_version(requested_version, package_id)

    def _add_local(self, package_id: str, package_path: Path, owner: str) -> None:
        if package_id in self._resolving:
            return
        self.sources[package_id] = file_dependency(package_path)
        self._resolving.add(package_id)
        try:
            manifest = read_json(package_path / "package.json", "LOCAL_PACKAGE_INVALID")
            dependencies = manifest.get("dependencies") or {}
            if not isinstance(dependencies, dict):
                raise PreparationError(
                    "LOCAL_PACKAGE_INVALID",
                    f"Package dependencies must be a JSON object: {package_id}",
                    str(package_path / "package.json"),
                )
            for dependency_id, version in sorted(dependencies.items()):
                if not isinstance(version, str):
                    raise PreparationError(
                        "LOCAL_PACKAGE_INVALID",
                        f"Dependency version for {dependency_id} in {package_id} must be a string.",
                        str(package_path / "package.json"),
                    )
                self._add(dependency_id, version, package_id)
        finally:
            self._resolving.remove(package_id)

    def _add_catalog(self, package_id: str, requested_version: str, owner: str) -> None:
        row = self.catalog.get((package_id, requested_version))
        if row is None:
            catalog_detail = str(self.catalog_path) if self.catalog_path else "no catalog was found"
            raise PreparationError(
                "DEPENDENCY_SOURCE_UNRESOLVED",
                f"Could not resolve {package_id}@{requested_version} required by {owner}; {catalog_detail}.",
                suggested_fix="Embed the dependency in Packages or add its exact version row to the local ActionFit catalog.",
            )
        repository_url = (row.get("repo_url") or "").strip()
        if not repository_url:
            raise PreparationError(
                "DEPENDENCY_SOURCE_UNRESOLVED",
                f"Catalog row {package_id}@{requested_version} has no repository URL.",
            )
        repository_url = urldefrag(repository_url).url
        self.sources[package_id] = f"{repository_url}#{requested_version}"
        for dependency_id, version in sorted(parse_catalog_dependencies(row.get("dependencies", ""), package_id).items()):
            self._add(dependency_id, version, package_id)


def read_unity_version(repo_root: Path, override: str | None) -> tuple[str, str | None]:
    if override:
        return override.strip(), None
    path = repo_root / "ProjectSettings" / "ProjectVersion.txt"
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise PreparationError("UNITY_VERSION_UNRESOLVED", f"Could not read {path}: {exc}", str(path)) from exc
    version = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("m_EditorVersion:")), "")
    revision = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("m_EditorVersionWithRevision:")), None)
    if not version:
        raise PreparationError("UNITY_VERSION_UNRESOLVED", f"m_EditorVersion is missing from {path}.", str(path))
    return version, revision


def validate_output_path(output_path: Path, repo_root: Path) -> Path:
    output = output_path.expanduser().absolute()
    if output.exists():
        raise PreparationError(
            "OUTPUT_ALREADY_EXISTS",
            f"Fixture output already exists and will not be overwritten: {output}",
            str(output),
            "Choose a new output path or run marker-guarded --cleanup first.",
        )
    fixture_root = repo_root / "Temp" / "ActionFitAiCi"
    inside_repo = is_within(output, repo_root)
    allowed_repo_fixture = is_within(output, fixture_root) and normalize_path(output) != normalize_path(fixture_root)
    if (inside_repo and not allowed_repo_fixture) or normalize_path(output) == normalize_path(repo_root):
        raise PreparationError(
            "OUTPUT_PATH_UNSAFE",
            f"Fixture output inside the source project must be a child of {fixture_root}: {output}",
            str(output),
        )
    return output


def prepare_project(
    repo_root: Path,
    package_id: str,
    output_path: Path,
    catalog_path: Path | None = None,
    unity_version_override: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = validate_output_path(output_path, repo_root)
    resolver = DependencyResolver(repo_root, catalog_path or find_catalog(repo_root, None))
    dependencies = resolver.resolve(package_id)
    unity_version, revision = read_unity_version(repo_root, unity_version_override)
    output.parent.mkdir(parents=True, exist_ok=True)
    building = output.parent / f".{output.name}.building-{uuid.uuid4().hex}"

    try:
        (building / "Assets").mkdir(parents=True)
        (building / "Library").mkdir()
        (building / "Packages").mkdir()
        (building / "ProjectSettings").mkdir()
        write_json(
            building / "Packages" / "manifest.json",
            {"dependencies": dependencies, "testables": [package_id]},
        )
        version_lines = [f"m_EditorVersion: {unity_version}"]
        if revision:
            version_lines.append(f"m_EditorVersionWithRevision: {revision}")
        (building / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "\n".join(version_lines) + "\n",
            encoding="utf-8",
        )
        marker = {
            "schemaVersion": SCHEMA_VERSION,
            "tool": TOOL_NAME,
            "packageId": package_id,
            "sourceRepo": str(repo_root),
            "projectPath": str(output),
        }
        write_json(building / MARKER_FILE, marker)
        building.rename(output)
    except Exception:
        if building.exists():
            remove_tree(building)
        raise

    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "mode": "prepare",
        "success": True,
        "exitCode": 0,
        "code": "UNITY_PROJECT_PREPARED",
        "message": f"Prepared disposable Unity project for {package_id}.",
        "packageId": package_id,
        "projectPath": str(output),
        "unityVersion": unity_version,
        "dependencies": dependencies,
        "diagnostics": [],
    }


def cleanup_project(output_path: Path) -> dict[str, Any]:
    output = output_path.expanduser().absolute()
    if not output.is_dir():
        raise PreparationError("FIXTURE_NOT_FOUND", f"Fixture directory was not found: {output}", str(output))
    if normalize_path(output) != os.path.normcase(str(output)):
        raise PreparationError("CLEANUP_PATH_UNSAFE", f"Cleanup path resolves through a link: {output}", str(output))
    marker_path = output / MARKER_FILE
    marker = read_json(marker_path, "FIXTURE_MARKER_MISSING")
    if marker.get("tool") != TOOL_NAME:
        raise PreparationError(
            "FIXTURE_MARKER_INVALID",
            f"Cleanup marker is not owned by {TOOL_NAME}: {marker_path}",
            str(marker_path),
        )
    if os.path.normcase(str(marker.get("projectPath", ""))) != os.path.normcase(str(output)):
        raise PreparationError(
            "FIXTURE_MARKER_INVALID",
            f"Cleanup marker projectPath does not match {output}.",
            str(marker_path),
        )
    remove_tree(output)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "mode": "cleanup",
        "success": True,
        "exitCode": 0,
        "code": "UNITY_PROJECT_CLEANED",
        "message": f"Removed disposable Unity project: {output}",
        "projectPath": str(output),
        "diagnostics": [],
    }


def failure_result(exc: Exception) -> dict[str, Any]:
    error = exc if isinstance(exc, PreparationError) else PreparationError("UNITY_PROJECT_INFRASTRUCTURE_ERROR", str(exc))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "mode": "unknown",
        "success": False,
        "exitCode": 2,
        "code": error.code,
        "message": str(error),
        "projectPath": "",
        "diagnostics": [
            {
                "code": error.code,
                "severity": "error",
                "path": error.path,
                "line": 1,
                "message": str(error),
                "suggestedFix": error.suggested_fix,
            }
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
        output = Path(arguments.output)
        if arguments.cleanup:
            result = cleanup_project(output)
        else:
            repo_root = find_repo_root(arguments.repo_root)
            catalog_path = find_catalog(repo_root, arguments.catalog)
            result = prepare_project(
                repo_root,
                arguments.package,
                output,
                catalog_path,
                arguments.unity_version,
            )
        exit_code = 0
    except Exception as exc:
        result = failure_result(exc)
        exit_code = 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
