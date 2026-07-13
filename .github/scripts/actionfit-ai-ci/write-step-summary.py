#!/usr/bin/env python3
"""Append one ActionFit AI CI result to a GitHub Actions step summary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def inline(value: Any) -> str:
    return str(value if value is not None else "").replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def render(title: str, result_path: Path) -> str:
    lines = [f"## {inline(title)}", ""]
    try:
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        lines.extend(("**Result:** ❌ unavailable", "", f"`{inline(error)}`", ""))
        return "\n".join(lines)

    success = bool(result.get("success"))
    lines.append(f"**Result:** {'✅ passed' if success else '❌ failed'}")
    for label, key in (("Package", "packageId"), ("Code", "code"), ("Message", "message")):
        value = result.get(key)
        if value:
            lines.append(f"- **{label}:** `{inline(value)}`")

    summary = result.get("summary") or {}
    if isinstance(summary, dict):
        packages = summary.get("packages")
        if isinstance(packages, int):
            lines.append(
                f"- **Packages:** {packages}, errors: {summary.get('errors', 0)}, warnings: {summary.get('warnings', 0)}"
            )
        mode = summary.get("mode")
        if mode:
            lines.append(f"- **Unity mode:** `{inline(mode)}`")
        nunit = summary.get("nunit")
        if isinstance(nunit, dict):
            lines.append(
                f"- **NUnit:** {nunit.get('passed', 0)}/{nunit.get('total', 0)} passed, "
                f"{nunit.get('failed', 0)} failed, {nunit.get('skipped', 0)} skipped"
            )

    phases = result.get("phases") or []
    if phases:
        lines.extend(("", "| Phase | Status | Seconds |", "| --- | --- | ---: |"))
        for phase in phases:
            lines.append(
                f"| {inline(phase.get('name'))} | {inline(phase.get('status'))} | "
                f"{inline(phase.get('durationSeconds', 0))} |"
            )

    diagnostics = result.get("diagnostics") or []
    if diagnostics:
        lines.extend(("", "### Diagnostics", ""))
        for item in diagnostics[:20]:
            lines.append(
                f"- `{inline(item.get('severity', 'error'))}` `{inline(item.get('code'))}`: "
                f"{inline(item.get('message'))}"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--summary-file", type=Path)
    arguments = parser.parse_args()

    output = render(arguments.title, arguments.result)
    summary_path = arguments.summary_file or (
        Path(os.environ["GITHUB_STEP_SUMMARY"]) if os.environ.get("GITHUB_STEP_SUMMARY") else None
    )
    if summary_path is None:
        print(output)
    else:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("a", encoding="utf-8") as stream:
            stream.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
