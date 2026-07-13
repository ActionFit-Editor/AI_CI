# AI CI (`com.actionfit.ai-ci`)

AI CI runs the ActionFit package contract validator from a local Unity project and prepares disposable Unity projects for isolated package compilation and tests. The local CLI, Unity Editor API, disposable-project generator, and future CI callers use the same package sources from the current worktree without contacting a remote runner.

## Install

```json
{
  "dependencies": {
    "com.actionfit.ai-ci": "https://github.com/ActionFit-Editor/AI_CI.git#1.0.2"
  }
}
```

Python 3.9 or newer must be available as `python3`, `python`, or the Windows `py -3` launcher. The package depends on `com.actionfit.custompackagemanager`, which owns the shared validation engine.

## Local CLI

Run from the Unity project root. JSON is the default output and keeps the shared `actionfit-package-contract-validator` schema unchanged.

```bash
python Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --package com.actionfit.ai-ci

python Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --changed --base-ref origin/dev_jewoo \
  --output Temp/ai-ci-result.json

python Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --all --format summary
```

Selection modes are mutually exclusive:

- `--package <package-id>` validates one package and can optionally use `--base-ref` for version checks.
- `--changed --base-ref <ref>` validates packages changed from the Git merge base, including uncommitted worktree changes.
- `--all` validates every embedded `com.actionfit.*` package.

Exit codes are inherited from the shared engine: `0` for success, `1` for contract failures, and `2` for infrastructure failures. `--output` always writes the JSON result even when `--format summary` is used for terminal output.

## Disposable Unity Project

Prepare a minimal Unity project for one embedded ActionFit package:

```bash
python Packages/com.actionfit.ai-ci/Tools~/prepare_unity_project.py \
  --package com.actionfit.ai-ci \
  --output Temp/ActionFitAiCi/com.actionfit.ai-ci \
  --repo-root .
```

The generator:

- references the target and available local dependencies through `file:` URLs, so current worktree and uncommitted package changes are used directly;
- resolves remaining `com.actionfit.*` dependencies from the exact requested version in `Assets/_Data/_CustomPackageManager/package_catalog.csv`;
- keeps declared Unity Registry versions for non-ActionFit dependencies;
- writes only an empty `Assets`, fixture-owned `Library`, minimal `Packages/manifest.json`, target `testables`, and `ProjectSettings/ProjectVersion.txt` under the new output folder;
- rejects package realpaths outside the current worktree `Packages` directory, limits in-repository fixtures to children of `Temp/ActionFitAiCi`, and never overwrites an existing output folder.

When validation is finished, remove only the marker-owned fixture:

```bash
python Packages/com.actionfit.ai-ci/Tools~/prepare_unity_project.py \
  --cleanup \
  --output Temp/ActionFitAiCi/com.actionfit.ai-ci
```

Cleanup rejects folders without a matching `.actionfit-ai-ci-fixture.json` marker and matching `projectPath`. The source project's `Packages/manifest.json`, `Library`, Assets, and scenes are not modified.

## Isolated Unity Tests

Run the same top-level command on Windows and macOS from the Unity project root:

```bash
python Packages/com.actionfit.ai-ci/Tools~/run_unity_package_tests.py \
  --package com.actionfit.custompackagemanager
```

The runner finds the exact Unity patch from `ProjectSettings/ProjectVersion.txt`, prepares a short-path disposable project under the operating system temporary directory, and writes durable artifacts under the worktree's `Temp/ActionFitAiCi/Results/<run-id>`. Pass `--unity-executable` or set `UNITY_EDITOR_PATH` when Unity Hub is not installed in its default location. Useful overrides include `--run-id`, `--result-dir`, `--timeout-seconds`, and `--keep-project`.

- If the package contains `Tests/Editor/*.asmdef`, the package is marked `testables`, only those assemblies run as EditMode tests with the source project's exact `com.unity.test-framework` version, and Unity produces `nunit-results.xml`.
- If no Editor test assembly exists, the same isolated project performs compile-only validation and succeeds when compilation succeeds.
- If `Tests/Shell/run-tests.sh` exists, it runs after Unity validation. Windows uses `BASH_EXE` or Git Bash; macOS uses Bash.
- `result.json`, `unity.log`, optional NUnit XML, and optional `shell.log` share one `runId`. Failed results include a Unity log tail.
- Exit code `0` means success, `1` means package compilation/test validation failed, and `2` means Unity, licensing, dependency resolution, timeout, or runner infrastructure failed.

The source game project and package contents are never copied or modified. The fixture uses local `file:` references, so uncommitted worktree changes are compiled and tested directly. GitHub Actions should call this runner instead of maintaining a second test implementation.

## Unity Editor API

`AiCiPackageValidationApi` is dialog-free and safe for AI connectors or editor automation:

```csharp
var result = AiCiPackageValidationApi.Execute(new AiCiPackageValidationRequest
{
    PackageId = "com.actionfit.ai-ci",
});

string json = AiCiPackageValidationApi.ExecuteJson(
    "{\"PackageId\":\"com.actionfit.ai-ci\"}");
```

`Execute` returns process metadata, a human-readable `Summary`, and the unchanged shared schema in `ResultJson`. `ExecuteJson` returns that shared JSON directly. The API validates the current worktree on disk; it does not create temporary projects, compile packages, run Unity tests, or modify game content.

## Unity Menu

- `Tools/Package/AI CI/Validate Package` validates the `com.actionfit.*` package containing the current Project selection.
- `Tools/Package/AI CI/README` opens this document.

The menu is a human-facing convenience layer. Automation should call the CLI or `AiCiPackageValidationApi` to avoid dialogs.

## Self-Test

```bash
python Packages/com.actionfit.ai-ci/Tests~/test_ai_ci.py
python Packages/com.actionfit.ai-ci/Tests~/test_prepare_unity_project.py
python Packages/com.actionfit.ai-ci/Tests~/test_run_unity_package_tests.py
```

The tests verify JSON passthrough, readable summaries, infrastructure result shape, local/catalog/Registry dependency closure, path guards, marker-owned cleanup, isolated compile/test modes, NUnit interpretation, shell execution, timeout handling, and failure classification.

## AI Guide

Read `AI_GUIDE.md` before modifying or diagnosing this package in a consuming project.

## Assembly

- **Editor** (`com.actionfit.ai-ci.Editor`): dialog-free validation API and Unity menu.
