#!/usr/bin/env python3
"""Compile and test one local ActionFit package in a disposable Unity project."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ai_ci import find_repo_root
from prepare_unity_project import PreparationError, cleanup_project, find_catalog, prepare_project, read_unity_version


SCHEMA_VERSION = "1.0"
TOOL_NAME = "actionfit-ai-ci-unity-package-tests"
DEFAULT_TIMEOUT_SECONDS = 900
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
COMPILER_ERROR_PATTERN = re.compile(r"\berror\s+CS\d{4}\b", re.IGNORECASE)
UNITY_VERSION_PATTERN = re.compile(r"Initialize engine version:\s*([^\s(]+)", re.IGNORECASE)
LICENSE_MARKERS = (
    "license is not active",
    "licensing error",
    "failed to activate/update license",
    "no valid unity editor license",
    "couldn't acquire a license",
)
DEPENDENCY_MARKERS = (
    "failed to resolve packages",
    "package manager resolve error",
    "error while resolving packages",
    "upm error",
    "unable to add package",
)
COMPILATION_MARKERS = (
    "scripts have compiler errors",
    "compilation failed",
    "failed to compile",
)


class RunnerError(RuntimeError):
    def __init__(self, code: str, message: str, exit_code: int = 2, suggested_fix: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.suggested_fix = suggested_fix or "Inspect the generated artifacts and fix the reported problem before retrying."


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RunnerError("INVALID_ARGUMENTS", f"Invalid arguments: {message}")


@dataclass
class ProcessOutcome:
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, metavar="PACKAGE_ID", help="Local package under Packages")
    parser.add_argument("--repo-root", help="Unity project root containing Packages")
    parser.add_argument("--unity-executable", help="Exact Unity editor executable override")
    parser.add_argument("--run-id", help="Stable artifact and fixture identifier")
    parser.add_argument("--result-dir", help="Artifact directory override")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--keep-project", action="store_true", help="Keep the disposable project for diagnosis")
    arguments = parser.parse_args(argv)
    if arguments.timeout_seconds <= 0:
        raise RunnerError("INVALID_ARGUMENTS", "--timeout-seconds must be greater than zero.")
    return arguments


def create_run_id(value: str | None) -> str:
    run_id = value or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise RunnerError("INVALID_RUN_ID", f"Invalid run ID: {run_id!r}")
    return run_id


def unity_candidates(version: str) -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        for root in filter(None, (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"))):
            candidates.append(Path(root) / "Unity/Hub/Editor" / version / "Editor/Unity.exe")
    elif sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/Unity/Hub/Editor") / version / "Unity.app/Contents/MacOS/Unity",
                Path.home() / "Applications/Unity/Hub/Editor" / version / "Unity.app/Contents/MacOS/Unity",
            ]
        )
    return candidates


def discover_unity(version: str, explicit: str | None = None) -> Path:
    configured = explicit or os.environ.get("UNITY_EDITOR_PATH")
    candidates = [Path(configured).expanduser()] if configured else unity_candidates(version)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    searched = ", ".join(str(path) for path in candidates) or "no supported default locations"
    raise RunnerError(
        "UNITY_EXECUTABLE_NOT_FOUND",
        f"Unity {version} executable was not found ({searched}).",
        suggested_fix="Install the exact Unity patch or pass --unity-executable/UNITY_EDITOR_PATH.",
    )


def package_root(repo_root: Path, package_id: str) -> Path:
    root = (repo_root / "Packages" / package_id).resolve()
    packages = (repo_root / "Packages").resolve()
    try:
        root.relative_to(packages)
    except ValueError as exc:
        raise RunnerError("PACKAGE_PATH_INVALID", f"Package path escapes Packages: {root}") from exc
    if not root.is_dir():
        raise RunnerError("PACKAGE_NOT_FOUND", f"Local package was not found: {root}")
    return root


def discover_test_assemblies(root: Path) -> list[str]:
    editor_tests = root / "Tests/Editor"
    if not editor_tests.is_dir():
        return []
    assemblies: set[str] = set()
    for asmdef_path in sorted(editor_tests.rglob("*.asmdef")):
        try:
            document = json.loads(asmdef_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunnerError(
                "PACKAGE_TEST_ASMDEF_INVALID",
                f"Could not read test assembly definition {asmdef_path}: {exc}",
                exit_code=1,
            ) from exc
        name = document.get("name") if isinstance(document, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise RunnerError(
                "PACKAGE_TEST_ASMDEF_INVALID",
                f"Test assembly definition has no name: {asmdef_path}",
                exit_code=1,
            )
        assemblies.add(name.strip())
    return sorted(assemblies)


def configure_fixture_for_tests(
    fixture_path: Path,
    repo_root: Path,
    assemblies: Sequence[str],
) -> None:
    manifest_path = fixture_path / "Packages/manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("FIXTURE_MANIFEST_INVALID", f"Could not read fixture manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("dependencies"), dict):
        raise RunnerError("FIXTURE_MANIFEST_INVALID", f"Fixture manifest has no dependencies object: {manifest_path}")

    if assemblies:
        source_manifest_path = repo_root / "Packages/manifest.json"
        try:
            source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8-sig"))
            test_framework_version = source_manifest["dependencies"]["com.unity.test-framework"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RunnerError(
                "TEST_FRAMEWORK_VERSION_UNRESOLVED",
                f"Could not resolve com.unity.test-framework from {source_manifest_path}.",
                suggested_fix="Declare an exact com.unity.test-framework version in the source Packages/manifest.json.",
            ) from exc
        if not isinstance(test_framework_version, str) or not test_framework_version.strip():
            raise RunnerError(
                "TEST_FRAMEWORK_VERSION_UNRESOLVED",
                f"Invalid com.unity.test-framework version in {source_manifest_path}.",
            )
        manifest["dependencies"]["com.unity.test-framework"] = test_framework_version.strip()
    else:
        manifest.pop("testables", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover_bash() -> Path | None:
    configured = os.environ.get("BASH_EXE")
    candidates: list[Path] = [Path(configured).expanduser()] if configured else []
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates.extend(
            [
                Path(program_files) / "Git/bin/bash.exe",
                Path(program_files) / "Git/usr/bin/bash.exe",
            ]
        )
    else:
        candidates.append(Path("/bin/bash"))
    discovered = shutil.which("bash")
    if discovered:
        candidate = Path(discovered)
        windows_system_bash = os.name == "nt" and candidate.name.lower() == "bash.exe" and "windows\\system32" in str(candidate).lower()
        if not windows_system_bash:
            candidates.append(candidate)
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def build_unity_command(
    executable: Path,
    project_path: Path,
    log_path: Path,
    assemblies: Sequence[str],
    nunit_path: Path,
) -> list[str]:
    command = [
        str(executable),
        "-batchmode",
        "-nographics",
        "-projectPath",
        str(project_path),
        "-logFile",
        str(log_path),
    ]
    if assemblies:
        command.extend(
            [
                "-runTests",
                "-testPlatform",
                "EditMode",
                "-assemblyNames",
                ";".join(assemblies),
                "-testResults",
                str(nunit_path),
            ]
        )
    else:
        command.append("-quit")
    return command


def run_process(command: Sequence[str], cwd: Path, timeout_seconds: int) -> ProcessOutcome:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return ProcessOutcome(
            completed.returncode,
            completed.stdout or "",
            completed.stderr or "",
            time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ProcessOutcome(-1, stdout, stderr, time.monotonic() - started, timed_out=True)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def write_process_log(path: Path, outcome: ProcessOutcome) -> None:
    path.write_text(
        f"returnCode: {outcome.return_code}\ntimedOut: {str(outcome.timed_out).lower()}\n"
        f"durationSeconds: {outcome.duration_seconds:.3f}\n\n[stdout]\n{outcome.stdout}\n\n[stderr]\n{outcome.stderr}\n",
        encoding="utf-8",
    )


def log_tail(text: str, line_count: int = 80) -> list[str]:
    return text.splitlines()[-line_count:]


def classify_unity_failure(outcome: ProcessOutcome, unity_log: str) -> RunnerError | None:
    lowered = unity_log.lower()
    if outcome.timed_out:
        return RunnerError("UNITY_TIMEOUT", "Unity exceeded the configured timeout.")
    if any(marker in lowered for marker in LICENSE_MARKERS):
        return RunnerError("UNITY_LICENSE_ERROR", "Unity could not acquire a valid editor license.")
    if any(marker in lowered for marker in DEPENDENCY_MARKERS):
        return RunnerError("DEPENDENCY_RESOLUTION_FAILED", "Unity Package Manager could not resolve the fixture dependencies.")
    if COMPILER_ERROR_PATTERN.search(unity_log) or any(marker in lowered for marker in COMPILATION_MARKERS):
        return RunnerError("PACKAGE_COMPILE_FAILED", "The isolated package project did not compile.", exit_code=1)
    if outcome.return_code != 0:
        return RunnerError("UNITY_RUNNER_FAILED", f"Unity exited with code {outcome.return_code}.")
    return None


def observed_unity_version(unity_log: str) -> str:
    match = UNITY_VERSION_PATTERN.search(unity_log)
    return match.group(1) if match else ""


def parse_nunit(path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise RunnerError("NUNIT_RESULTS_INVALID", f"Could not read NUnit results {path}: {exc}") from exc

    def integer(name: str) -> int:
        try:
            return int(root.attrib.get(name, "0"))
        except ValueError:
            return 0

    result = root.attrib.get("result", root.attrib.get("outcome", "")).strip()
    failed_tests: list[dict[str, str]] = []
    for test_case in root.iter():
        if test_case.tag.rsplit("}", 1)[-1] != "test-case":
            continue
        outcome = test_case.attrib.get("result", test_case.attrib.get("outcome", "")).strip().lower()
        if outcome not in {"failed", "failure", "error"}:
            continue
        message = ""
        for child in test_case.iter():
            if child.tag.rsplit("}", 1)[-1] == "message" and child.text:
                message = " ".join(child.text.split())
                break
        failed_tests.append(
            {
                "name": test_case.attrib.get("fullname") or test_case.attrib.get("name") or "unknown test",
                "message": message,
            }
        )
    summary = {
        "result": result,
        "total": integer("total"),
        "passed": integer("passed"),
        "failed": integer("failed"),
        "skipped": integer("skipped"),
        "inconclusive": integer("inconclusive"),
        "failedTests": failed_tests[:20],
        "failedTestsTruncated": len(failed_tests) > 20,
    }
    summary["success"] = summary["failed"] == 0 and result.lower() not in {"failed", "failure", "error"}
    return summary


def diagnostic(error: RunnerError, path: str = ".") -> dict[str, Any]:
    return {
        "code": error.code,
        "severity": "error",
        "path": path,
        "line": 1,
        "message": str(error),
        "suggestedFix": error.suggested_fix,
    }


def phase(name: str, status: str, duration: float, **values: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "durationSeconds": round(duration, 3), **values}


def execute(arguments: argparse.Namespace) -> dict[str, Any]:
    repo_root = find_repo_root(arguments.repo_root)
    run_id = create_run_id(arguments.run_id)
    target_root = package_root(repo_root, arguments.package)
    unity_version, _ = read_unity_version(repo_root, None)
    unity_executable = discover_unity(unity_version, arguments.unity_executable)
    fixture_path = Path(tempfile.gettempdir()) / "ActionFitAiCi/Fixtures" / run_id
    result_dir = Path(arguments.result_dir).expanduser().absolute() if arguments.result_dir else repo_root / "Temp/ActionFitAiCi/Results" / run_id
    result_dir.mkdir(parents=True, exist_ok=False)
    unity_log_path = result_dir / "unity.log"
    nunit_path = result_dir / "nunit-results.xml"
    shell_log_path = result_dir / "shell.log"
    result_path = result_dir / "result.json"
    assemblies = discover_test_assemblies(target_root)
    shell_script = target_root / "Tests/Shell/run-tests.sh"
    phases: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    result_error: RunnerError | None = None
    nunit_summary: dict[str, Any] | None = None
    prepared = False
    unity_output = ""
    actual_unity_version = ""

    try:
        started = time.monotonic()
        prepare_project(repo_root, arguments.package, fixture_path, find_catalog(repo_root, None))
        prepared = True
        configure_fixture_for_tests(fixture_path, repo_root, assemblies)
        phases.append(phase("prepare", "passed", time.monotonic() - started, projectPath=str(fixture_path)))

        unity_command = build_unity_command(unity_executable, fixture_path, unity_log_path, assemblies, nunit_path)
        unity_outcome = run_process(unity_command, repo_root, arguments.timeout_seconds)
        unity_text = read_text(unity_log_path)
        if unity_outcome.stdout or unity_outcome.stderr:
            unity_text = unity_text + "\n" + unity_outcome.stdout + "\n" + unity_outcome.stderr
        unity_output = unity_text
        if not unity_log_path.is_file():
            unity_log_path.write_text(unity_text, encoding="utf-8")
        actual_unity_version = observed_unity_version(unity_text)
        result_error = classify_unity_failure(unity_outcome, unity_text)
        if actual_unity_version and actual_unity_version != unity_version:
            result_error = RunnerError(
                "UNITY_VERSION_MISMATCH",
                f"Expected Unity {unity_version}, but the runner started {actual_unity_version}.",
                suggested_fix="Pass the executable for the exact patch declared by ProjectSettings/ProjectVersion.txt.",
            )
        if assemblies and nunit_path.is_file():
            nunit_summary = parse_nunit(nunit_path)
            if not nunit_summary["success"] and (result_error is None or result_error.code == "UNITY_RUNNER_FAILED"):
                result_error = RunnerError("PACKAGE_TESTS_FAILED", "One or more package EditMode tests failed.", exit_code=1)
        elif result_error is None and assemblies:
            result_error = RunnerError("NUNIT_RESULTS_MISSING", "Unity did not produce the requested NUnit result file.")
        phases.append(
            phase(
                "unity",
                "failed" if result_error else "passed",
                unity_outcome.duration_seconds,
                mode="editmode" if assemblies else "compile-only",
                assemblies=assemblies,
                returnCode=unity_outcome.return_code,
            )
        )

        if result_error is None and shell_script.is_file():
            bash = discover_bash()
            if bash is None:
                result_error = RunnerError(
                    "BASH_NOT_FOUND",
                    f"Shell tests exist but Bash was not found: {shell_script}",
                    suggested_fix="Install Git Bash on Windows or set BASH_EXE to a Bash executable.",
                )
                phases.append(phase("shell", "failed", 0.0, script=str(shell_script)))
            else:
                shell_outcome = run_process([str(bash), "Tests/Shell/run-tests.sh"], target_root, arguments.timeout_seconds)
                write_process_log(shell_log_path, shell_outcome)
                if shell_outcome.timed_out:
                    result_error = RunnerError("SHELL_TEST_TIMEOUT", "Package shell tests exceeded the configured timeout.")
                elif shell_outcome.return_code != 0:
                    result_error = RunnerError("PACKAGE_SHELL_TESTS_FAILED", "Package shell tests failed.", exit_code=1)
                phases.append(
                    phase(
                        "shell",
                        "failed" if result_error else "passed",
                        shell_outcome.duration_seconds,
                        script=str(shell_script),
                        returnCode=shell_outcome.return_code,
                    )
                )
        elif not shell_script.is_file():
            phases.append(phase("shell", "skipped", 0.0, reason="Tests/Shell/run-tests.sh not found"))
        else:
            phases.append(phase("shell", "skipped", 0.0, reason="Unity validation did not pass"))
    except PreparationError as exc:
        result_error = RunnerError(exc.code, str(exc), suggested_fix=exc.suggested_fix)
        phases.append(phase("prepare", "failed", 0.0))
    except RunnerError as exc:
        result_error = exc
        if not any(item["name"] == "prepare" for item in phases):
            phases.append(phase("prepare", "failed", 0.0))
    except Exception as exc:  # Keep a stable infrastructure result at the CLI boundary.
        result_error = RunnerError("UNITY_TEST_INFRASTRUCTURE_ERROR", str(exc))
    finally:
        if prepared and not arguments.keep_project:
            started = time.monotonic()
            try:
                cleanup_project(fixture_path)
                phases.append(phase("cleanup", "passed", time.monotonic() - started))
            except Exception as exc:
                cleanup_error = RunnerError("FIXTURE_CLEANUP_FAILED", f"Could not clean fixture {fixture_path}: {exc}")
                diagnostics.append(diagnostic(cleanup_error, str(fixture_path)))
                if result_error is None:
                    result_error = cleanup_error
                phases.append(phase("cleanup", "failed", time.monotonic() - started))
        elif prepared:
            phases.append(phase("cleanup", "skipped", 0.0, reason="--keep-project"))

    if result_error:
        diagnostics.insert(0, diagnostic(result_error, str(target_root)))
    unity_log = read_text(unity_log_path) or unity_output
    failure_log = unity_log
    if result_error and result_error.code == "PACKAGE_SHELL_TESTS_FAILED":
        shell_log = read_text(shell_log_path)
        if shell_log:
            failure_log = "[shell.log]\n" + shell_log
    elif result_error and result_error.code == "PACKAGE_TESTS_FAILED" and nunit_summary:
        failed_tests = nunit_summary.get("failedTests") or []
        if failed_tests:
            failure_log = "\n".join(
                f"[nunit] {item['name']}: {item['message']}".rstrip()
                for item in failed_tests
            )
    success = result_error is None
    exit_code = 0 if success else result_error.exit_code
    code = "PACKAGE_VALIDATION_PASSED" if success else result_error.code
    message = (
        f"Isolated validation passed for {arguments.package}."
        if success
        else str(result_error)
    )
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "runId": run_id,
        "packageId": arguments.package,
        "success": success,
        "exitCode": exit_code,
        "code": code,
        "message": message,
        "unityVersion": unity_version,
        "observedUnityVersion": actual_unity_version,
        "unityExecutable": str(unity_executable),
        "projectPath": str(fixture_path),
        "resultDirectory": str(result_dir),
        "phases": phases,
        "summary": {
            "mode": "editmode" if assemblies else "compile-only",
            "testAssemblies": assemblies,
            "nunit": nunit_summary,
        },
        "artifacts": {
            "resultJson": str(result_path),
            "unityLog": str(unity_log_path),
            "nunitXml": str(nunit_path) if nunit_path.is_file() else "",
            "shellLog": str(shell_log_path) if shell_log_path.is_file() else "",
        },
        "diagnostics": diagnostics,
        "logTail": log_tail(failure_log) if not success else [],
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def failure_result(exc: Exception) -> dict[str, Any]:
    error = exc if isinstance(exc, RunnerError) else RunnerError("UNITY_TEST_INFRASTRUCTURE_ERROR", str(exc))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "runId": "",
        "packageId": "",
        "success": False,
        "exitCode": error.exit_code,
        "code": error.code,
        "message": str(error),
        "phases": [],
        "summary": {},
        "artifacts": {},
        "diagnostics": [diagnostic(error)],
        "logTail": [],
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
        result = execute(arguments)
    except Exception as exc:
        result = failure_result(exc)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return int(result["exitCode"])


if __name__ == "__main__":
    raise SystemExit(main())
