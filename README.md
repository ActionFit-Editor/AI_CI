# AI CI (`com.actionfit.ai-ci`)

AI CI runs the ActionFit package contract validator from a local Unity project, prepares disposable Unity projects for isolated package compilation and tests, and ships manual plus pull-request Advisory GitHub Actions validation that reuses those same engines. Local and CI validation therefore keep the same schemas, diagnostics, and exit codes.

## Install

```json
{
  "dependencies": {
    "com.actionfit.ai-ci": "https://github.com/ActionFit-Editor/AI_CI.git#1.0.13"
  }
}
```

Python 3.9 or newer must be available as `python3`, `python`, or the Windows `py -3` launcher. The package depends on `com.actionfit.custompackagemanager`, which owns the shared validation engine.

Installing or updating the package does not modify the consuming repository's `.github` directory. To preview the package-owned files, open `Tools/Package/AI CI/Setup Package CI`. Select `Apply` only after reviewing the Missing/Different/Current list. Apply creates or replaces only these owned targets and preserves unrelated workflows and scripts:

- `.github/workflows/actionfit-package-validation.yml`
- `.github/scripts/actionfit-ai-ci/run-static-validation.sh`
- `.github/scripts/actionfit-ai-ci/run-unity-validation.sh`
- `.github/scripts/actionfit-ai-ci/write-step-summary.py`

Run the menu again after an AI CI package update to preview and explicitly synchronize a newer template. A Different target may contain repository-specific edits, so review it before allowing Apply to overwrite it.

## Agent Skills

Custom Package Manager의 `Install or Refresh Agent Skills`는 Codex와 Claude에 다음 project-local skill을 설치합니다.

- `package-ci-help`: validator, isolated Unity runner, workflow setup과 결과 코드를 설명합니다.
- `package-ci-validate`: package contract validator를 read-only로 실행합니다.
- `package-ci-setup`: 명시 호출 시 먼저 Missing/Different/Current preview를 보여 주고, `Different` 대상은 별도 덮어쓰기 승인을 받은 뒤에만 다섯 파일을 동기화합니다.

write-capable setup skill은 암시 호출되지 않습니다. 설치와 refresh 자체는 `.github`를 수정하지 않으며, 사용자가 수정했거나 관리되지 않는 installed skill도 보존합니다.

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
- `result.json`, `unity.log`, optional NUnit XML, and optional `shell.log` share one `runId`. Failed EditMode results include bounded failed-test names and messages, while Shell failures include the bounded `shell.log` tail, so the structured result remains actionable when artifact upload is unavailable.
- Exit code `0` means success, `1` means package compilation/test validation failed, and `2` means Unity, licensing, dependency resolution, timeout, or runner infrastructure failed.

The source game project and package contents are never copied or modified. The fixture uses local `file:` references, so uncommitted worktree changes are compiled and tested directly. GitHub Actions should call this runner instead of maintaining a second test implementation.

## GitHub Actions Validation

After explicitly applying the setup assets, open GitHub Actions, select `ActionFit Package Validation`, and choose `Run workflow` on a trusted branch. Enter the embedded `package_id`; optionally enter `base_ref` when the static package contract should enforce a version change against that Git ref.

The same workflow also runs as a non-required Advisory check for `pull_request` events. It grants only `contents: read`, does not use a workflow-level path filter, and handles pull requests as follows:

- The planner compares the exact PR base SHA with the checked-out head SHA and emits a sorted matrix containing only changed `Packages/com.actionfit.*` package IDs. A package folder's sibling `.meta` maps back to the owning package instead of becoming a second matrix entry. Deleted package paths stay in scope so contract validation reports the missing package.
- A PR with no ActionFit package changes finishes through the final Advisory job without creating an empty matrix or leaving a pending check.
- `Static package contract (<package>)` runs once per changed package on GitHub-hosted Ubuntu and invokes `Tools~/ai_ci.py`.
- `Isolated Unity package validation (<package>)` runs once per changed package only after the static matrix succeeds, targets `[self-hosted, macOS, unity-package-ci]`, and invokes `Tools~/run_unity_package_tests.py`.
- Pull requests from forks are not allowed to execute package code on the persistent self-hosted runner; the final Advisory job reports that boundary as a failure. The workflow never uses `pull_request_target`.
- New commits cancel an older in-progress run for the same pull request. Manually dispatched runs are not canceled.
- The plan and every package job append a GitHub Step Summary and attempt to retain package-distinguishable JSON and logs for 14 days. The Unity artifact also includes NUnit XML and shell logs when those outputs exist. Artifact upload is best-effort: quota or storage failures are reported on the upload step but do not fail a successful validation or prevent the Unity job from starting. Validation, preflight, and cleanup failures still fail their jobs.
- The Unity job runs the repository preflight before credentials or package code, prepares only job-scoped read access, and calls runner cleanup under `if: always()`.
- The Unity wrapper creates a short marker-owned `RUNNER_TEMP/afci.*` root for its fixture so Unity Bee IPC sockets remain below the macOS domain-socket path limit.

The Unity job requires the dedicated runner and local read-only package token described in `Docs/AI/tools/unity-package-ci-runner.md` in this project. It intentionally does not use the `unity-mobile` runner, mobile signing/deployment secrets, `pull_request_target`, or package publishing. The workflow does not configure repository branch protection by itself. Until the external runner is provisioned and online, the static job can run but the Unity job will remain queued.

## Pull Request Merge Gate Operations

The stable final check name is `Advisory package validation result`. Require or manually enforce only this final aggregate check, not the package-specific matrix job names, because matrix membership changes with each pull request.

When repository branch protection is unavailable, use the workflow as a manual merge gate:

- Do not merge a pull request targeting the integration branch until `Advisory package validation result` completes successfully.
- A package failure has exit code `1` or a failed static, compiler, EditMode, or Shell result. The package author owns the correction. Open the failed package job, read its Step Summary, then inspect its JSON/log/NUnit artifact when available. Do not bypass a package failure.
- An infrastructure failure has exit code `2`, a queued/offline runner, preflight or package-access failure, Unity licensing failure, timeout, or malformed/missing runner result. The CI or runner operator owns recovery. Restore the runner or dependency access and rerun the same commit instead of changing package behavior merely to make CI green.
- Artifact upload quota or storage failure is non-blocking when validation and cleanup succeeded. Use the Step Summary and bounded `logTail` diagnostics, then retry artifact retention after storage recovers.
- A temporary merge exception may be considered only for a documented infrastructure outage, after equivalent local static and isolated Unity validation succeeds and the repository owner explicitly approves it. Record the reason and evidence on the pull request. Never use this exception for a package failure.

If the repository later supports protected branches or rulesets, promote the same `Advisory package validation result` context to Required after confirming a package PR and a no-package PR both finish without a pending check. Preserve unrelated branch settings. To roll back during a runner incident, remove only this required context and keep the workflow installed as Advisory; restore the context after the runner recovers and a trusted rerun succeeds. Never reroute package validation to `unity-mobile` as a rollback.

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

`AiCiWorkflowSetupApi.Preview()` is read-only and reports the five workflow assets as Missing, Different, or Current. `AiCiWorkflowSetupApi.Apply()` performs the same explicit synchronization as the menu without showing dialogs. Automation must call Preview first and must not infer approval to overwrite Different files.

## Unity Menu

- `Tools/Package/AI CI/Validate Package` validates the `com.actionfit.*` package containing the current Project selection.
- `Tools/Package/AI CI/Setup Package CI` previews package-owned GitHub Actions assets and writes them only after explicit Apply confirmation.
- `Tools/Package/AI CI/README` opens this document.

The menu is a human-facing convenience layer. Automation should call the CLI or `AiCiPackageValidationApi` to avoid dialogs.

## Self-Test

```bash
python Packages/com.actionfit.ai-ci/Tests~/test_ai_ci.py
python Packages/com.actionfit.ai-ci/Tests~/test_prepare_unity_project.py
python Packages/com.actionfit.ai-ci/Tests~/test_run_unity_package_tests.py
python Packages/com.actionfit.ai-ci/Tests~/test_github_actions.py
```

The tests verify JSON passthrough, readable summaries, infrastructure result shape, local/catalog/Registry dependency closure, path guards, marker-owned cleanup, isolated compile/test modes, actionable NUnit and Shell failure details, timeout handling, failure classification, workflow/source synchronization, PR package planning and fast success, read-only runner boundaries, Step Summary rendering, and always-cleanup fixture handoff.

## AI Guide

Read `AI_GUIDE.md` before modifying or diagnosing this package in a consuming project.

## Assembly

- **Editor** (`com.actionfit.ai-ci.Editor`): dialog-free validation/setup APIs and Unity menu.
