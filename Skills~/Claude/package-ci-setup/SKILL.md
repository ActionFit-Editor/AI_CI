---
name: package-ci-setup
description: Preview and explicitly synchronize the five AI CI workflow assets into a consuming repository. Use only when the user explicitly requests package CI setup or refresh.
---

# Set Up Package CI

This is a write-capable workflow. Installing AI CI is not setup approval. Run only for an explicitly named repository or worktree after reading its instructions and the package `README.md` and `AI_GUIDE.md`.

1. Verify the exact Unity project/worktree path and connected Editor with `unity-cli --project "<absolute-project>" status`.
2. Call the dialog-free read-only preview and capture its structured result:

```bash
unity-cli --project "<absolute-project>" exec \
  'return JsonUtility.ToJson(AiCiWorkflowSetupApi.Preview(), true);' \
  --usings ActionFit.AiCi.Editor,UnityEngine
```

3. List every target as `Missing`, `Different`, or `Current` before any write.
   - If all are `Current`, finish without calling Apply.
   - If one or more are `Different`, stop and request explicit approval to overwrite those exact paths. The original setup request alone is not approval to replace repository-specific edits.
   - If targets are only `Missing` or the user has explicitly approved every `Different` target, continue.
4. Call `AiCiWorkflowSetupApi.Apply()` once, then call Preview again and require all five targets to be `Current`.
5. Inspect and report the resulting Git diff for exactly these package-owned targets:
   - `.github/workflows/actionfit-package-validation.yml`
   - `.github/scripts/actionfit-ai-ci/plan-package-validation.py`
   - `.github/scripts/actionfit-ai-ci/run-static-validation.sh`
   - `.github/scripts/actionfit-ai-ci/run-unity-validation.sh`
   - `.github/scripts/actionfit-ai-ci/write-step-summary.py`

The synchronized workflow routes Plan, Static, Unity, and Advisory jobs only to `[self-hosted, macOS, unity-package-ci]`. Setup does not register, start, label, or provision that runner; report this prerequisite before Apply.

Do not modify any other workflow or script. Do not run the workflow, register a runner, configure credentials, alter branch protection, publish a package, or overwrite `Different` files without the separate explicit approval required above.
