#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor.PackageManager;
using UnityEngine;

namespace ActionFit.AiCi.Editor
{
    /// <summary>
    /// Selects the repository and package scope passed to the local package contract validator.
    /// </summary>
    [Serializable]
    public sealed class AiCiPackageValidationRequest
    {
        public string PackageId;
        public bool Changed;
        public bool All;
        public string BaseRef;
        public string RepoRoot;
        public string OutputPath;
        public string PythonExecutable;
    }

    /// <summary>
    /// Reports the local process result while preserving the shared validator JSON unchanged.
    /// </summary>
    [Serializable]
    public sealed class AiCiPackageValidationRunResult
    {
        public bool Success;
        public int ExitCode;
        public string Code;
        public string Message;
        public string Summary;
        public string ResultJson;
        public string StandardError;
        public string PythonExecutable;
        public string ValidatorPath;
    }

    /// <summary>
    /// Public, dialog-free API shared by Unity Editor automation and AI connectors.
    /// </summary>
    public static class AiCiPackageValidationApi
    {
        private const string PackageId = "com.actionfit.ai-ci";
        private const string CliRelativePath = "Tools~/ai_ci.py";

        /// <summary>
        /// Runs package contract validation against the current worktree on disk.
        /// </summary>
        public static AiCiPackageValidationRunResult Execute(AiCiPackageValidationRequest request)
        {
            if (!TryValidateRequest(request, out string validationError))
                return Failure("INVALID_REQUEST", validationError, null, null, null);

            string repoRoot = string.IsNullOrWhiteSpace(request.RepoRoot)
                ? Directory.GetParent(Application.dataPath)?.FullName
                : Path.GetFullPath(request.RepoRoot);
            if (string.IsNullOrWhiteSpace(repoRoot) || !Directory.Exists(Path.Combine(repoRoot, "Packages")))
                return Failure("REPOSITORY_NOT_FOUND", "The repository root must contain a Packages directory.", null, null, null);

            string cliPath = FindCliPath();
            if (string.IsNullOrWhiteSpace(cliPath))
                return Failure("AI_CI_CLI_NOT_FOUND", $"Could not find {PackageId}/{CliRelativePath}.", null, null, null);

            string arguments = BuildArguments(request, repoRoot, cliPath);
            AiCiPackageValidationRunResult lastInvalidResult = null;
            foreach (PythonCommand command in GetPythonCommands(request.PythonExecutable))
            {
                if (!TryRun(command, arguments, repoRoot, out ProcessResult processResult, out string startError))
                {
                    if (!string.IsNullOrWhiteSpace(request.PythonExecutable))
                        return Failure("PYTHON_START_FAILED", startError, command.Executable, cliPath, null);
                    continue;
                }

                AiCiPackageValidationRunResult result = BuildResult(processResult, command.Executable, cliPath);
                if (result.Code != "INVALID_VALIDATOR_RESULT" || !string.IsNullOrWhiteSpace(request.PythonExecutable))
                    return result;
                lastInvalidResult = result;
            }

            if (lastInvalidResult != null) return lastInvalidResult;
            return Failure(
                "PYTHON_NOT_FOUND",
                "Python 3.9 or newer was not found. Install python3/python or the Windows py launcher.",
                request.PythonExecutable,
                cliPath,
                null);
        }

        /// <summary>
        /// Runs a JSON request and returns the shared validator result JSON directly.
        /// </summary>
        public static string ExecuteJson(string requestJson)
        {
            try
            {
                var request = JsonConvert.DeserializeObject<AiCiPackageValidationRequest>(requestJson ?? "");
                return Execute(request).ResultJson;
            }
            catch (Exception ex)
            {
                return BuildInfrastructureJson("INVALID_REQUEST_JSON", ex.Message);
            }
        }

        private static bool TryValidateRequest(AiCiPackageValidationRequest request, out string error)
        {
            if (request == null)
            {
                error = "A validation request is required.";
                return false;
            }

            int modeCount = (string.IsNullOrWhiteSpace(request.PackageId) ? 0 : 1) +
                            (request.Changed ? 1 : 0) +
                            (request.All ? 1 : 0);
            if (modeCount != 1)
            {
                error = "Select exactly one mode: PackageId, Changed, or All.";
                return false;
            }

            if (request.Changed && string.IsNullOrWhiteSpace(request.BaseRef))
            {
                error = "Changed validation requires BaseRef.";
                return false;
            }

            error = "";
            return true;
        }

        private static string FindCliPath()
        {
            PackageInfo packageInfo = PackageInfo.FindForAssembly(typeof(AiCiPackageValidationApi).Assembly);
            if (packageInfo != null)
            {
                string resolved = Path.Combine(packageInfo.resolvedPath, CliRelativePath);
                if (File.Exists(resolved)) return Path.GetFullPath(resolved);
            }

            string projectRoot = Directory.GetParent(Application.dataPath)?.FullName;
            if (string.IsNullOrWhiteSpace(projectRoot)) return "";
            string embedded = Path.Combine(projectRoot, "Packages", PackageId, CliRelativePath);
            return File.Exists(embedded) ? Path.GetFullPath(embedded) : "";
        }

        private static string BuildArguments(AiCiPackageValidationRequest request, string repoRoot, string cliPath)
        {
            var arguments = new List<string> { Quote(cliPath) };
            if (!string.IsNullOrWhiteSpace(request.PackageId))
            {
                arguments.Add("--package");
                arguments.Add(Quote(request.PackageId.Trim()));
            }
            else if (request.Changed)
            {
                arguments.Add("--changed");
            }
            else
            {
                arguments.Add("--all");
            }

            if (!string.IsNullOrWhiteSpace(request.BaseRef))
            {
                arguments.Add("--base-ref");
                arguments.Add(Quote(request.BaseRef.Trim()));
            }

            arguments.Add("--repo-root");
            arguments.Add(Quote(repoRoot));
            arguments.Add("--format");
            arguments.Add("json");
            if (!string.IsNullOrWhiteSpace(request.OutputPath))
            {
                arguments.Add("--output");
                arguments.Add(Quote(request.OutputPath.Trim()));
            }
            return string.Join(" ", arguments);
        }

        private static IEnumerable<PythonCommand> GetPythonCommands(string explicitExecutable)
        {
            if (!string.IsNullOrWhiteSpace(explicitExecutable))
            {
                yield return new PythonCommand(explicitExecutable.Trim(), "");
                yield break;
            }

            if (Application.platform == RuntimePlatform.WindowsEditor)
                yield return new PythonCommand("py", "-3");
            yield return new PythonCommand("python3", "");
            yield return new PythonCommand("python", "");
        }

        private static bool TryRun(
            PythonCommand command,
            string arguments,
            string workingDirectory,
            out ProcessResult result,
            out string error)
        {
            try
            {
                var startInfo = new ProcessStartInfo
                {
                    FileName = command.Executable,
                    Arguments = string.IsNullOrWhiteSpace(command.PrefixArguments)
                        ? arguments
                        : command.PrefixArguments + " " + arguments,
                    WorkingDirectory = workingDirectory,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                };
                using var process = new Process { StartInfo = startInfo };
                if (!process.Start())
                {
                    result = null;
                    error = $"Could not start {command.Executable}.";
                    return false;
                }

                var outputTask = process.StandardOutput.ReadToEndAsync();
                var errorTask = process.StandardError.ReadToEndAsync();
                process.WaitForExit();
                result = new ProcessResult(process.ExitCode, outputTask.GetAwaiter().GetResult(), errorTask.GetAwaiter().GetResult());
                error = "";
                return true;
            }
            catch (Exception ex)
            {
                result = null;
                error = ex.Message;
                return false;
            }
        }

        private static AiCiPackageValidationRunResult BuildResult(ProcessResult process, string pythonExecutable, string cliPath)
        {
            string json = (process.StandardOutput ?? "").Trim();
            try
            {
                JObject document = JObject.Parse(json);
                int jsonExitCode = document.Value<int?>("exitCode") ?? process.ExitCode;
                bool success = document.Value<bool?>("success") ?? jsonExitCode == 0;
                return new AiCiPackageValidationRunResult
                {
                    Success = success,
                    ExitCode = jsonExitCode,
                    Code = jsonExitCode == 0 ? "VALID" : jsonExitCode == 1 ? "CONTRACT_FAILED" : "INFRASTRUCTURE_FAILED",
                    Message = jsonExitCode == 0 ? "Package contract validation passed." : "Package contract validation did not pass.",
                    Summary = BuildSummary(document),
                    ResultJson = json + Environment.NewLine,
                    StandardError = process.StandardError ?? "",
                    PythonExecutable = pythonExecutable,
                    ValidatorPath = cliPath,
                };
            }
            catch (Exception ex)
            {
                return Failure(
                    "INVALID_VALIDATOR_RESULT",
                    $"AI CI returned invalid JSON: {ex.Message}",
                    pythonExecutable,
                    cliPath,
                    process.StandardError);
            }
        }

        private static string BuildSummary(JObject document)
        {
            int exitCode = document.Value<int?>("exitCode") ?? 2;
            JObject summary = document["summary"] as JObject;
            int packages = summary?.Value<int?>("packages") ?? 0;
            int errors = summary?.Value<int?>("errors") ?? 0;
            int warnings = summary?.Value<int?>("warnings") ?? 0;
            string status = exitCode == 0 ? "PASS" : exitCode == 1 ? "FAIL" : "INFRASTRUCTURE ERROR";
            var lines = new List<string>
            {
                $"Package contract validation: {status}",
                $"Packages: {packages}, errors: {errors}, warnings: {warnings}",
            };
            foreach (JToken diagnostic in document["diagnostics"]?.Take(20) ?? Enumerable.Empty<JToken>())
            {
                lines.Add(
                    $"[{diagnostic.Value<string>("severity")}] {diagnostic.Value<string>("code")} " +
                    $"{diagnostic.Value<string>("path")}:{diagnostic.Value<int?>("line") ?? 1} - " +
                    diagnostic.Value<string>("message"));
            }
            return string.Join(Environment.NewLine, lines);
        }

        private static AiCiPackageValidationRunResult Failure(
            string code,
            string message,
            string pythonExecutable,
            string validatorPath,
            string standardError)
        {
            string json = BuildInfrastructureJson(code, message);
            JObject document = JObject.Parse(json);
            return new AiCiPackageValidationRunResult
            {
                Success = false,
                ExitCode = 2,
                Code = code,
                Message = message,
                Summary = BuildSummary(document),
                ResultJson = json,
                StandardError = standardError ?? "",
                PythonExecutable = pythonExecutable ?? "",
                ValidatorPath = validatorPath ?? "",
            };
        }

        private static string BuildInfrastructureJson(string code, string message)
        {
            var diagnostic = new JObject
            {
                ["code"] = code,
                ["severity"] = "error",
                ["path"] = ".",
                ["line"] = 1,
                ["message"] = message,
                ["suggestedFix"] = "Fix the local AI CI arguments or Python environment and run validation again.",
            };
            var document = new JObject
            {
                ["schemaVersion"] = "1.0",
                ["tool"] = "actionfit-package-contract-validator",
                ["mode"] = "unknown",
                ["baseRef"] = null,
                ["success"] = false,
                ["exitCode"] = 2,
                ["summary"] = new JObject
                {
                    ["packages"] = 0,
                    ["errors"] = 1,
                    ["warnings"] = 0,
                },
                ["packages"] = new JArray(),
                ["diagnostics"] = new JArray(diagnostic),
            };
            return document.ToString(Formatting.Indented) + Environment.NewLine;
        }

        private static string Quote(string value)
        {
            value ??= "";
            var builder = new StringBuilder("\"");
            int backslashes = 0;
            foreach (char character in value)
            {
                if (character == '\\')
                {
                    backslashes++;
                    continue;
                }

                if (character == '"')
                {
                    builder.Append('\\', backslashes * 2 + 1);
                    builder.Append(character);
                    backslashes = 0;
                    continue;
                }

                builder.Append('\\', backslashes);
                builder.Append(character);
                backslashes = 0;
            }

            builder.Append('\\', backslashes * 2);
            builder.Append('"');
            return builder.ToString();
        }

        private sealed class PythonCommand
        {
            public PythonCommand(string executable, string prefixArguments)
            {
                Executable = executable;
                PrefixArguments = prefixArguments;
            }

            public string Executable { get; }
            public string PrefixArguments { get; }
        }

        private sealed class ProcessResult
        {
            public ProcessResult(int exitCode, string standardOutput, string standardError)
            {
                ExitCode = exitCode;
                StandardOutput = standardOutput;
                StandardError = standardError;
            }

            public int ExitCode { get; }
            public string StandardOutput { get; }
            public string StandardError { get; }
        }
    }
}
#endif
