---
name: package-ci-help
description: Explain AI CI, its installed skills, package validation commands, isolated Unity runner, workflow setup, result codes, menus, and safety boundaries.
---

# AI CI Help

Answer in the user's language. Explain commands without running validation or synchronizing workflow files unless the user separately requests that operation.

1. Read `PACKAGE_SKILLS.md` first. Treat its generated package identity, complete related-skill table, `$skill-name` invocations, descriptions, and access boundaries as authoritative.
2. Read `Packages/com.actionfit.ai-ci/README.md` and `Packages/com.actionfit.ai-ci/AI_GUIDE.md` when present. If downloaded, resolve `Library/PackageCache/com.actionfit.ai-ci@*` without editing it.
3. Explain these distinct capabilities:
   - read-only package contract validation through `Tools~/ai_ci.py` or `AiCiPackageValidationApi`;
   - disposable-project compilation and EditMode/shell testing through `Tools~/run_unity_package_tests.py`;
   - read-only workflow preview and explicit five-file synchronization through `AiCiWorkflowSetupApi` or `Tools > Package > AI CI > Setup Package CI`;
   - dedicated-self-hosted manual and trusted same-repository pull-request Advisory GitHub Actions validation.
4. Explain the mutually exclusive `--package`, `--changed --base-ref`, and `--all` modes and exit codes `0` success, `1` package failure, and `2` infrastructure failure.
5. State that every workflow job targets `[self-hosted, macOS, unity-package-ci]`, both matrices are serialized, fork pull requests skip the complete workflow before runner allocation, and an offline or mislabeled runner leaves all checks queued.
6. State that install or refresh never writes `.github`, setup never configures runners or branch protection, and package validation does not publish, deploy, contact external services, or modify game content.

List `Validate Package`, `Setup Package CI`, and `README` under `Tools > Package > AI CI`. Recommend the package's `--help` and guide for exact installed flags rather than reconstructing a stale command catalog.
