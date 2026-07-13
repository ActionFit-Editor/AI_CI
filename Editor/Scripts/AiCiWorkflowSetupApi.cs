#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor.PackageManager;
using UnityEngine;

namespace ActionFit.AiCi.Editor
{
    public enum AiCiWorkflowAssetState
    {
        Missing,
        Different,
        Current,
    }

    [Serializable]
    public sealed class AiCiWorkflowAssetPreview
    {
        public string SourceRelativePath;
        public string TargetRelativePath;
        public AiCiWorkflowAssetState State;
    }

    [Serializable]
    public sealed class AiCiWorkflowSetupResult
    {
        public bool Success;
        public string Message;
        public string RepositoryRoot;
        public List<AiCiWorkflowAssetPreview> Assets = new List<AiCiWorkflowAssetPreview>();

        public bool IsCurrent => Success && Assets.All(asset => asset.State == AiCiWorkflowAssetState.Current);
    }

    public static class AiCiWorkflowSetupService
    {
        private static readonly (string Source, string Target)[] AssetPaths =
        {
            ("WorkflowTemplates/actionfit-package-validation.yml", ".github/workflows/actionfit-package-validation.yml"),
            (".github/scripts/actionfit-ai-ci/plan-package-validation.py", ".github/scripts/actionfit-ai-ci/plan-package-validation.py"),
            (".github/scripts/actionfit-ai-ci/run-static-validation.sh", ".github/scripts/actionfit-ai-ci/run-static-validation.sh"),
            (".github/scripts/actionfit-ai-ci/run-unity-validation.sh", ".github/scripts/actionfit-ai-ci/run-unity-validation.sh"),
            (".github/scripts/actionfit-ai-ci/write-step-summary.py", ".github/scripts/actionfit-ai-ci/write-step-summary.py"),
        };

        public static AiCiWorkflowSetupResult Preview(string packageRoot, string repositoryRoot)
        {
            var result = new AiCiWorkflowSetupResult
            {
                Success = false,
                RepositoryRoot = repositoryRoot,
            };
            if (string.IsNullOrWhiteSpace(packageRoot) || !Directory.Exists(packageRoot))
            {
                result.Message = $"AI CI package root was not found: {packageRoot}";
                return result;
            }
            if (string.IsNullOrWhiteSpace(repositoryRoot) || !Directory.Exists(repositoryRoot))
            {
                result.Message = $"Git repository root was not found: {repositoryRoot}";
                return result;
            }

            foreach ((string sourceRelativePath, string targetRelativePath) in AssetPaths)
            {
                string sourcePath = Combine(packageRoot, sourceRelativePath);
                string targetPath = Combine(repositoryRoot, targetRelativePath);
                if (!File.Exists(sourcePath))
                {
                    result.Message = $"Package workflow source was not found: {sourceRelativePath}";
                    return result;
                }

                result.Assets.Add(new AiCiWorkflowAssetPreview
                {
                    SourceRelativePath = sourceRelativePath,
                    TargetRelativePath = targetRelativePath,
                    State = !File.Exists(targetPath)
                        ? AiCiWorkflowAssetState.Missing
                        : FilesMatch(sourcePath, targetPath)
                            ? AiCiWorkflowAssetState.Current
                            : AiCiWorkflowAssetState.Different,
                });
            }

            result.Success = true;
            result.Message = result.IsCurrent
                ? "Package CI workflow assets are already current."
                : "Package CI workflow assets are ready for explicit synchronization.";
            return result;
        }

        public static AiCiWorkflowSetupResult Apply(string packageRoot, string repositoryRoot)
        {
            AiCiWorkflowSetupResult preview = Preview(packageRoot, repositoryRoot);
            if (!preview.Success || preview.IsCurrent) return preview;

            foreach (AiCiWorkflowAssetPreview asset in preview.Assets.Where(asset => asset.State != AiCiWorkflowAssetState.Current))
            {
                string sourcePath = Combine(packageRoot, asset.SourceRelativePath);
                string targetPath = Combine(repositoryRoot, asset.TargetRelativePath);
                string directory = Path.GetDirectoryName(targetPath);
                if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);

                string temporaryPath = targetPath + ".actionfit-ai-ci.tmp";
                try
                {
                    File.Copy(sourcePath, temporaryPath, true);
                    File.Copy(temporaryPath, targetPath, true);
                }
                finally
                {
                    if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
                }
            }

            AiCiWorkflowSetupResult result = Preview(packageRoot, repositoryRoot);
            result.Message = result.IsCurrent
                ? "Package CI workflow assets were synchronized successfully."
                : "Package CI workflow synchronization did not converge.";
            return result;
        }

        private static string Combine(string root, string relativePath)
        {
            return Path.GetFullPath(Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static bool FilesMatch(string left, string right)
        {
            byte[] leftBytes = File.ReadAllBytes(left);
            byte[] rightBytes = File.ReadAllBytes(right);
            return leftBytes.SequenceEqual(rightBytes);
        }
    }

    public static class AiCiWorkflowSetupApi
    {
        private const string PackageId = "com.actionfit.ai-ci";

        public static AiCiWorkflowSetupResult Preview()
        {
            return ResolvePaths(out string packageRoot, out string repositoryRoot, out string error)
                ? AiCiWorkflowSetupService.Preview(packageRoot, repositoryRoot)
                : Failure(error);
        }

        public static AiCiWorkflowSetupResult Apply()
        {
            return ResolvePaths(out string packageRoot, out string repositoryRoot, out string error)
                ? AiCiWorkflowSetupService.Apply(packageRoot, repositoryRoot)
                : Failure(error);
        }

        private static bool ResolvePaths(out string packageRoot, out string repositoryRoot, out string error)
        {
            packageRoot = "";
            repositoryRoot = FindRepositoryRoot(Path.GetFullPath(Path.Combine(Application.dataPath, "..")));
            if (string.IsNullOrWhiteSpace(repositoryRoot))
            {
                error = "Could not find the Git repository root from the Unity project path.";
                return false;
            }

            PackageInfo package = PackageInfo.FindForAssembly(typeof(AiCiWorkflowSetupApi).Assembly);
            if (package != null && !string.IsNullOrWhiteSpace(package.resolvedPath))
                packageRoot = Path.GetFullPath(package.resolvedPath);
            else
                packageRoot = Path.Combine(Path.GetFullPath(Path.Combine(Application.dataPath, "..")), "Packages", PackageId);

            if (!Directory.Exists(packageRoot))
            {
                error = $"Could not resolve the {PackageId} package root.";
                return false;
            }

            error = "";
            return true;
        }

        private static string FindRepositoryRoot(string startPath)
        {
            var current = new DirectoryInfo(startPath);
            while (current != null)
            {
                string marker = Path.Combine(current.FullName, ".git");
                if (Directory.Exists(marker) || File.Exists(marker)) return current.FullName;
                current = current.Parent;
            }
            return "";
        }

        private static AiCiWorkflowSetupResult Failure(string message)
        {
            return new AiCiWorkflowSetupResult { Success = false, Message = message };
        }
    }
}
#endif
