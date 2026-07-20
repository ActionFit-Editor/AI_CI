# AI Guide - AI CI

This file is shipped inside the UPM package so an AI assistant in a consuming Unity project can run ActionFit package contract validation without access to the source project's local AI documentation.

## Package Identity

- Package ID: `com.actionfit.ai-ci`
- Display name: AI CI
- Repository: `https://github.com/ActionFit-Editor/AI_CI.git`
- Current package version at generation time: `1.0.18`
- Unity version: `6000.2`

## Purpose

AI CI exposes local package contract validation, isolated Unity package testing, and an explicitly installed manual plus pull-request Advisory GitHub Actions workflow. All workflow jobs target the same dedicated macOS self-hosted runner class so consuming repositories do not depend on GitHub-hosted compute. Contract checks delegate to `com.actionfit.custompackagemanager/Tools~/package_contract_validator.py`; the project generator resolves the current worktree dependency closure; and both local and workflow entry points reuse the same engines, result schemas, and exit codes without modifying the game project.

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

- `Skills~/manifest.json`: schema v2 registration for `package-ci-help`, read-only `package-ci-validate`, and explicit write-capable `package-ci-setup` across Codex and Claude.
- `Skills~/Codex/` and `Skills~/Claude/`: package-owned skill sources installed project-locally by Custom Package Manager.
- `Tools~/ai_ci.py`: Unity-independent CLI wrapper that locates and invokes the shared validator.
- `Tools~/prepare_unity_project.py`: cross-platform dependency closure, minimal Unity project preparation, structured results, and marker-guarded cleanup.
- `Tools~/run_unity_package_tests.py`: cross-platform exact-patch Unity discovery, isolated compilation/EditMode execution, optional shell tests, artifacts, timeout handling, and result classification.
- `WorkflowTemplates/actionfit-package-validation.yml`: package-owned self-hosted-only manual and trusted same-repository PR Advisory workflow source with planning, serialized static and Unity matrices, and a final result job.
- `.github/scripts/actionfit-ai-ci/plan-package-validation.py`: exact-base-SHA PR change planner that emits sorted ActionFit package matrices and a structured result.
- `.github/scripts/actionfit-ai-ci/`: package-owned planner, workflow wrappers, and GitHub Step Summary renderer; the setup API copies these into the consuming repository only on explicit Apply.
- `Editor/Scripts/AiCiPackageValidationApi.cs`: dialog-free Unity Editor API and JSON entry point.
- `Editor/Scripts/AiCiWorkflowSetupApi.cs`: read-only workflow preview plus explicit synchronization API for the five owned repository assets.
- `Editor/Scripts/AiCiPackageMenu.cs`: selected-package validation, workflow setup, and README menu commands.
- `Tests/Editor/AiCiWorkflowSetupServiceTests.cs`: preview, explicit apply, overwrite boundary, and no-partial-write regression tests.
- `Tests~/test_ai_ci.py`: local CLI and result-contract regression tests.
- `Tests~/test_prepare_unity_project.py`: local/catalog/Registry closure, path safety, manifest, and cleanup regression tests.
- `Tests~/test_run_unity_package_tests.py`: compile-only, EditMode, NUnit, shell, timeout, artifact, and package-versus-infrastructure regression tests.
- `Tests~/test_github_actions.py`: package/root template parity, workflow security, Step Summary, fallback result, and fixture cleanup handoff tests.
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

## Isolated Unity Test Contract

- `run_unity_package_tests.py --package <id>` is the single Windows/macOS entry point for local use and future GitHub Actions. CI must reuse it instead of reproducing Unity arguments or result classification.
- Read the exact Unity patch from the source `ProjectSettings/ProjectVersion.txt`. Discover the matching Unity Hub installation, or use `--unity-executable`/`UNITY_EDITOR_PATH` for an exact-patch override.
- Always prepare the fixture through `prepare_unity_project.py`, use current worktree `file:` references, place the fixture under the operating system temporary directory to protect Windows path length headroom, store artifacts under the worktree `Temp` outside the fixture, and clean the marker-owned fixture unless `--keep-project` is explicit.
- Discover test assemblies only from asmdefs beneath the target package's `Tests/Editor`. Keep the target package in the fixture manifest's `testables`, add the source manifest's exact `com.unity.test-framework` version, pass only the discovered assembly names to Unity's EditMode runner, and write NUnit XML. PlayMode and player/mobile builds are outside this command.
- When no Editor test assembly exists, run Unity import/compilation with `-batchmode -nographics -quit`; this is a successful compile-only result when Unity exits cleanly.
- Run `Tests/Shell/run-tests.sh` only when that exact path exists and only after Unity validation succeeds. Use `BASH_EXE` or Git Bash on Windows and Bash on macOS.
- Keep one `runId` across `result.json`, `unity.log`, optional `nunit-results.xml`, optional `shell.log`, fixture path, and result directory. Failed EditMode results include bounded failed-test names and messages, Shell failures include a bounded `shell.log` tail, and other failures include a bounded Unity log tail so Step Summary remains actionable when artifact storage is unavailable.
- Exit `0` for success, `1` for package compiler/EditMode/shell failures, and `2` for missing Unity/Bash, licensing, dependency resolution, timeout, malformed/missing runner output, or other infrastructure failures.
- Result fields and codes are automation contracts. Preserve `schemaVersion`, `tool`, `runId`, `packageId`, `success`, `exitCode`, `code`, `unityVersion`, `observedUnityVersion`, `phases`, `summary`, `artifacts`, `diagnostics`, and `logTail` when extending the runner.

## GitHub Actions Workflow Contract

- Package installation or update must never write `.github` automatically. `AiCiWorkflowSetupApi.Preview` and `Tools/Package/AI CI/Setup Package CI` show Missing/Different/Current first; only explicit `Apply` may synchronize the fixed workflow and four fixed scripts.
- Treat `WorkflowTemplates/actionfit-package-validation.yml` and package `.github/scripts/actionfit-ai-ci/*` as the sources of truth. The repository-root copies must remain byte-identical after synchronization.
- Keep both `workflow_dispatch` and `pull_request`. Manual runs require `package_id` and accept optional `base_ref`; PR runs use the exact event base SHA and explicitly check out the head SHA. Do not add `pull_request_target`, Required Check, schedule, package publishing, deployment, or automatic package-install triggers without separate approval.
- Do not add a workflow-level `paths` filter. The planner must inspect the PR diff inside the job, emit a sorted matrix containing only `Packages/com.actionfit.*` IDs that still have a HEAD `package.json`, skip deleted or renamed-away package paths that cannot be validated, and emit an empty list for the no-package fast-success path.
- Run planning, static validation, isolated Unity validation, and the final Advisory job only on `[self-hosted, macOS, unity-package-ci]`. Do not route any package-validation job to GitHub-hosted labels or `unity-mobile`.
- Keep top-level permissions at `contents: read` and checkout credentials non-persistent. Every job must use a server-evaluated condition that allows only manual dispatch or a pull request whose head repository equals `github.repository`. This prevents a fork PR from receiving any persistent self-hosted runner before candidate code is checked out and preserves the boundary if job dependencies change later.
- A fork PR intentionally skips the complete self-hosted workflow. Without a trusted GitHub-hosted fallback it cannot produce a validated Advisory result and must never be merged as if package validation passed. Do not use `pull_request_target` to manufacture a fork result.
- Static validation runs per matrix package through `Tools~/ai_ci.py`. Unity validation runs per matrix package only after the static matrix succeeds through `Tools~/run_unity_package_tests.py`.
- Keep `max-parallel: 1` on both matrices so one persistent package runner processes package work serially and fixture, workspace, credential-helper, and cleanup state cannot overlap.
- Keep PR concurrency scoped to the PR number and cancel older in-progress PR runs. Preserve non-canceling manual dispatch behavior. Use `fail-fast: false` so every package result is distinguishable.
- The Unity wrapper must run repository preflight first, prepare read-only package access in job scope, create a short marker-owned `RUNNER_TEMP/afci.*` root so macOS Bee IPC sockets remain below the platform path limit, export `PACKAGE_CI_FIXTURE_ROOT`, and leave final cleanup to an `if: always()` step. Cleanup must continue accepting the legacy `RUNNER_TEMP/actionfit-unity-package-ci-*` prefix for in-flight compatibility.
- The plan and both validation matrices write GitHub Step Summary output and attempt to keep package-distinguishable JSON/log artifacts. Unity additionally attempts to preserve NUnit XML and shell output when produced. Artifact upload steps must use `continue-on-error: true` so storage quota or service failures do not override a successful validation or block the dependent Unity job. Validation, preflight, and cleanup failures remain blocking. Infrastructure fallback JSON must keep the Unity runner schema.
- Every workflow run depends on the externally provisioned dedicated runner described by `Docs/AI/tools/unity-package-ci-runner.md`; repository code does not create the OS user, install Python, register the runner, activate Unity, or create the token. Plan and static jobs use the runner-provided `python3` instead of `actions/setup-python`, which assumes a writable hosted tool cache on macOS. If the runner is offline or missing a required label, planning and all dependent checks remain queued.

## Pull Request Merge Gate Contract

- The stable final status context is `Advisory package validation result`. Manual policy and branch protection must target only this aggregate context, never dynamic matrix job names.
- The final context is valid only for manual runs and trusted same-repository pull requests that actually reached the dedicated runner. A skipped fork workflow is not successful validation.
- Installing or applying AI CI workflow assets does not edit repository branch protection or rulesets. Those external settings require a separate, explicit repository-owner decision.
- When protected branches are unavailable, consuming projects may treat the final context as a manual merge gate: do not merge until it completes successfully.
- Exit code `1` and static, compiler, EditMode, or Shell failures are package failures owned by the package author. Inspect the package job Step Summary first, then its structured artifact and logs when available. Never bypass a package failure.
- Exit code `2`, a queued/offline or mislabeled runner, preflight, package-access, licensing, timeout, or malformed-result failure is infrastructure owned by the CI or runner operator. Recover the environment and rerun the same commit; do not change package behavior only to hide infrastructure failure.
- Artifact upload failure remains non-blocking when validation and cleanup succeeded. Step Summary and bounded `logTail` diagnostics remain the fallback evidence.
- A manual merge exception is permitted only for a documented infrastructure outage after equivalent local static and isolated Unity validation succeeds and the repository owner explicitly approves the exception on the pull request. It is never valid for package failure.
- When branch protection becomes available, require the same final context only after a trusted same-repository package PR and no-package PR both prove that it terminates on the dedicated runner. Preserve unrelated branch settings and separately reject fork PRs that cannot produce a valid result.
- Required-check rollback removes only the final required context and leaves the workflow installed as Advisory. Re-enable it after runner recovery and a trusted successful rerun. Never redirect package validation to `unity-mobile` as rollback.

## API And Menu Rules

- `package-ci-validate` may run only the read-only contract validator. `package-ci-setup` must call Preview first, finish without Apply when current, and require separate explicit overwrite approval for every Different target before Apply.
- `AiCiPackageValidationApi` is the public dialog-free API for Unity connectors and editor automation.
- `AiCiPackageValidationApi.ExecuteJson` returns the shared engine JSON directly, including infrastructure failures.
- `AiCiWorkflowSetupApi.Preview` is read-only. `Apply` writes only the five fixed package-owned targets and must be called only after explicit overwrite approval for Different files.
- The Editor API may start Python but must not start Unity, create a temporary project, compile packages, run Unity tests, or modify project content.
- `Tools/Package/AI CI/Validate Package` is a human-facing selected-package command. Keep UI dialogs in the menu layer, never in the API.
- `Tools/Package/AI CI/Setup Package CI` must show a preview and separate Apply confirmation; installing the package is not setup approval.
- Keep executable commands above the separated `README` entry under `Tools/Package/AI CI/`.

## Editing And Verification

- Keep `package.json`, README install tags, this guide's version, and PackageInfo metadata aligned.
- Preserve Unity `.meta` files and existing GUIDs.
- Run `python Packages/com.actionfit.ai-ci/Tests~/test_ai_ci.py` after CLI or result presentation changes.
- Run `python Packages/com.actionfit.ai-ci/Tests~/test_prepare_unity_project.py` after dependency closure, project layout, path guard, or cleanup changes.
- Run `python Packages/com.actionfit.ai-ci/Tests~/test_run_unity_package_tests.py` after Unity command, test discovery, shell, artifact, timeout, or failure-classification changes.
- Run `python Packages/com.actionfit.ai-ci/Tests~/test_github_actions.py`, `actionlint`, and `shellcheck` after workflow/template/wrapper changes.
- Run `python Packages/com.actionfit.custompackagemanager/Tools~/package_contract_validator.py --package com.actionfit.ai-ci` before finishing.
- Run the consuming project's AI documentation validator when package files change.
- Unity compilation and tests are separate from this package's contract validation and must be reported separately.

## Package Tools Menu

- Unity menu root: `Tools/Package/AI CI/`.
- `Validate Package`: validates the selected embedded `com.actionfit.*` package.
- `Setup Package CI`: previews and explicitly synchronizes the package-owned manual/PR Advisory workflow and helper scripts into the consuming repository.
- `README`: opens this package README.
- Keep this package in the executable-tools priority band.

## Release Notes

- Publishing is manual through Custom Package Manager.
- Before reusing a version, check remote Git tags. Published tags are immutable.
- If this package is modified after its version is tagged, bump to the next unused patch version before publishing.
- Do not create repositories, push, tag, publish, or append catalog rows unless the user explicitly requests publishing.
