using System.Net;
using System.Text;
using System.Text.Json;
using WritingDemo.Core;

var tests = new (string Name, Func<Task> Run)[]
{
    ("ArgumentList keeps paths safe and pins server flags", TestServerArgumentsAsync),
    ("backend preference parsing and strict Vulkan device names", TestBackendParsingAsync),
    ("no reported Vulkan GPU chooses CPU only once", TestNoVulkanDeviceFallsBackToCpuAsync),
    ("Vulkan startup failure retries once with CPU", TestVulkanStartupFailureFallsBackOnceAsync),
    ("cancellation, bad package hash, and rate limit never fall back", TestTerminalBackendFailuresAsync),
    ("explicit Vulkan never falls back and uses the exact device", TestExplicitVulkanAndArgumentsAsync),
    ("CPU arguments disable GPU, KV, and op offload", TestCpuArgumentsAsync),
    ("child process environment is package-scoped without backend-path override", TestRuntimeProcessEnvironmentAsync),
    ("Vulkan offload evidence comes from the server log", TestOffloadEvidenceAsync),
    ("offload log can be read while the server keeps it open", TestSharedLogReadAsync),
    ("runtime manifest paths cannot escape the LAB package", TestRuntimeManifestPathSafetyAsync),
    ("unlisted DLLs and EXEs are rejected from the runtime package", TestUnlistedPackageBinaryAsync),
    ("request uses the literal prompt template and manifest sampling values", TestRequestBodyAsync),
    ("strict health requires a JSON status object", TestHealthJsonAsync),
    ("fake HTTP preserves the exact API JSON and response fields", TestSuccessfulFakeHttpAsync),
    ("HTTP 429 is captured and never retried", TestRateLimitIsNotRetriedAsync),
    ("generation honors caller cancellation", TestCallerCancellationAsync),
    ("reasoning content and nonempty think tags fail visibly", TestReasoningLeaksAsync)
};

var failures = new List<string>();
foreach (var test in tests)
{
    try
    {
        await test.Run();
        Console.WriteLine($"PASS {test.Name}");
    }
    catch (Exception ex)
    {
        failures.Add($"FAIL {test.Name}: {ex}");
        Console.Error.WriteLine(failures[^1]);
    }
}

Console.WriteLine($"{tests.Length - failures.Count}/{tests.Length} runtime checks passed.");
return failures.Count == 0 ? 0 : 1;

static Task TestServerArgumentsAsync()
{
    const string server = @"C:\runtime folder\llama-server.exe";
    const string model = @"D:\models\with spaces\selected.gguf";
    const string serverLog = @"C:\logs\server output.log";
    var port = LlamaRuntime.DedicatedPortStart + 2;
    var info = LlamaRuntime.CreateServerStartInfo(server, model, serverLog, port, true, @"C:\runtime folder");
    var args = info.ArgumentList.ToArray();

    Assert(info.UseShellExecute is false, "shell execution must be disabled");
    Assert(info.RedirectStandardOutput && info.RedirectStandardError, "both server streams should be captured");
    Assert(args.Contains("-m") && args[Array.IndexOf(args, "-m") + 1] == Path.GetFullPath(model), "model path must be one safe argument");
    Assert(args.Contains(Path.GetFullPath(serverLog)), "server log path must be one safe argument");
    Assert(args.Contains("--host") && args[Array.IndexOf(args, "--host") + 1] == "127.0.0.1", "server must bind loopback");
    Assert(args.Contains("--port") && args[Array.IndexOf(args, "--port") + 1] == port.ToString(), "dedicated port must be passed");
    Assert(!Enumerable.Range(8101, 16).Contains(port), "demo port overlaps the benchmark range");
    Assert(HasPair(args, "-c", "4096"), "context must be 4096");
    Assert(HasPair(args, "--parallel", "1"), "parallelism must be 1");
    Assert(HasPair(args, "-ngl", "999"), "GPU layers must be 999");
    Assert(HasPair(args, "-s", "42"), "server seed must be 42");
    Assert(HasPair(args, "--reasoning", "off"), "reasoning must be off");
    Assert(HasPair(args, "--reasoning-budget", "0"), "reasoning budget must be zero");
    Assert(HasPair(args, "--chat-template-kwargs", "{\"enable_thinking\":false}"), "native thinking toggle must be false");
    Assert(!args.Contains("--grammar") && !args.Contains("--json-schema"), "constrained output flags are forbidden");

    var noToggle = LlamaRuntime.CreateServerStartInfo(server, model, serverLog, port, false, @"C:\runtime folder");
    Assert(!noToggle.ArgumentList.Contains("--chat-template-kwargs"), "families without a native toggle must keep the native template defaults");
    return Task.CompletedTask;
}

static Task TestBackendParsingAsync()
{
    Assert(BackendSelectionPolicy.TryParsePreference("AutoVulkanCpu", out var automatic)
        && automatic == RuntimePreference.AutoVulkanCpu, "auto backend option should parse");
    Assert(BackendSelectionPolicy.TryParsePreference("cpu", out var cpu)
        && cpu == RuntimePreference.Cpu, "CPU backend option should parse case-insensitively");
    Assert(!BackendSelectionPolicy.TryParsePreference("cuda-with-fallback", out _), "unknown backend strings must be rejected");

    var devices = BackendSelectionPolicy.ParseVulkanDevices(
        "Available devices:\r\n  CUDA0: NVIDIA CUDA (8000 MiB, 7000 MiB free)\r\n  Vulkan0: NVIDIA RTX 3070 (8192 MiB, 7000 MiB free)\r\n  Vulkan0: duplicate\r\n");
    Assert(devices.SequenceEqual(["Vulkan0"]), "only unique Vulkan device records should parse");
    Assert(BackendSelectionPolicy.ParseVulkanDevices("Available devices:\n  (none)\n  CUDA0: CUDA device\n").Count == 0,
        "CPU/CUDA/none rows must not count as Vulkan GPUs");
    return Task.CompletedTask;
}

static async Task TestNoVulkanDeviceFallsBackToCpuAsync()
{
    var cpuStarts = 0;
    var vulkanStarts = 0;
    var decision = await BackendSelectionPolicy.StartAsync(
        RuntimePreference.AutoVulkanCpu,
        _ => Task.FromResult("Available devices:\n  (none)\n"),
        (_, _) => { vulkanStarts++; return Task.CompletedTask; },
        _ => { cpuStarts++; return Task.CompletedTask; },
        CancellationToken.None);

    Assert(decision.ActualBackend == "CPU" && decision.Device is null, "no Vulkan GPU must select CPU");
    Assert(decision.FallbackReason is not null, "automatic CPU selection must explain why it fell back");
    Assert(cpuStarts == 1 && vulkanStarts == 0, "no-device policy must start CPU once without a Vulkan launch");
}

static async Task TestVulkanStartupFailureFallsBackOnceAsync()
{
    var cpuStarts = 0;
    var vulkanStarts = 0;
    var decision = await BackendSelectionPolicy.StartAsync(
        RuntimePreference.AutoVulkanCpu,
        _ => Task.FromResult("Available devices:\n  Vulkan0: synthetic GPU (8 MiB, 8 MiB free)\n"),
        (_, _) =>
        {
            vulkanStarts++;
            throw new VulkanStartupFailureException("synthetic driver startup error");
        },
        _ => { cpuStarts++; return Task.CompletedTask; },
        CancellationToken.None);

    Assert(decision.ActualBackend == "CPU" && decision.FallbackReason!.Contains("synthetic driver", StringComparison.Ordinal),
        "automatic startup failure should record a CPU fallback reason");
    Assert(vulkanStarts == 1 && cpuStarts == 1, "only one Vulkan and one CPU startup attempt are allowed");
}

static async Task TestTerminalBackendFailuresAsync()
{
    using (var cancellation = new CancellationTokenSource())
    {
        var cpuStarts = 0;
        try
        {
            await BackendSelectionPolicy.StartAsync(
                RuntimePreference.AutoVulkanCpu,
                token =>
                {
                    cancellation.Cancel();
                    token.ThrowIfCancellationRequested();
                    return Task.FromResult("Available devices:\n  Vulkan0: synthetic GPU\n");
                },
                (_, _) => Task.CompletedTask,
                _ => { cpuStarts++; return Task.CompletedTask; },
                cancellation.Token);
            throw new InvalidOperationException("Expected caller cancellation.");
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
        Assert(cpuStarts == 0, "caller cancellation must not launch CPU fallback");
    }

    await AssertNoFallbackForExceptionAsync(
        new InvalidDataException("synthetic package hash mismatch"), "wrong package hash");
    await AssertNoFallbackForExceptionAsync(
        new LlamaRateLimitException("synthetic HTTP 429"), "HTTP 429");
}

static async Task AssertNoFallbackForExceptionAsync(Exception error, string label)
{
    var cpuStarts = 0;
    try
    {
        await BackendSelectionPolicy.StartAsync(
            RuntimePreference.AutoVulkanCpu,
            _ => Task.FromException<string>(error),
            (_, _) => Task.CompletedTask,
            _ => { cpuStarts++; return Task.CompletedTask; },
            CancellationToken.None);
        throw new InvalidOperationException($"Expected {label} to remain terminal.");
    }
    catch (Exception ex) when (ReferenceEquals(ex, error)) { }
    Assert(cpuStarts == 0, $"{label} must not start CPU fallback");
}

static async Task TestExplicitVulkanAndArgumentsAsync()
{
    var cpuStarts = 0;
    try
    {
        await BackendSelectionPolicy.StartAsync(
            RuntimePreference.Vulkan,
            _ => Task.FromResult("Available devices:\n  Vulkan0: synthetic GPU\n"),
            (_, _) => throw new VulkanStartupFailureException("synthetic startup failure"),
            _ => { cpuStarts++; return Task.CompletedTask; },
            CancellationToken.None);
        throw new InvalidOperationException("Explicit Vulkan should surface startup failure.");
    }
    catch (InvalidOperationException ex) when (ex.Message.Contains("Vulkan", StringComparison.Ordinal)) { }
    Assert(cpuStarts == 0, "explicit Vulkan must not fall back to CPU");

    var info = LlamaRuntime.CreateBackendServerStartInfo(
        @"C:\runtime folder\llama-server.exe",
        @"D:\models\model.gguf",
        @"C:\logs\server.log",
        LlamaRuntime.DedicatedPortStart + 1,
        true,
        @"C:\runtime folder",
        RuntimePreference.Vulkan,
        "Vulkan0");
    var args = info.ArgumentList.ToArray();
    Assert(HasPair(args, "--device", "Vulkan0") && HasPair(args, "-ngl", "999"),
        "Vulkan must pass the exact probed device and GPU layer count");
    Assert(Array.IndexOf(args, "--device") < Array.IndexOf(args, "-ngl"), "device selection should precede layer offload flags");
    Assert(HasPair(args, "--chat-template-kwargs", "{\"enable_thinking\":false}"),
        "native thinking toggle must remain unchanged for Vulkan");
}

static Task TestCpuArgumentsAsync()
{
    var info = LlamaRuntime.CreateBackendServerStartInfo(
        @"C:\runtime folder\llama-server.exe",
        @"D:\models\model.gguf",
        @"C:\logs\server.log",
        LlamaRuntime.DedicatedPortStart + 3,
        false,
        @"C:\runtime folder",
        RuntimePreference.Cpu,
        null);
    var args = info.ArgumentList.ToArray();
    Assert(HasPair(args, "--device", "none") && HasPair(args, "-ngl", "0"), "CPU must disable GPU layer offload");
    Assert(args.Contains("--no-kv-offload") && args.Contains("--no-op-offload"),
        "CPU must disable KV and host-op offload");
    Assert(!args.Contains("--chat-template-kwargs"), "CPU must preserve native thinking defaults when no toggle is declared");
    Assert(HasPair(args, "--parallel", "1") && HasPair(args, "-s", "42")
        && HasPair(args, "--reasoning", "off") && HasPair(args, "--reasoning-budget", "0"),
        "CPU runtime flags must preserve the existing sampling/thinking setup");
    return Task.CompletedTask;
}

static Task TestRuntimeProcessEnvironmentAsync()
{
    var packageDirectory = Path.GetFullPath(Path.Combine(Path.GetTempPath(), $"runtime-package-{Guid.NewGuid():N}"));
    var serverPath = Path.Combine(packageDirectory, "llama-server.exe");
    var startInfo = VulkanProbeProcess.CreateStartInfo(serverPath, packageDirectory);
    startInfo.Environment["GGML_BACKEND_PATH"] = @"C:\foreign\ggml-plugins\ggml-backend.dll";
    startInfo.Environment["LLAMA_ARG_DEVICE"] = "CUDA0";
    startInfo.Environment["LLAMA_ARG_N_GPU_LAYERS"] = "999";
    startInfo.Environment["LLAMA_ARG_DEVICE_DRAFT"] = "CUDA0";
    startInfo.Environment["LLAMA_ARG_N_GPU_LAYERS_DRAFT"] = "999";

    LlamaRuntime.ConfigureVerifiedPackageEnvironment(startInfo, packageDirectory);

    var expectedSystemDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32");
    var expectedPath = packageDirectory + Path.PathSeparator + expectedSystemDirectory;
    Assert(startInfo.WorkingDirectory == packageDirectory, "probe working directory must be the verified package directory");
    Assert(!startInfo.Environment.ContainsKey("GGML_BACKEND_PATH"), "inherited backend plugin path must be removed");
    Assert(startInfo.Environment["PATH"] == expectedPath, "child PATH must begin and end with only the package and Windows system directories");
    Assert(!startInfo.Environment.ContainsKey("LLAMA_ARG_DEVICE")
        && !startInfo.Environment.ContainsKey("LLAMA_ARG_N_GPU_LAYERS")
        && !startInfo.Environment.ContainsKey("LLAMA_ARG_DEVICE_DRAFT")
        && !startInfo.Environment.ContainsKey("LLAMA_ARG_N_GPU_LAYERS_DRAFT"),
        "inherited GPU-selection overrides must be removed from child processes");
    return Task.CompletedTask;
}

static Task TestOffloadEvidenceAsync()
{
    Assert(LlamaRuntime.ParseOffloadedLayers("llama_model_load: offloaded 31/32 layers to GPU\n") == 31,
        "positive GPU layer count should be parsed from the server log");
    Assert(LlamaRuntime.ParseOffloadedLayers("llama_model_load: offloaded 0/32 layers to GPU\n") == 0,
        "zero GPU layers must not count as actual Vulkan offload");
    Assert(LlamaRuntime.ParseOffloadedLayers("server ready, no model offload summary\n") == 0,
        "missing GPU evidence must not be guessed from a Vulkan executable");
    return Task.CompletedTask;
}

static async Task TestSharedLogReadAsync()
{
    var path = Path.Combine(Path.GetTempPath(), $"writing-demo-server-log-{Guid.NewGuid():N}.log");
    try
    {
        await File.WriteAllTextAsync(path, "llama_model_load: offloaded 19/20 layers to GPU\n");
        await using var serverLikeWriter = new FileStream(path, FileMode.Open, FileAccess.ReadWrite,
            FileShare.ReadWrite | FileShare.Delete, 4096, FileOptions.Asynchronous);
        var content = await LlamaRuntime.ReadSharedLogFileAsync(path, CancellationToken.None);
        Assert(content.Contains("offloaded 19/20 layers to GPU", StringComparison.Ordinal),
            "the active server log should remain readable while its writer handle is open");
    }
    finally
    {
        if (File.Exists(path)) File.Delete(path);
    }
}

static Task TestRuntimeManifestPathSafetyAsync()
{
    Assert(RuntimePackageVerifier.NormalizeRelativePath("tools/llama.cpp/b11457-vulkan/llama-server.exe")
        == "tools/llama.cpp/b11457-vulkan/llama-server.exe", "pinned manifest path should normalize");
    AssertThrows<InvalidDataException>(() => RuntimePackageVerifier.NormalizeRelativePath("../foreign/llama-server.exe"),
        "parent traversal must be rejected");
    AssertThrows<InvalidDataException>(() => RuntimePackageVerifier.NormalizeRelativePath(@"C:\foreign\llama-server.exe"),
        "absolute manifest paths must be rejected");
    return Task.CompletedTask;
}

static Task TestUnlistedPackageBinaryAsync()
{
    var root = Path.Combine(Path.GetTempPath(), $"writing-demo-package-{Guid.NewGuid():N}");
    Directory.CreateDirectory(root);
    try
    {
        var server = Path.Combine(root, "llama-server.exe");
        var backend = Path.Combine(root, "ggml-vulkan.dll");
        var foreign = Path.Combine(root, "foreign-backend.dll");
        var license = Path.Combine(root, "license-llvm-openmp");
        File.WriteAllBytes(server, [1]);
        File.WriteAllBytes(backend, [2]);
        File.WriteAllBytes(foreign, [3]);
        File.WriteAllText(license, "synthetic package license");

        AssertThrows<InvalidDataException>(
            () => RuntimePackageVerifier.ValidateBinaryInventory(root, [server, backend, license]),
            "unlisted DLLs must be rejected before launch");
        File.Delete(foreign);
        RuntimePackageVerifier.ValidateBinaryInventory(root, [server, backend, license]);
    }
    finally
    {
        if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
    }
    return Task.CompletedTask;
}

static Task TestRequestBodyAsync()
{
    using var generationDoc = JsonDocument.Parse("""
        {"max_tokens":512,"seed":42,"reasoning_budget_tokens":0,"temperature":0.7,"top_p":0.8,"top_k":20,"min_p":0.0,"repeat_penalty":1.0,"presence_penalty":1.5,"frequency_penalty":0.0}
        """);
    var exercise = SyntheticExercise();
    const string studentText = "I has a cat.";
    var prompt = LlamaRuntime.BuildUserPrompt(exercise, studentText);
    Assert(prompt == "Level: A1\nTask: Write three synthetic sentences.\nStudent text: I has a cat.", "the exact user prompt template changed");

    var request = LlamaRuntime.BuildRequestJson(generationDoc.RootElement, "synthetic system prompt", exercise, studentText);
    using var body = JsonDocument.Parse(request);
    var root = body.RootElement;
    Assert(root.GetProperty("stream").GetBoolean() is false, "stream must be false");
    var messages = root.GetProperty("messages");
    Assert(messages.GetArrayLength() == 2, "exactly system and user messages are required");
    Assert(messages[0].GetProperty("content").GetString() == "synthetic system prompt", "system prompt must be copied literally");
    Assert(messages[1].GetProperty("content").GetString() == prompt, "user prompt must be copied literally");
    foreach (var property in generationDoc.RootElement.EnumerateObject())
        Assert(root.GetProperty(property.Name).GetRawText() == property.Value.GetRawText(), $"generation field {property.Name} changed");
    Assert(!request.Contains("GOLD_SENTINEL", StringComparison.Ordinal), "correct example leaked into the request");
    Assert(!request.Contains("INCORRECT_SENTINEL", StringComparison.Ordinal), "incorrect example leaked into the request");
    Assert(!root.TryGetProperty("response_format", out _) && !root.TryGetProperty("grammar", out _), "no constrained decoding field may be added");
    return Task.CompletedTask;
}

static Task TestHealthJsonAsync()
{
    Assert(LlamaRuntime.IsStrictHealthyJson("{\"status\":\"ok\"}"), "canonical health JSON should pass");
    Assert(!LlamaRuntime.IsStrictHealthyJson("ok"), "plain text must not pass the JSON health check");
    Assert(!LlamaRuntime.IsStrictHealthyJson("{\"status\":\"loading\"}"), "non-ok JSON must not pass");
    Assert(!LlamaRuntime.IsStrictHealthyJson("{\"message\":\"ok\"}"), "a different field must not pass");
    Assert(!LlamaRuntime.IsStrictHealthyJson("[]"), "a JSON array must not pass");
    return Task.CompletedTask;
}

static async Task TestSuccessfulFakeHttpAsync()
{
    using var generationDoc = JsonDocument.Parse("""{"max_tokens":512,"reasoning_budget_tokens":0,"seed":42,"temperature":0.7}""");
    const string responseJson = "{\"choices\":[{\"message\":{\"content\":\"  synthetic response\\n\"},\"finish_reason\":\"stop\"}],\"usage\":{\"completion_tokens\":4}}";
    var handler = new FakeHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new StringContent(responseJson, Encoding.UTF8, "application/json")
    }));
    using var client = new HttpClient(handler);
    string? capturedRequest = null;
    string? capturedResponse = null;
    HttpStatusCode? capturedStatus = null;

    var result = await LlamaRuntime.SendGenerationRequestAsync(
        client,
        new Uri("http://127.0.0.1:18432/"),
        generationDoc.RootElement,
        "synthetic system prompt",
        SyntheticExercise(),
        "I has a cat.",
        TimeSpan.FromSeconds(2),
        CancellationToken.None,
        CancellationToken.None,
        (request, status, response) =>
        {
            capturedRequest = request;
            capturedStatus = status;
            capturedResponse = response;
            return Task.CompletedTask;
        });

    Assert(handler.CallCount == 1, "a successful completion must make one HTTP request");
    Assert(handler.RequestBody is not null && handler.RequestBody == capturedRequest, "capture must preserve the exact request sent");
    Assert(capturedStatus == HttpStatusCode.OK && capturedResponse == responseJson, "capture must preserve the exact API JSON");
    Assert(result.ApiJson == responseJson, "GenerationResult.ApiJson must be the exact response body");
    Assert(result.Content == "  synthetic response\n", "response content must retain its exact whitespace");
    Assert(result.FinishReason == "stop", "finish_reason must be returned exactly");
    Assert(result.ElapsedSeconds >= 0, "elapsed time must be present");
}

static async Task TestRateLimitIsNotRetriedAsync()
{
    using var generationDoc = JsonDocument.Parse("""{"max_tokens":512,"reasoning_budget_tokens":0,"seed":42}""");
    const string responseJson = "{\"error\":{\"message\":\"synthetic rate limit\"}}";
    var handler = new FakeHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.TooManyRequests)
    {
        Content = new StringContent(responseJson, Encoding.UTF8, "application/json")
    }));
    using var client = new HttpClient(handler);
    var captured = false;
    try
    {
        await LlamaRuntime.SendGenerationRequestAsync(
            client,
            new Uri("http://127.0.0.1:18432/"),
            generationDoc.RootElement,
            "synthetic system prompt",
            SyntheticExercise(),
            "synthetic student text",
            TimeSpan.FromSeconds(2),
            CancellationToken.None,
            CancellationToken.None,
            (_, status, body) =>
            {
                captured = status == HttpStatusCode.TooManyRequests && body == responseJson;
                return Task.CompletedTask;
            });
        throw new InvalidOperationException("Expected a rate-limit exception.");
    }
    catch (LlamaRateLimitException ex)
    {
        Assert(ex.ResponseBody == responseJson, "rate-limit body must be retained for the handoff");
    }
    Assert(handler.CallCount == 1, "HTTP 429 must never be retried");
    Assert(captured, "the exact HTTP 429 body must be captured");
}

static async Task TestCallerCancellationAsync()
{
    using var generationDoc = JsonDocument.Parse("""{"max_tokens":512,"reasoning_budget_tokens":0,"seed":42}""");
    var handler = new FakeHandler(async (_, token) =>
    {
        await Task.Delay(Timeout.InfiniteTimeSpan, token);
        return new HttpResponseMessage(HttpStatusCode.OK);
    });
    using var client = new HttpClient(handler);
    using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));
    try
    {
        await LlamaRuntime.SendGenerationRequestAsync(
            client,
            new Uri("http://127.0.0.1:18432/"),
            generationDoc.RootElement,
            "synthetic system prompt",
            SyntheticExercise(),
            "synthetic student text",
            TimeSpan.FromSeconds(2),
            cancellation.Token,
            CancellationToken.None);
        throw new InvalidOperationException("Expected caller cancellation.");
    }
    catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
    Assert(handler.CallCount == 1, "caller cancellation must not cause a retry");
}

static async Task TestReasoningLeaksAsync()
{
    using var generationDoc = JsonDocument.Parse("""{"max_tokens":512,"reasoning_budget_tokens":0,"seed":42}""");
    var withReasoningField = "{\"choices\":[{\"message\":{\"content\":\"visible\",\"reasoning_content\":\"private reasoning\"},\"finish_reason\":\"stop\"}]}";
    await AssertInvalidResponseAsync(generationDoc.RootElement, withReasoningField, "reasoning_content");
    var withThinkTags = "{\"choices\":[{\"message\":{\"content\":\"<think>private reasoning</think>answer\"},\"finish_reason\":\"stop\"}]}";
    await AssertInvalidResponseAsync(generationDoc.RootElement, withThinkTags, "<think>");
    var secondThinkTagIsNotHidden = "{\"choices\":[{\"message\":{\"content\":\"<think></think><think>private reasoning</think>answer\"},\"finish_reason\":\"stop\"}]}";
    await AssertInvalidResponseAsync(generationDoc.RootElement, secondThinkTagIsNotHidden, "<think>");
}

static async Task AssertInvalidResponseAsync(JsonElement generation, string responseJson, string expectedMessage)
{
    var handler = new FakeHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new StringContent(responseJson, Encoding.UTF8, "application/json")
    }));
    using var client = new HttpClient(handler);
    try
    {
        await LlamaRuntime.SendGenerationRequestAsync(
            client,
            new Uri("http://127.0.0.1:18432/"),
            generation,
            "synthetic system prompt",
            SyntheticExercise(),
            "synthetic student text",
            TimeSpan.FromSeconds(2),
            CancellationToken.None,
            CancellationToken.None);
        throw new InvalidOperationException("Expected an invalid-data exception for reasoning leakage.");
    }
    catch (InvalidDataException ex)
    {
        Assert(ex.Message.Contains(expectedMessage, StringComparison.Ordinal), "reasoning failure must be explicit");
    }
    Assert(handler.CallCount == 1, "reasoning output must not trigger another completion request");
}

static WritingExercise SyntheticExercise() => new(
    "synthetic-id",
    "A1",
    "synthetic title",
    "Write three synthetic sentences.",
    "GOLD_SENTINEL",
    "INCORRECT_SENTINEL");

static bool HasPair(string[] args, string name, string value)
{
    var index = Array.IndexOf(args, name);
    return index >= 0 && index + 1 < args.Length && args[index + 1] == value;
}

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

static void AssertThrows<TException>(Action action, string message) where TException : Exception
{
    try
    {
        action();
    }
    catch (TException)
    {
        return;
    }
    throw new InvalidOperationException(message);
}

sealed class FakeHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> respond)
    : HttpMessageHandler
{
    public int CallCount { get; private set; }
    public string? RequestBody { get; private set; }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        CallCount++;
        RequestBody = request.Content is null ? null : await request.Content.ReadAsStringAsync(cancellationToken);
        return await respond(request, cancellationToken);
    }
}
