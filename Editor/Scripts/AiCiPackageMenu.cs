#if UNITY_EDITOR
using System;
using UnityEditor;
using UnityEngine;

namespace ActionFit.AiCi.Editor
{
    public static class AiCiPackageMenu
    {
        private const string MenuRoot = "Tools/Package/AI CI/";
        private const string ReadmePath = "Packages/com.actionfit.ai-ci/README.md";
        private const int ValidatePriority = 40;
        private const int SetupPriority = 41;
        private const int ReadmePriority = 90;

        [MenuItem(MenuRoot + "Validate Package", false, ValidatePriority)]
        private static void ValidatePackage()
        {
            string packageId = FindSelectedPackageId();
            if (string.IsNullOrWhiteSpace(packageId))
            {
                EditorUtility.DisplayDialog(
                    "AI CI",
                    "Select a file or folder under Packages/com.actionfit.* and run validation again.",
                    "OK");
                return;
            }

            AiCiPackageValidationRunResult result = AiCiPackageValidationApi.Execute(
                new AiCiPackageValidationRequest { PackageId = packageId });
            if (result.Success)
                UnityEngine.Debug.Log($"[AI CI] Validation passed: {packageId}\n{result.Summary}");
            else
                UnityEngine.Debug.LogError($"[AI CI] Validation failed: {packageId}\n{result.Summary}");

            EditorUtility.DisplayDialog("AI CI", result.Summary, "OK");
        }

        [MenuItem(MenuRoot + "Setup Package CI", false, SetupPriority)]
        private static void SetupPackageCi()
        {
            AiCiWorkflowSetupResult preview = AiCiWorkflowSetupApi.Preview();
            if (!preview.Success)
            {
                Debug.LogError($"[AI CI] Package CI setup preview failed: {preview.Message}");
                EditorUtility.DisplayDialog("Setup Package CI", preview.Message, "OK");
                return;
            }

            string details = string.Join(
                "\n",
                preview.Assets.ConvertAll(asset => $"[{asset.State}] {asset.TargetRelativePath}"));
            if (preview.IsCurrent)
            {
                EditorUtility.DisplayDialog("Setup Package CI", $"Already up to date.\n\n{details}", "OK");
                return;
            }

            if (!EditorUtility.DisplayDialog(
                    "Setup Package CI",
                    $"Preview the package-owned workflow assets below.\n"
                    + "Missing files will be created and different files will be overwritten.\n"
                    + "No changes are made until Apply is selected.\n\n"
                    + details,
                    "Apply",
                    "Cancel"))
            {
                return;
            }

            AiCiWorkflowSetupResult result = AiCiWorkflowSetupApi.Apply();
            if (result.Success && result.IsCurrent)
                Debug.Log($"[AI CI] {result.Message}\n{details}");
            else
                Debug.LogError($"[AI CI] Package CI setup failed: {result.Message}");
            EditorUtility.DisplayDialog("Setup Package CI", result.Message, "OK");
        }

        [MenuItem(MenuRoot + "README", false, ReadmePriority)]
        private static void OpenReadme()
        {
            var readme = AssetDatabase.LoadAssetAtPath<TextAsset>(ReadmePath);
            if (readme == null)
            {
                EditorUtility.DisplayDialog("Package README", $"README was not found.\n{ReadmePath}", "OK");
                return;
            }

            Selection.activeObject = readme;
            AssetDatabase.OpenAsset(readme);
        }

        private static string FindSelectedPackageId()
        {
            string path = AssetDatabase.GetAssetPath(Selection.activeObject).Replace("\\", "/");
            if (!path.StartsWith("Packages/com.actionfit.", StringComparison.Ordinal)) return "";
            string[] parts = path.Split('/');
            return parts.Length >= 2 ? parts[1] : "";
        }
    }
}
#endif
