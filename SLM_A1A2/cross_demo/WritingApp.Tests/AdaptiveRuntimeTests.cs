using WritingApp.Shared;
using WritingDemo.Core;

internal static class AdaptiveRuntimeTests
{
    public static IEnumerable<(string, Func<Task>)> Cases => new (string, Func<Task>)[]
    {
        ("partial GPU candidate remains eligible below 4 GiB", PartialBudget),
        ("CPU wins when integrated GPU is slower; usable partial GPU can win", Choice),
        ("device-lost load recovers in a fresh worker with fewer layers", PartialRecovery),
        ("cached placement avoids generating calibration answers again", Cached),
        ("lower memory invalidates an oversized cached placement", BudgetChanges),
        ("more memory recalibrates a substantially restricted placement", BudgetImproves),
        ("bounded recovery still considers a second GPU", SecondGpu),
        ("corrupt local profile is replaced by a traced new calibration", CorruptProfile),
        ("changing power mode during calibration does not persist a mixed profile", PowerChanges),
        ("technical CPU fallback expires instead of permanently excluding GPU", TransientFailure),
        ("failed GPU result is reused beyond five minutes", FailedGpuCache),
        ("GPU deadline follows CPU median with finite bounds", GpuDeadline),
        ("GPU generation timeout does not retry a nearly identical placement", NoRetryAfterTimeout),
        ("device loss during generation does not retry the same adapter", NoRetryAfterDeviceLoss),
        ("allocation failure during generation can recover with fewer layers", GenerationMemoryRecovery),
        ("two slow GPU samples cannot meet a three-sample median", StopSlowerGpu),
        ("invalid GPU sample stops qualification and preserves its trace", StopInvalidGpu),
        ("background calibration retains RAW but cannot persist a decision", BackgroundInterruption),
        ("cancellation frees a candidate and saves no completed profile", Cancellation),
        ("Vulkan generation failure invalidates profile without retrying the answer", GenerationFailure),
    };
    private static void Check(bool ok, string reason) { if (!ok) throw new Exception(reason); }
    private static GpuPlan Plan(int layers = 33) => new(0,"test-gpu","Synthetic GPU",4L<<30,4L<<30,layers,33,2L<<30,256L<<20,null);
    private static BackendTrial[] Samples(string backend,double seconds,string status="STRICT") =>
        Enumerable.Range(0,3).Select(_=>new BackendTrial(backend,seconds,120,"stop",status,null)).ToArray();
    private static Task PartialBudget()
    {
        var gpu=Plan(14) with {FreeBytes=2L<<30,TotalBytes=2L<<30,EstimatedBytes=1600L<<20};
        var result=AdaptiveRuntimePolicy.Candidates(new("fixture","driver",33,[gpu]));
        Check(result.Length==1&&result[0].GpuLayers==14,"must not reject a 2 GiB partial placement");
        Check(AdaptiveRuntimePolicy.Candidates(new("fixture","driver",33,[gpu with{FreeBytes=100}])).Length==0,"budget enforced");
        return Task.CompletedTask;
    }
    private static Task Choice()
    {
        var cpu=new PlacementTrial(RuntimePlacement.Cpu,Samples("CPU",37),null);
        var gpu=new PlacementTrial(new(0,"test-gpu",14),Samples("Vulkan",45),null);
        Check(AdaptiveRuntimePolicy.Choose([cpu,gpu]).Placement.GpuLayers==0,"slower iGPU must not win");
        Check(AdaptiveRuntimePolicy.Choose([cpu,gpu with{Samples=Samples("Vulkan",18)}]).Placement.GpuLayers==14,"partial acceleration should win");
        Check(AdaptiveRuntimePolicy.Choose([cpu,gpu with{Samples=Samples("Vulkan",5,"INCONSISTENT")}]).Placement.GpuLayers==0,"unusable output must not win");
        var emptyCpu=cpu with{Samples=Samples("CPU",0.01).Select(t=>t with{Tokens=0}).ToArray()};
        Check(AdaptiveRuntimePolicy.Choose([emptyCpu,gpu]).Placement.GpuLayers==14,"immediate EOS with no tokens is not a CPU performance result");
        return Task.CompletedTask;
    }
    private static async Task PartialRecovery()
    {
        using var temp=new Scratch();var scenario=new Scenario{FailFull=true};
        await using var engine=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        var state=await engine.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.Backend=="Vulkan"&&state.OffloadedLayers==32,"one-block CPU recovery");
        Check(scenario.Loads.SequenceEqual([0,33,32,32]),"bounded attempts and explicit final placement");
        Check(scenario.GenerationCalls==8,"one warmup and three samples per completed backend");
        Check(scenario.Workers.Select(w=>w.Number).Distinct().Count()==scenario.Workers.Count,"each candidate gets a fresh process adapter");
        Check(scenario.Workers.Take(scenario.Workers.Count-1).All(w=>w.Disposed),"failed and calibration workers disposed");
    }
    private static async Task Cached()
    {
        using var temp=new Scratch();var scenario=new Scenario{FailFull=true};
        await using(var first=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host"))
            await first.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        var generations=scenario.GenerationCalls;
        await using var second=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        var state=await second.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.OffloadedLayers==32&&scenario.GenerationCalls==generations,"cache should load directly");
    }
    private static async Task BudgetChanges()
    {
        using var temp=new Scratch();var scenario=new Scenario{FailFull=true};
        await using(var first=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host"))
            await first.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        scenario.EstimatedLayers=14;
        await using var second=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        var state=await second.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.OffloadedLayers==14,"must never reuse cached 32 under a 14-layer estimate");
    }
    private static async Task Cancellation()
    {
        using var temp=new Scratch();using var cts=new CancellationTokenSource();
        var scenario=new Scenario{Cancel=cts};
        await using var engine=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        try{await engine.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,cts.Token);throw new Exception("missing cancellation");}
        catch(OperationCanceledException){}
        Check(scenario.Workers.All(w=>w.Disposed),"cancelled worker must be freed");
        Check(!Directory.GetFiles(temp.Path,"*.json").Any(p=>!System.IO.Path.GetFileName(p).StartsWith("trace-")),"no completed profile");
    }
    private static async Task BudgetImproves()
    {
        using var temp=new Scratch();var scenario=new Scenario{EstimatedLayers=14};
        await using(var first=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host"))
            await first.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        var calls=scenario.GenerationCalls;scenario.EstimatedLayers=33;
        await using var second=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        var state=await second.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.OffloadedLayers==33&&scenario.GenerationCalls>calls,"larger budget should be evaluated again");
    }
    private static async Task SecondGpu()
    {
        using var temp=new Scratch();var scenario=new Scenario{ExtraDevice=true,FailPrimary=true};
        await using var engine=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        var state=await engine.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.AdapterId=="second-gpu","one failing adapter must not consume every GPU attempt");
        Check(engine.LastProfile!.Trials.Count(t=>t.Placement.GpuLayers>0)==3,"bounded GPU candidate count");
    }
    private static async Task CorruptProfile()
    {
        using var temp=new Scratch();var scenario=new Scenario();
        await using(var first=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host"))
            await first.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        var profile=Directory.GetFiles(temp.Path,"*.json").Single(p=>!System.IO.Path.GetFileName(p).StartsWith("trace-"));
        await File.WriteAllTextAsync(profile,"{broken");var calls=scenario.GenerationCalls;
        await using var second=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        await second.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(scenario.GenerationCalls>calls,"corrupt profile should not become a cached CPU decision");
    }
    private static async Task PowerChanges()
    {
        using var temp=new Scratch();var host="AC";var scenario=new Scenario{OnGenerate=()=>host="battery"};
        await using var engine=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,()=>host);
        var state=await engine.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.Backend=="CPU"&&state.FallbackReason!.Contains("no se guardó"),"mixed power conditions need a visible temporary choice");
        Check(Directory.GetFiles(temp.Path,"*.json").All(p=>System.IO.Path.GetFileName(p).StartsWith("trace-")),"no reusable mixed-condition profile");
    }
    private static async Task TransientFailure()
    {
        using var temp=new Scratch();var scenario=new Scenario{FailPrimary=true};
        await using(var first=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host"))
            await first.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        var file=Directory.GetFiles(temp.Path,"*.json").Single(p=>!System.IO.Path.GetFileName(p).StartsWith("trace-"));
        var profile=System.Text.Json.JsonSerializer.Deserialize(await File.ReadAllTextAsync(file),AppJsonContext.Default.AdaptiveProfile)!;
        await File.WriteAllTextAsync(file,System.Text.Json.JsonSerializer.Serialize(profile with{DateUtc=DateTimeOffset.UtcNow.AddHours(-25)},AppJsonContext.Default.AdaptiveProfile));
        scenario.FailPrimary=false;
        await using var second=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        var state=await second.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.Backend=="Vulkan","a transient GPU failure must not be a permanent CPU-only classification");
    }
    private static Task GpuDeadline()
    {
        PlacementTrial Cpu(double s)=>new(RuntimePlacement.Cpu,Samples("CPU",s),null);
        Check(AdaptiveRuntimePolicy.GpuGenerationTimeout(Cpu(22.5)).TotalSeconds==67.5,"F3-like timeout follows measured CPU");
        Check(AdaptiveRuntimePolicy.GpuGenerationTimeout(Cpu(.2)).TotalSeconds==20,"pipeline allowance floor");
        Check(AdaptiveRuntimePolicy.GpuGenerationTimeout(Cpu(100)).TotalSeconds==120,"deadline upper bound");
        Check(AdaptiveRuntimePolicy.GpuGenerationTimeout(new(RuntimePlacement.Cpu,[],"failed")).TotalSeconds==120,"no invalid CPU baseline arithmetic");
        return Task.CompletedTask;
    }
    private static async Task FailedGpuCache()
    {
        using var temp=new Scratch();var s=new Scenario{GpuGenerationError="timeout"};
        await using(var first=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host")) await first.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);
        var file=Directory.GetFiles(temp.Path,"*.json").Single(p=>!System.IO.Path.GetFileName(p).StartsWith("trace-"));
        var profile=System.Text.Json.JsonSerializer.Deserialize(await File.ReadAllTextAsync(file),AppJsonContext.Default.AdaptiveProfile)!;
        await File.WriteAllTextAsync(file,System.Text.Json.JsonSerializer.Serialize(profile with{DateUtc=DateTimeOffset.UtcNow.AddHours(-2)},AppJsonContext.Default.AdaptiveProfile));
        var count=s.GenerationCalls;s.GpuGenerationError=null;
        await using var second=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host");
        var state=await second.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.Backend=="CPU"&&s.GenerationCalls==count,"do not repeat known failure every five minutes");
    }
    private static async Task NoRetryAfterTimeout()
    {
        using var temp=new Scratch();var s=new Scenario{GpuGenerationError="timeout"};
        await using var engine=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host");
        var state=await engine.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.Backend=="CPU"&&s.Loads.SequenceEqual([0,33,0]),"no 32-layer retry after a generation hang");
        Check(engine.LastProfile!.Trials.Last().FailureStage=="timeout","typed failure retained");
        Check(s.Workers.Where(w=>w.GpuGenerations>0).All(w=>w.GenerationTimeout.TotalSeconds==60),"deadline delivered to actual candidate workers");
    }
    private static async Task NoRetryAfterDeviceLoss()
    {
        using var temp=new Scratch();var s=new Scenario{GpuGenerationError="device lost"};
        await using var engine=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host");
        await engine.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);
        Check(s.Loads.SequenceEqual([0,33,0])&&engine.LastProfile!.Trials.Last().FailureStage=="generation","device loss does not trigger almost identical GPU work");
    }
    private static async Task GenerationMemoryRecovery()
    {
        using var temp=new Scratch();var s=new Scenario{FullGenerationAllocationFailure=true};
        await using var engine=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host");
        var state=await engine.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.OffloadedLayers==32&&engine.LastProfile!.Trials[1].FailureStage=="memory","keep partial offloading recovery for explicit allocation errors");
    }
    private static async Task StopSlowerGpu()
    {
        using var temp=new Scratch();var s=new Scenario{GpuSeconds=25};
        await using var engine=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host");
        var state=await engine.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);
        var gpu=engine.LastProfile!.Trials.Last();
        Check(state.Backend=="CPU"&&gpu.Samples.Length==2&&gpu.FailureStage=="slower"&&s.GenerationCalls==7,"third GPU sample cannot make the median eligible");
    }
    private static async Task StopInvalidGpu()
    {
        using var temp=new Scratch();var s=new Scenario{GpuInvalid=true};
        await using var engine=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host");
        var state=await engine.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);
        Check(state.Backend=="CPU"&&engine.LastProfile!.Trials.Last().Samples.Length==1&&s.GenerationCalls==6,"one invalid real sample rules out three usable samples");
        Check(Directory.GetFiles(temp.Path,"trace-*.json").Length==6,"retain complete invalid output too");
    }
    private static async Task BackgroundInterruption()
    {
        using var temp=new Scratch();var allowed=true;var s=new Scenario{OnGenerate=()=>allowed=false};
        await using var engine=new AdaptiveInferenceEngine(s.Factory,temp.Path,"host",()=>allowed);
        try { await engine.LoadAsync(Model,"fixture",BackendPreference.AutoVulkanCpu,2048,default);throw new Exception("background operation was accepted"); }
        catch(CalibrationInterruptedException) { }
        Check(engine.LastProfile is null&&s.Workers.All(w=>w.Disposed),"no cached decision or live worker");
        var files=Directory.GetFiles(temp.Path,"*.json");
        Check(files.Length==1&&System.IO.Path.GetFileName(files[0]).StartsWith("trace-"),"complete RAW retained without a completed profile");
        var trace=System.Text.Json.JsonSerializer.Deserialize(await File.ReadAllTextAsync(files[0]),AppJsonContext.Default.CalibrationTrace)!;
        Check(!trace.ForegroundValid,"background sample cannot be reused as timing evidence");
    }
    private static async Task GenerationFailure()
    {
        using var temp=new Scratch();var scenario=new Scenario();
        await using var engine=new AdaptiveInferenceEngine(scenario.Factory,temp.Path,"host");
        await engine.LoadAsync(Model,"fixture.gguf",BackendPreference.AutoVulkanCpu,2048,default);
        var calls=scenario.GenerationCalls;scenario.FailGeneration=true;
        try{await engine.GenerateAsync(BackendCalibrationPolicy.Exercise,"fixture",42,default);throw new Exception("failure missing");}
        catch(IOException){}
        Check(scenario.GenerationCalls==calls+1,"technical failure must not retry");
        Check(Directory.GetFiles(temp.Path,"*.failed-*").Length==1,"failed profile archived");
        Check(scenario.Workers.All(w=>w.Disposed),"faulty worker disposed");
    }
    private static ModelEntry Model=>PortableCatalog.All.First(m=>m.Id=="13-gemma4-e2b-ud-q4-k-xl");
    private sealed class Scenario
    {
        public bool FailFull,FailGeneration,ExtraDevice,FailPrimary;
        public bool FullGenerationAllocationFailure,GpuInvalid;
        public string? GpuGenerationError;
        public double GpuSeconds=5;
        public int EstimatedLayers=33,GenerationCalls;
        public CancellationTokenSource? Cancel;
        public Action? OnGenerate;
        public List<int> Loads=[];
        public List<Fake> Workers=[];
        public IPlacementEngine Factory(bool gpu){var w=new Fake(this,Workers.Count);Workers.Add(w);return w;}
    }
    private sealed class Fake(Scenario scenario,int number):IPlacementEngine
    {
        public int Number=>number;
        public bool Disposed;
        public int GpuGenerations;
        private RuntimePlacement _placement=RuntimePlacement.Cpu;
        public TimeSpan GenerationTimeout{get;set;}
        public Task<RuntimeInventory> InspectAsync(string p,int c,CancellationToken ct)=>Task.FromResult(new RuntimeInventory("fixture","driver",33,
            scenario.ExtraDevice?[Plan(scenario.EstimatedLayers),Plan() with{Index=1,Id="second-gpu",IsIntegrated=true}]:[Plan(scenario.EstimatedLayers)]));
        public Task<EngineState> LoadPlacementAsync(ModelEntry m,string p,RuntimePlacement placement,int c,CancellationToken ct)
        {
            scenario.Loads.Add(placement.GpuLayers);_placement=placement;
            if((scenario.FailFull&&placement.GpuLayers==33)||(scenario.FailPrimary&&placement.DeviceId=="test-gpu"))throw new IOException("VK_ERROR_DEVICE_LOST");
            return Task.FromResult(new EngineState(placement.GpuLayers==0?BackendPreference.Cpu:BackendPreference.Vulkan,
                placement.GpuLayers==0?"CPU":"Vulkan","Synthetic GPU",placement.GpuLayers,null,c,"writing_json_grammar_v1",33,placement.DeviceId));
        }
        public Task<EngineState> LoadAsync(ModelEntry m,string p,BackendPreference b,int c,CancellationToken ct)=>LoadPlacementAsync(m,p,RuntimePlacement.Cpu,c,ct);
        public Task<EngineOutput> GenerateAsync(WritingExercise e,string text,int seed,CancellationToken ct)
        {
            scenario.GenerationCalls++;
            if(_placement.GpuLayers>0)
            {
                GpuGenerations++;
                if(scenario.GpuGenerationError=="timeout")throw new TimeoutException("synthetic generation timeout");
                if(scenario.GpuGenerationError is { } error)throw new IOException(error);
                if(scenario.FullGenerationAllocationFailure&&_placement.GpuLayers==33)throw new IOException("VK_ERROR_OUT_OF_DEVICE_MEMORY");
            }
            scenario.OnGenerate?.Invoke();
            if(scenario.FailGeneration)throw new IOException("device lost");
            if(scenario.Cancel is not null){scenario.Cancel.Cancel();ct.ThrowIfCancellationRequested();}
            const string output="{\"is_correct\":false,\"corrected_text\":\"I wake up at seven. I eat breakfast at home.\",\"errors\":[{\"original\":\"wakes\",\"correction\":\"wake\",\"type\":\"verb\",\"explanation\":\"Use wake after I.\"}],\"feedback\":\"\"}";
            return Task.FromResult(new EngineOutput(scenario.GpuInvalid&&_placement.GpuLayers>0?"{}":output,"stop",_placement.GpuLayers==0?20:scenario.GpuSeconds,null,new(100,100,100,1,1,false)));
        }
        public Task UnloadAsync(){Disposed=true;return Task.CompletedTask;}
        public ValueTask DisposeAsync(){Disposed=true;return ValueTask.CompletedTask;}
    }
    private sealed class Scratch:IDisposable
    {
        public string Path{get;}=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"writing-adaptive-test-"+Guid.NewGuid().ToString("N"));
        public Scratch()=>Directory.CreateDirectory(Path);
        public void Dispose()
        {
            var resolved=System.IO.Path.GetFullPath(Path);
            Check(resolved.StartsWith(System.IO.Path.GetFullPath(System.IO.Path.GetTempPath()),StringComparison.OrdinalIgnoreCase)&&
                System.IO.Path.GetFileName(resolved).StartsWith("writing-adaptive-test-"),"unsafe cleanup path");
            Directory.Delete(resolved,true);
        }
    }
}
