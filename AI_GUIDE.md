# AI Guide - AI CI

This file is shipped inside the UPM package so an AI assistant in a consuming Unity project can run ActionFit package contract validation without access to the source project's local AI documentation.

## Package Identity

- Package ID: `com.actionfit.ai-ci`
- Display name: AI CI
- Repository: `https://github.com/ActionFit-Editor/AI_CI.git`
- Current package version at generation time: `1.0.1`
- Unity version: `6000.2`

## Purpose

AI CI exposes local package contract validation and disposable Unity project preparation for developers, AI agents, Unity Editor automation, and future GitHub Actions workflows. Contract checks delegate to `com.actionfit.custompackagemanager/Tools~/package_contract_validator.py`, while the project generator resolves the current worktree package dependency closure without modifying the game project.

## Project Router Registration

This package should be listed in `Packages/com.actionfit.custompackagemanager/PACKAGE_AI_GUIDE_ROUTER.md`.

Requested router entry:

- `Packages/com.actionfit.ai-ci/AI_GUIDE.md` - AI CI provides the local package contract validation CLI, dialog-free Unity Editor API, structured JSON results, and human-readable summaries. Read when running or changing ActionFit package validation entry points.

If the router file is not already included in the AI assistant's default reading sequence, the router file is responsible for asking the user to link it from the project's primary AI markdown entry point. Prefer an existing `PROJECT.md`, otherwise use `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or another primary AI entry point.

Read this file when:

- running local ActionFit package contract validation through AI CI
- changing files under `Packages/com.actionfit.ai-ci/`
- changing the AI CI CLI, Unity Editor API, menu, result handling, or engine discovery
- preparing a release for `com.actionfit.ai-ci`

## Main Files

- `Tools~/ai_ci.py`: Unity-independent CLI wrapper that locates and invokes the shared validator.
- `Tools~/prepare_unity_project.py`: cross-platform dependency closure, minimal Unity project preparation, structured results, and marker-guarded cleanup.
- `Editor/Scripts/AiCiPackageValidationApi.cs`: dialog-free Unity Editor API and JSON entry point.
- `Editor/Scripts/AiCiPackageMenu.cs`: selected-package validation and README menu commands.
- `Tests~/test_ai_ci.py`: local CLI and result-contract regression tests.
- `Tests~/test_prepare_unity_project.py`: local/catalog/Registry closure, path safety, manifest, and cleanup regression tests.
- `Editor/PackageInfo/ActionFitPackageInfo_SO.asset`: package catalog metadata and single-version release notes.

## Validation Contract

- Use exactly one selection mode: `--package`, `--changed`, or `--all`.
- `--changed` requires `--base-ref` and includes committed, staged, unstaged, and untracked package changes detected by the shared engine.
- JSON is the default CLI output. It must preserve `schemaVersion`, `tool`, `mode`, `baseRef`, `success`, `exitCode`, `summary`, `packages`, and `diagnostics` from the shared engine.
- Diagnostics keep stable `code`, `severity`, `path`, `line`, `message`, and `suggestedFix` fields.
- Exit codes remain `0` for success, `1` for contract failures, and `2` for infrastructure failures.
- `--format summary` is presentation only. It must not introduce a second validation implementation.
- `--output` writes the JSON result regardless of terminal format.

## Engine Ownership And Discovery

- The validation engine is owned by `com.actionfit.custompackagemanager/Tools~/package_contract_validator.py`.
- Do not copy validator checks into this package. Add or change checks in the owning package, then keep AI CI as an invocation layer.
- Resolve embedded engines from `Packages/com.actionfit.custompackagemanager` first, then downloaded engines from `Library/PackageCache/com.actionfit.custompackagemanager@*`.
- The CLI and Editor API validate the repository/worktree currently on disk, including uncommitted changes.
- Validation must not contact catalogs, GitHub, Jira, Firebase, or credential stores.

## Disposable Unity Project Contract

- `prepare_unity_project.py --package <id> --output <path>` is the shared local and future GitHub Actions preparation command. MCC-1434 runners should import this module or invoke this exact CLI instead of rebuilding dependency closure.
- The target package must be a physical package under the current worktree `Packages` directory. The generated manifest uses its real `file:` path, including uncommitted changes.
- Resolve dependencies in this order: physical package under the current worktree `Packages`, exact requested `com.actionfit.*` catalog version as `<repo_url>#<version>`, then the declared Unity Registry version for non-ActionFit packages.
- Catalog resolution must use an exact package ID and version row and recursively include its `dependencies` field. Missing exact sources return `DEPENDENCY_SOURCE_UNRESOLVED`.
- Reject local package realpaths outside the current worktree `Packages` directory, version conflicts, non-Registry external values, in-repository output paths outside `Temp/ActionFitAiCi/<fixture>`, and existing output folders.
- The output contains only fixture-owned `Assets`, `Library`, `Packages/manifest.json`, target `testables`, `ProjectSettings/ProjectVersion.txt`, and `.actionfit-ai-ci-fixture.json` before Unity runs.
- `--cleanup` may delete only a directory whose marker tool and `projectPath` match the requested output. Never use cleanup for an unmarked project or the source game project.
- Project preparation and cleanup must not modify the source `Packages/manifest.json`, `Library`, Assets, scenes, or package contents.

## API And Menu Rules

- `AiCiPackageValidationApi` is the public dialog-free API for Unity connectors and editor automation.
- `AiCiPackageValidationApi.ExecuteJson` returns the shared engine JSON directly, including infrastructure failures.
- The Editor API may start Python but must not start Unity, create a temporary project, compile packages, run Unity tests, or modify project content.
- `Tools/Package/AI CI/Validate Package` is a human-facing selected-package command. Keep UI dialogs in the menu layer, never in the API.
- Keep executable commands above the separated `README` entry under `Tools/Package/AI CI/`.

## Editing And Verification

- Keep `package.json`, README install tags, this guide's version, and PackageInfo metadata aligned.
- Preserve Unity `.meta` files and existing GUIDs.
- Run `python Packages/com.actionfit.ai-ci/Tests~/test_ai_ci.py` after CLI or result presentation changes.
- Run `python Packages/com.actionfit.ai-ci/Tests~/test_prepare_unity_project.py` after dependency closure, project layout, path guard, or cleanup changes.
- Run `python Packages/com.actionfit.custompackagemanager/Tools~/package_contract_validator.py --package com.actionfit.ai-ci` before finishing.
- Run the consuming project's AI documentation validator when package files change.
- Unity compilation and tests are separate from this package's contract validation and must be reported separately.

## Package Tools Menu

- Unity menu root: `Tools/Package/AI CI/`.
- `Validate Package`: validates the selected embedded `com.actionfit.*` package.
- `README`: opens this package README.
- Keep this package in the executable-tools priority band.

## Release Notes

- Publishing is manual through Custom Package Manager.
- Before reusing a version, check remote Git tags. Published tags are immutable.
- If this package is modified after its version is tagged, bump to the next unused patch version before publishing.
- Do not create repositories, push, tag, publish, or append catalog rows unless the user explicitly requests publishing.
