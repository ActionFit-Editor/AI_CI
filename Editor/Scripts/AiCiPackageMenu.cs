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
