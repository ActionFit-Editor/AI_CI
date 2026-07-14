#!/usr/bin/env python3
"""Plan manual or pull-request ActionFit package validation jobs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "1.0"
TOOL_NAME = "actionfit-ai-ci-package-plan"
PACKAGE_ID_PATTERN = re.compile(r"com\.actionfit\.[a-z0-9][a-z0-9._-]*")


class PlanningError(RuntimeError):
    pass


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", choices=("workflow_dispatch", "pull_request"), required=True)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--package", default="")
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args(argv)


def require_safe_value(value: str, label: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise PlanningError(f"{label} contains a control character")
    return value


def run_git(repo_root: Path, arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip() or "unknown git error"
        raise PlanningError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout


def changed_package_ids(repo_root: Path, base_ref: str) -> list[str]:
    require_safe_value(base_ref, "base ref")
    if not base_ref:
        raise PlanningError("pull_request planning requires --base-ref")
    run_git(repo_root, ("rev-parse", "--verify", f"{base_ref}^{{commit}}"))
    output = run_git(
        repo_root,
        ("diff", "--no-renames", "--name-only", "-z", f"{base_ref}...HEAD", "--", "Packages"),
    )
    package_ids: set[str] = set()
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        parts = path.split("/")
        if len(parts) < 2 or parts[0] != "Packages":
            continue

        candidate = parts[1]
        if len(parts) == 2 and candidate.endswith(".meta"):
            candidate = candidate[:-5]
        if not PACKAGE_ID_PATTERN.fullmatch(candidate):
            continue
        if not (repo_root / "Packages" / candidate / "package.json").is_file():
            # Deleted or renamed-away packages leave only removal diff entries and
            # have no directory at HEAD, so they cannot be validated.
            continue
        package_ids.add(candidate)
    return sorted(package_ids)


def plan(event: str, repo_root: Path, package_id: str, base_ref: str) -> dict[str, Any]:
    resolved_root = repo_root.resolve()
    if not resolved_root.is_dir():
        raise PlanningError(f"Repository root is not a Git worktree: {resolved_root}")
    run_git(resolved_root, ("rev-parse", "--is-inside-work-tree"))

    package_id = require_safe_value(package_id.strip(), "package ID")
    base_ref = require_safe_value(base_ref.strip(), "base ref")
    if event == "workflow_dispatch":
        if not PACKAGE_ID_PATTERN.fullmatch(package_id):
            raise PlanningError(f"Invalid ActionFit package ID: {package_id or '<empty>'}")
        mode = "manual"
        packages = [package_id]
    else:
        mode = "pull_request"
        packages = changed_package_ids(resolved_root, base_ref)

    code = "PACKAGE_VALIDATION_PLAN_READY" if packages else "NO_ACTIONFIT_PACKAGE_CHANGES"
    message = (
        f"Planned validation for {len(packages)} ActionFit package(s)."
        if packages
        else "No changed Packages/com.actionfit.* path was detected."
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "mode": mode,
        "baseRef": base_ref or None,
        "success": True,
        "exitCode": 0,
        "code": code,
        "message": message,
        "packages": packages,
        "summary": {"packages": len(packages), "errors": 0, "warnings": 0},
        "diagnostics": [],
    }


def failure_result(error: Exception, base_ref: str) -> dict[str, Any]:
    message = str(error)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "mode": "unknown",
        "baseRef": base_ref or None,
        "success": False,
        "exitCode": 2,
        "code": "PACKAGE_VALIDATION_PLAN_FAILED",
        "message": message,
        "packages": [],
        "summary": {"packages": 0, "errors": 1, "warnings": 0},
        "diagnostics": [
            {
                "severity": "error",
                "code": "PACKAGE_VALIDATION_PLAN_FAILED",
                "message": message,
            }
        ],
    }


def write_json(path: Path | None, result: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_github_outputs(path: Path | None, result: dict[str, Any]) -> None:
    if path is None:
        return
    packages = json.dumps(result["packages"], ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"packages={packages}\n")
        stream.write(f"package_count={len(result['packages'])}\n")
        stream.write(f"base_ref={result.get('baseRef') or ''}\n")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
    try:
        result = plan(arguments.event, arguments.repo_root, arguments.package, arguments.base_ref)
        exit_code = 0
    except Exception as error:
        result = failure_result(error, arguments.base_ref)
        exit_code = 2
    write_json(arguments.output, result)
    if exit_code == 0:
        write_github_outputs(arguments.github_output, result)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
