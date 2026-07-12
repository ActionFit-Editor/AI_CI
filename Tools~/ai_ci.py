#!/usr/bin/env python3
"""Run the shared ActionFit package contract validator from a local project."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "1.0"
TOOL_NAME = "actionfit-package-contract-validator"
VALIDATOR_RELATIVE_PATH = Path("Tools~") / "package_contract_validator.py"


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(f"Invalid arguments: {message}")


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--package", metavar="PACKAGE_ID", help="Validate one com.actionfit.* package")
    mode.add_argument("--changed", action="store_true", help="Validate packages changed from --base-ref")
    mode.add_argument("--all", action="store_true", help="Validate all embedded com.actionfit.* packages")
    parser.add_argument("--base-ref", help="Git base ref used by the shared validator")
    parser.add_argument("--repo-root", help="Unity project root containing Packages")
    parser.add_argument("--output", help="Write the JSON result to this path")
    parser.add_argument("--format", choices=("json", "summary"), default="json", help="Terminal output format")
    arguments = parser.parse_args(argv)
    if arguments.changed and not arguments.base_ref:
        raise ValueError("--changed requires --base-ref")
    return arguments


def find_repo_root(explicit_root: str | None) -> Path:
    candidates = [Path(explicit_root)] if explicit_root else [Path.cwd(), *Path.cwd().parents, Path(__file__), *Path(__file__).parents]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            resolved = resolved.parent
        if (resolved / "Packages").is_dir():
            return resolved
    raise RuntimeError("Could not find a Unity project root containing a Packages directory")


def find_validator(repo_root: Path) -> Path:
    embedded = repo_root / "Packages" / "com.actionfit.custompackagemanager" / VALIDATOR_RELATIVE_PATH
    if embedded.is_file():
        return embedded

    package_cache = repo_root / "Library" / "PackageCache"
    if package_cache.is_dir():
        candidates = sorted(
            (
                package_root / VALIDATOR_RELATIVE_PATH
                for package_root in package_cache.glob("com.actionfit.custompackagemanager@*")
            ),
            reverse=True,
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    raise RuntimeError("Could not find the package contract validator from com.actionfit.custompackagemanager")


def infrastructure_result(code: str, message: str, base_ref: str | None = None) -> dict[str, Any]:
    diagnostic = {
        "code": code,
        "severity": "error",
        "path": ".",
        "line": 1,
        "message": message,
        "suggestedFix": "Fix the local AI CI arguments, project packages, or Python environment and run validation again.",
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "mode": "unknown",
        "baseRef": base_ref,
        "success": False,
        "exitCode": 2,
        "summary": {"packages": 0, "errors": 1, "warnings": 0},
        "packages": [],
        "diagnostics": [diagnostic],
    }


def validator_arguments(arguments: argparse.Namespace, repo_root: Path) -> list[str]:
    result: list[str] = []
    if arguments.package:
        result.extend(("--package", arguments.package))
    elif arguments.changed:
        result.append("--changed")
    else:
        result.append("--all")
    if arguments.base_ref:
        result.extend(("--base-ref", arguments.base_ref))
    result.extend(("--repo-root", str(repo_root)))
    if arguments.output:
        result.extend(("--output", arguments.output))
    return result


def run_validator(arguments: argparse.Namespace, repo_root: Path, validator: Path) -> tuple[dict[str, Any], int]:
    completed = subprocess.run(
        [sys.executable, str(validator), *validator_arguments(arguments, repo_root)],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no validator output"
        return infrastructure_result("INVALID_VALIDATOR_RESULT", f"Shared validator returned invalid JSON: {exc}. {detail}"), 2
    exit_code = result.get("exitCode")
    if not isinstance(exit_code, int):
        return infrastructure_result("INVALID_VALIDATOR_RESULT", "Shared validator JSON is missing an integer exitCode."), 2
    return result, exit_code


def render_summary(result: dict[str, Any]) -> str:
    exit_code = int(result.get("exitCode", 2))
    status = "PASS" if exit_code == 0 else "FAIL" if exit_code == 1 else "INFRASTRUCTURE ERROR"
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    lines = [
        f"Package contract validation: {status}",
        f"Packages: {summary.get('packages', 0)}, errors: {summary.get('errors', 0)}, warnings: {summary.get('warnings', 0)}",
    ]
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), list) else []
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"[{item.get('severity', 'error')}] {item.get('code', 'UNKNOWN')} "
            f"{item.get('path', '.')}:{item.get('line', 1)} - {item.get('message', '')}"
        )
        suggestion = item.get("suggestedFix")
        if suggestion:
            lines.append(f"  Fix: {suggestion}")
    return "\n".join(lines) + "\n"


def serialize_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    arguments: argparse.Namespace | None = None
    try:
        arguments = parse_arguments(argv if argv is not None else sys.argv[1:])
        repo_root = find_repo_root(arguments.repo_root)
        validator = find_validator(repo_root)
        result, exit_code = run_validator(arguments, repo_root, validator)
    except Exception as exc:
        result = infrastructure_result("AI_CI_INFRASTRUCTURE_ERROR", str(exc), getattr(arguments, "base_ref", None))
        exit_code = 2

    if getattr(arguments, "output", None) and exit_code == 2:
        output_path = Path(arguments.output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(serialize_result(result), encoding="utf-8")
        except OSError:
            pass

    if getattr(arguments, "format", "json") == "summary":
        sys.stdout.write(render_summary(result))
    else:
        sys.stdout.write(serialize_result(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
