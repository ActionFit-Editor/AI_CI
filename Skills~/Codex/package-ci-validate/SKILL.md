---
name: package-ci-validate
description: Run read-only ActionFit package contract validation for one package, changed packages, or all embedded packages and interpret structured failures. Use before package commits or PRs.
---

# Validate ActionFit Packages

Validate the current repository or worktree on disk without changing package or game content.

1. Read repository instructions and the AI CI `README.md` and `AI_GUIDE.md`.
2. Confirm the repository root and resolve the AI CI package root from `Packages/com.actionfit.ai-ci`, otherwise `Library/PackageCache/com.actionfit.ai-ci@*`. Never edit PackageCache.
3. Select exactly one mode from the user's scope:
   - `--package <package-id>` for one physical `com.actionfit.*` package;
   - `--changed --base-ref <ref>` for committed and uncommitted changed packages;
   - `--all` only when all embedded packages were explicitly requested.
4. Run from the repository root, for example:

```bash
python3 Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --package com.actionfit.example --format summary

python3 Packages/com.actionfit.ai-ci/Tools~/ai_ci.py \
  --changed --base-ref origin/dev_jewoo --format summary
```

Use the resolved PackageCache path in place of `Packages/com.actionfit.ai-ci` only when necessary. Add `--output` only when the user or repository workflow requests a durable JSON result.

5. Report the exact mode, base ref, package count, exit code, diagnostic codes and paths, and suggested fixes. Distinguish package failure (`1`) from infrastructure failure (`2`); do not hide either behind a generic failure.

Do not run workflow setup, isolated Unity tests, GitHub Actions, publishing, deployment, or external service calls from this skill. Do not copy or reimplement the shared Custom Package Manager validation engine.
