# AI CI (`com.actionfit.ai-ci`)

AI CI는 로컬 Unity 프로젝트에서 AI 문서와 ActionFit 패키지 계약 검증기를 실행하고, 격리 패키지 compile 및 test를 위한 일회용 Unity 프로젝트를 준비합니다. 같은 engine을 재사용하는 수동 및 pull request Advisory GitHub Actions 검증도 제공합니다. 따라서 로컬과 CI 검증이 동일한 schema, 진단 및 exit code를 유지합니다.

## 설치

```json
{
  "dependencies": {
    "com.actionfit.ai-ci": "https://github.com/ActionFit-Editor/AI_CI.git#1.0.21"
  }
}
```

Python 3.9 이상을 `python3`, `python` 또는 Windows `py -3` launcher로 실행할 수 있어야 합니다. 이 패키지는 공유 검증 engine을 소유하는 `com.actionfit.custompackagemanager`에 의존합니다.

패키지를 설치하거나 업데이트해도 사용하는 저장소의 `.github` 디렉터리는 변경하지 않습니다. 패키지 소유 파일을 미리 보려면 `Tools/Package/AI CI/Setup Package CI`를 엽니다. Missing/Different/Current 목록을 검토한 뒤에만 `Apply`를 선택합니다. Apply는 아래 소유 target만 생성 또는 교체하고 관련 없는 workflow와 script는 보존합니다.

- `.github/workflows/actionfit-package-validation.yml`
- `.github/scripts/actionfit-ai-ci/run-static-validation.sh`
- `.github/scripts/actionfit-ai-ci/run-unity-validation.sh`
- `.github/scripts/actionfit-ai-ci/write-step-summary.py`

AI CI 패키지 업데이트 후 메뉴를 다시 실행해 새 template을 미리 보고 명시적으로 동기화합니다. Different target에는 저장소별 수정이 있을 수 있으므로 Apply의 덮어쓰기를 허용하기 전에 검토합니다.

## Agent Skill 안내

Custom Package Manager의 `Install or Refresh Agent Skills`는 Codex와 Claude에 다음 project-local skill을 설치합니다.

- `package-ci-help`: validator, isolated Unity runner, workflow setup과 결과 코드를 설명합니다.
- `package-ci-validate`: package contract validator를 read-only로 실행합니다.
- `package-ci-setup`: 명시 호출 시 먼저 Missing/Different/Current preview를 보여 주고, `Different` 대상은 별도 덮어쓰기 승인을 받은 뒤에만 다섯 파일을 동기화합니다.

write-capable `package-ci-setup`도 Codex 기본 컨텍스트에 포함됩니다. 컨텍스트 노출이나 설치·refresh 자체는 `.github` 수정 승인이 아니며, Preview와 대상별 명시적 Apply 승인 규칙을 계속 적용합니다. 사용자가 수정했거나 관리되지 않는 installed skill도 보존합니다.

## 로컬 CLI

Unity 프로젝트 root에서 실행합니다. JSON이 기본 출력이며 공유 `actionfit-package-contract-validator` schema를 변경 없이 유지합니다.

```bash
python Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --package com.actionfit.ai-ci

python Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --changed --base-ref origin/dev_jewoo \
  --output Temp/ai-ci-result.json

python Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --all --format summary
```

선택 mode는 서로 배타적입니다.

- `--package <package-id>`는 패키지 하나를 검증하고 선택적으로 `--base-ref`를 사용해 버전을 확인합니다.
- `--changed --base-ref <ref>`는 commit하지 않은 worktree 변경을 포함해 Git merge base에서 변경된 패키지를 검증합니다.
- `--all`은 모든 embedded `com.actionfit.*` 패키지를 검증합니다.

Exit code는 공유 engine을 따릅니다. 성공은 `0`, 계약 실패는 `1`, infrastructure 실패는 `2`입니다. Terminal 출력에 `--format summary`를 사용해도 `--output`은 항상 JSON 결과를 씁니다.

## 일회용 Unity 프로젝트

Embedded ActionFit 패키지 하나를 위한 최소 Unity 프로젝트를 준비합니다.

```bash
python Packages/com.actionfit.ai-ci/Tools~/prepare_unity_project.py \
  --package com.actionfit.ai-ci \
  --output Temp/ActionFitAiCi/com.actionfit.ai-ci \
  --repo-root .
```

Generator 동작:

- target과 사용할 수 있는 local 의존성을 `file:` URL로 참조하므로 현재 worktree 및 commit하지 않은 패키지 변경을 직접 사용합니다.
- 나머지 `com.actionfit.*` 의존성은 `Assets/_Data/_CustomPackageManager/package_catalog.csv`에 요청된 정확한 버전으로 해석합니다.
- ActionFit이 아닌 의존성은 선언된 Unity Registry 버전을 유지합니다.
- 새 output 폴더 아래에 빈 `Assets`, fixture 소유 `Library`, 최소 `Packages/manifest.json`, target `testables`, `ProjectSettings/ProjectVersion.txt`만 씁니다.
- 현재 worktree `Packages` 디렉터리 밖의 package realpath를 거부하고 저장소 내부 fixture를 `Temp/ActionFitAiCi` 하위로 제한하며 기존 output 폴더를 덮어쓰지 않습니다.

검증이 끝나면 marker가 소유한 fixture만 제거합니다.

```bash
python Packages/com.actionfit.ai-ci/Tools~/prepare_unity_project.py \
  --cleanup \
  --output Temp/ActionFitAiCi/com.actionfit.ai-ci
```

Cleanup은 일치하는 `.actionfit-ai-ci-fixture.json` marker와 `projectPath`가 없는 폴더를 거부합니다. Source 프로젝트의 `Packages/manifest.json`, `Library`, Assets와 Scene은 변경하지 않습니다.

## 격리 Unity 테스트

Windows와 macOS 모두 Unity 프로젝트 root에서 같은 top-level 명령을 실행합니다.

```bash
python Packages/com.actionfit.ai-ci/Tools~/run_unity_package_tests.py \
  --package com.actionfit.custompackagemanager
```

Runner는 `ProjectSettings/ProjectVersion.txt`에서 정확한 Unity patch를 찾고 운영체제 임시 디렉터리 아래에 짧은 경로의 일회용 프로젝트를 준비한 뒤, worktree의 `Temp/ActionFitAiCi/Results/<run-id>`에 영속 artifact를 씁니다. Unity Hub가 기본 위치에 없으면 `--unity-executable`을 전달하거나 `UNITY_EDITOR_PATH`를 설정합니다. 유용한 override는 `--run-id`, `--result-dir`, `--timeout-seconds`, `--keep-project`입니다.

- 패키지에 `Tests/Editor/*.asmdef`가 있으면 `testables`로 표시하고 source 프로젝트의 정확한 `com.unity.test-framework` 버전으로 해당 어셈블리만 EditMode test로 실행하며 Unity가 `nunit-results.xml`을 생성합니다.
- Editor test 어셈블리가 없으면 같은 격리 프로젝트가 compile-only 검증을 수행하고 compile 성공 시 통과합니다.
- `Tests/Shell/run-tests.sh`가 있으면 Unity 검증 후 실행합니다. Windows는 `BASH_EXE` 또는 Git Bash, macOS는 Bash를 사용합니다.
- `result.json`, `unity.log`, 선택형 NUnit XML과 선택형 `shell.log`는 하나의 `runId`를 공유합니다. 실패한 EditMode 결과에는 제한된 실패 test 이름 및 message가, Shell 실패에는 제한된 `shell.log` tail이 포함되어 artifact upload를 사용할 수 없어도 구조화 결과로 대응할 수 있습니다.
- Exit code `0`은 성공, `1`은 패키지 compile/test 검증 실패, `2`는 Unity, license, 의존성 해석, timeout 또는 runner infrastructure 실패입니다.

Source 게임 프로젝트와 패키지 콘텐츠를 복사하거나 변경하지 않습니다. Fixture가 local `file:` 참조를 사용하므로 commit하지 않은 worktree 변경을 직접 compile하고 test합니다. GitHub Actions는 별도 test 구현을 유지하지 않고 이 runner를 호출해야 합니다.

## GitHub Actions 검증

설정 asset을 명시적으로 적용한 뒤 GitHub Actions에서 `ActionFit Package Validation`을 선택하고 신뢰하는 branch의 `Run workflow`를 실행합니다. Embedded `package_id`를 입력하고 static 패키지 계약에서 특정 Git ref 대비 버전 변경을 강제하려면 선택적으로 `base_ref`를 입력합니다.

같은 workflow는 `pull_request` event에서 필수가 아닌 Advisory check로도 실행됩니다. Plan, AI 문서, static, Unity, 최종 Advisory를 포함한 모든 job은 `[self-hosted, macOS, unity-package-ci]` 전용 runner만 사용하며 GitHub-hosted compute label을 사용하지 않습니다. `contents: read`만 부여하고 workflow 수준 path filter를 사용하지 않으며 pull request를 다음과 같이 처리합니다.

- Planner는 정확한 PR base SHA와 checkout한 head SHA를 비교하고 HEAD에 `package.json`이 남아 있는 변경된 `Packages/com.actionfit.*` 패키지 ID만 정렬 matrix에 포함합니다. 패키지 폴더와 나란한 `.meta`는 두 번째 matrix 항목이 아니라 소유 패키지로 mapping하고, 삭제되거나 다른 ID로 이동해 더는 검증할 수 없는 경로는 제외합니다.
- ActionFit 패키지 변경이 없는 PR은 빈 matrix 또는 pending check를 남기지 않고 최종 Advisory job에서 완료합니다.
- `AI documentation contract`는 패키지 변경 유무와 관계없이 `Tools/AI/validate_ai_docs.py`를 실행하며, 정확한 PR base SHA를 버전 기준으로 전달합니다.
- `Static package contract (<package>)`는 전용 runner에서 변경 패키지마다 한 번 `Tools~/ai_ci.py`를 호출합니다.
- `Isolated Unity package validation (<package>)`은 같은 전용 runner에서 static matrix 성공 후 변경 패키지마다 한 번 `Tools~/run_unity_package_tests.py`를 호출합니다.
- Static과 Unity matrix는 모두 `max-parallel: 4`이므로 변경 패키지를 최대 네 개의 `unity-package-ci` runner에서 동시에 검증합니다. Runner가 네 개보다 적으면 GitHub Actions가 사용 가능한 runner 수에 맞춰 나머지 package job을 queue에 유지합니다. Unity matrix는 전체 Static matrix가 성공한 뒤 시작합니다.
- 수동 실행과 head repository가 현재 repository와 같은 pull request만 job-level 조건을 통과합니다. Fork pull request는 candidate code checkout이나 runner 배정 전에 전체 workflow가 skip되며 검증 성공으로 취급하면 안 됩니다. `pull_request_target`은 사용하지 않습니다.
- 새 commit은 같은 pull request의 이전 진행 중 실행을 취소합니다. 수동 실행은 취소하지 않습니다.
- Plan과 모든 패키지 job은 GitHub Step Summary를 추가하고 패키지별로 구분되는 JSON과 log를 7일간 보관하려고 시도합니다. Unity artifact에는 출력이 있으면 NUnit XML과 shell log도 포함합니다. Artifact upload는 best-effort이므로 quota 또는 storage 실패를 upload step에 보고하지만 성공한 검증을 실패시키거나 Unity job 시작을 막지 않습니다. 검증, preflight 및 cleanup 실패는 계속 해당 job을 실패시킵니다.
- Unity job은 자격 증명 또는 패키지 code보다 먼저 저장소 preflight를 실행하고 job 범위 읽기 권한만 준비하며 `if: always()`에서 runner cleanup을 호출합니다.
- Unity wrapper는 fixture에 marker 소유의 짧은 `RUNNER_TEMP/afci.*` root를 만들어 Unity Bee IPC socket이 macOS domain-socket 경로 제한 아래에 있도록 합니다.

모든 workflow job에는 이 프로젝트 `Docs/AI/tools/unity-package-ci-runner.md`에 설명된 전용 runner와 `python3` 3.9 이상이 필요하고, Unity job에는 local 읽기 전용 package token과 Unity license가 추가로 필요합니다. Plan, AI 문서, Static job은 macOS self-hosted runner에서 writable hosted tool cache를 가정하는 `actions/setup-python`을 사용하지 않고 runner에 설치된 Python을 직접 사용합니다. 의도적으로 GitHub-hosted runner, `unity-mobile` runner, mobile signing/deployment secret, `pull_request_target` 또는 패키지 publish를 사용하지 않습니다. Workflow가 저장소 branch protection을 자체 설정하지 않습니다. 전용 runner가 online이 아니거나 label이 맞지 않으면 Plan부터 queue에 남습니다.

## Pull Request Merge Gate 운영

안정적인 최종 check 이름은 `Advisory package validation result`입니다. Matrix 구성은 pull request마다 달라지므로 패키지별 matrix job 이름이 아니라 이 최종 집계 check만 필수로 지정하거나 수동 강제합니다.

저장소 branch protection을 사용할 수 없으면 workflow를 수동 merge gate로 사용합니다.

- Integration branch를 target으로 하는 pull request는 AI 문서 검증을 포함한 `Advisory package validation result`가 성공할 때까지 merge하지 않습니다.
- Fork pull request는 self-hosted workflow가 의도적으로 skip되므로 성공한 Advisory 증거가 없으며 merge 대상이 아닙니다.
- 패키지 실패는 exit code `1` 또는 실패한 static, compiler, EditMode, Shell 결과입니다. 수정 책임은 패키지 작성자에게 있습니다. 실패한 패키지 job의 Step Summary를 읽고 사용할 수 있으면 JSON/log/NUnit artifact를 확인합니다. 패키지 실패를 우회하지 않습니다.
- Infrastructure 실패는 exit code `2`, queued/offline runner, preflight 또는 package access 실패, Unity license 실패, timeout 또는 잘못되거나 누락된 runner 결과입니다. CI 또는 runner 운영자가 복구를 담당합니다. 단순히 CI를 통과시키려고 패키지 동작을 바꾸지 말고 runner 또는 dependency access를 복구해 같은 commit을 다시 실행합니다.
- 검증과 cleanup이 성공했다면 artifact upload quota 또는 storage 실패는 차단하지 않습니다. Step Summary와 제한된 `logTail` 진단을 사용하고 storage 복구 후 artifact 보관을 재시도합니다.
- 임시 merge 예외는 문서화된 infrastructure 장애가 있고 동등한 local static 및 격리 Unity 검증이 성공하며 저장소 owner가 명시적으로 승인한 경우에만 고려합니다. Pull request에 사유와 증거를 기록하고 패키지 실패에는 이 예외를 사용하지 않습니다.

저장소가 이후 protected branch 또는 ruleset을 지원하면 신뢰하는 same-repository 패키지 PR과 패키지 변경 없는 PR이 모두 전용 runner에서 pending check 없이 완료되는 것을 확인한 뒤 같은 `Advisory package validation result` context를 Required로 올립니다. 관련 없는 branch 설정은 보존하고 fork PR은 별도로 차단합니다. Runner 장애 중 rollback하려면 이 required context만 제거하고 workflow는 Advisory로 유지합니다. Runner 복구 및 신뢰하는 재실행 성공 후 context를 복원합니다. Rollback 목적으로 패키지 검증을 GitHub-hosted 또는 `unity-mobile`에 연결하면 안 됩니다.

## Unity Editor API

`AiCiPackageValidationApi`는 dialog가 없으며 AI connector 또는 Editor 자동화에서 안전하게 사용할 수 있습니다.

```csharp
var result = AiCiPackageValidationApi.Execute(new AiCiPackageValidationRequest
{
    PackageId = "com.actionfit.ai-ci",
});

string json = AiCiPackageValidationApi.ExecuteJson(
    "{\"PackageId\":\"com.actionfit.ai-ci\"}");
```

`Execute`는 process metadata, 사람이 읽을 수 있는 `Summary`와 변경되지 않은 공유 schema를 `ResultJson`으로 반환합니다. `ExecuteJson`은 해당 공유 JSON을 직접 반환합니다. API는 디스크의 현재 worktree를 검증하며 임시 프로젝트 생성, 패키지 compile, Unity test 실행 또는 게임 콘텐츠 변경을 수행하지 않습니다.

`AiCiWorkflowSetupApi.Preview()`는 읽기 전용이며 다섯 workflow asset을 Missing, Different, Current로 보고합니다. `AiCiWorkflowSetupApi.Apply()`는 dialog 없이 메뉴와 같은 명시적 동기화를 수행합니다. 자동화는 먼저 Preview를 호출해야 하며 Different 파일 덮어쓰기 승인을 추론하면 안 됩니다.

## Unity 메뉴

- `Tools/Package/AI CI/Validate Package`: 현재 Project 선택을 포함하는 `com.actionfit.*` 패키지를 검증합니다.
- `Tools/Package/AI CI/Setup Package CI`: 패키지 소유 GitHub Actions asset을 미리 보고 명시적인 Apply 확인 후에만 씁니다.
- `Tools/Package/AI CI/README`: 이 문서를 엽니다.

메뉴는 사람을 위한 편의 계층입니다. 자동화는 dialog를 피하기 위해 CLI 또는 `AiCiPackageValidationApi`를 호출해야 합니다.

## 자체 테스트

```bash
python Packages/com.actionfit.ai-ci/Tests~/test_ai_ci.py
python Packages/com.actionfit.ai-ci/Tests~/test_prepare_unity_project.py
python Packages/com.actionfit.ai-ci/Tests~/test_run_unity_package_tests.py
python Packages/com.actionfit.ai-ci/Tests~/test_github_actions.py
```

테스트는 JSON passthrough, 읽기 쉬운 summary, infrastructure result shape, local/catalog/Registry dependency closure, path guard, marker 소유 cleanup, 격리 compile/test mode, 대응 가능한 NUnit 및 Shell 실패 상세, timeout 처리, 실패 분류, workflow/source 동기화, PR 패키지 plan 및 빠른 성공, 읽기 전용 runner 경계, Step Summary rendering과 항상 cleanup하는 fixture handoff를 검증합니다.

## AI 가이드

사용하는 프로젝트에서 이 패키지를 변경하거나 진단하기 전에 `AI_GUIDE.md`를 읽습니다.

## 어셈블리

- **Editor** (`com.actionfit.ai-ci.Editor`): dialog 없는 검증/설정 API와 Unity 메뉴입니다.
