#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using NUnit.Framework;

namespace ActionFit.AiCi.Editor.Tests
{
    public class AiCiWorkflowSetupServiceTests
    {
        private string _root;
        private string _packageRoot;
        private string _repositoryRoot;

        [SetUp]
        public void SetUp()
        {
            _root = Path.Combine(Path.GetTempPath(), "AiCiWorkflowSetupTests", Guid.NewGuid().ToString("N"));
            _packageRoot = Path.Combine(_root, "package");
            _repositoryRoot = Path.Combine(_root, "repository");
            Directory.CreateDirectory(_repositoryRoot);
            WritePackageAsset("WorkflowTemplates/actionfit-package-validation.yml", "workflow-v1");
            WritePackageAsset(".github/scripts/actionfit-ai-ci/run-static-validation.sh", "static-v1");
            WritePackageAsset(".github/scripts/actionfit-ai-ci/run-unity-validation.sh", "unity-v1");
            WritePackageAsset(".github/scripts/actionfit-ai-ci/write-step-summary.py", "summary-v1");
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(_root)) Directory.Delete(_root, true);
        }

        [Test]
        public void PreviewDoesNotWriteAndApplyCreatesAllAssets()
        {
            AiCiWorkflowSetupResult preview = AiCiWorkflowSetupService.Preview(_packageRoot, _repositoryRoot);

            Assert.That(preview.Success, Is.True);
            Assert.That(preview.IsCurrent, Is.False);
            Assert.That(preview.Assets, Has.Count.EqualTo(4));
            Assert.That(preview.Assets.All(asset => asset.State == AiCiWorkflowAssetState.Missing), Is.True);
            Assert.That(File.Exists(Target(".github/workflows/actionfit-package-validation.yml")), Is.False);

            AiCiWorkflowSetupResult applied = AiCiWorkflowSetupService.Apply(_packageRoot, _repositoryRoot);

            Assert.That(applied.Success, Is.True);
            Assert.That(applied.IsCurrent, Is.True);
            Assert.That(File.ReadAllText(Target(".github/workflows/actionfit-package-validation.yml")),
                Is.EqualTo("workflow-v1"));
        }

        [Test]
        public void ApplyOverwritesOnlyDifferentOwnedAssetAndPreservesUnrelatedFile()
        {
            AiCiWorkflowSetupService.Apply(_packageRoot, _repositoryRoot);
            File.WriteAllText(Target(".github/workflows/actionfit-package-validation.yml"), "local-change");
            string unrelated = Target(".github/workflows/keep.yml");
            Directory.CreateDirectory(Path.GetDirectoryName(unrelated) ?? throw new InvalidOperationException());
            File.WriteAllText(unrelated, "keep");

            AiCiWorkflowSetupResult preview = AiCiWorkflowSetupService.Preview(_packageRoot, _repositoryRoot);
            AiCiWorkflowSetupResult applied = AiCiWorkflowSetupService.Apply(_packageRoot, _repositoryRoot);

            Assert.That(preview.Assets.Single(asset => asset.TargetRelativePath.EndsWith(".yml")).State,
                Is.EqualTo(AiCiWorkflowAssetState.Different));
            Assert.That(applied.IsCurrent, Is.True);
            Assert.That(File.ReadAllText(Target(".github/workflows/actionfit-package-validation.yml")),
                Is.EqualTo("workflow-v1"));
            Assert.That(File.ReadAllText(unrelated), Is.EqualTo("keep"));
        }

        [Test]
        public void MissingPackageSourceBlocksApplyWithoutPartialWrites()
        {
            File.Delete(Path.Combine(_packageRoot, ".github/scripts/actionfit-ai-ci/run-unity-validation.sh"));

            AiCiWorkflowSetupResult result = AiCiWorkflowSetupService.Apply(_packageRoot, _repositoryRoot);

            Assert.That(result.Success, Is.False);
            Assert.That(result.Message, Does.Contain("run-unity-validation.sh"));
            Assert.That(Directory.Exists(Target(".github")), Is.False);
        }

        private void WritePackageAsset(string relativePath, string contents)
        {
            string path = Path.Combine(_packageRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(path) ?? throw new InvalidOperationException());
            File.WriteAllText(path, contents);
        }

        private string Target(string relativePath)
        {
            return Path.Combine(_repositoryRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
        }
    }
}
#endif
