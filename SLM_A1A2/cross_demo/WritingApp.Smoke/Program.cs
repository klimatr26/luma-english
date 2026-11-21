using System.Runtime.InteropServices;
using System.Text.Json;
using WritingApp.Shared;
using WritingApp.Native;
using WritingDemo.Core;

if(args.Length==3 && args[0]=="--parse-phone")
{
    using var data=JsonDocument.Parse(await File.ReadAllTextAsync(args[1]));
    var rootElement=data.RootElement;
    var raw=rootElement.GetProperty("raw").GetString()!;
    var user=rootElement.GetProperty("input").GetProperty("user_prompt").GetString()!;
    const string marker="\nStudent text: ";
    var position=user.IndexOf(marker,StringComparison.Ordinal);
    if(position<0) throw new InvalidDataException("Missing synthetic student input.");
    var parsed=FeedbackParser.Parse(raw,user[(position+marker.Length)..]);
    if(File.Exists(args[2])) throw new IOException("Refusing to overwrite parsed evidence.");
    await File.WriteAllTextAsync(args[2],JsonSerializer.Serialize(parsed,AppJsonContext.Default.FeedbackParseResult));
    Console.WriteLine("PHONE PARSER "+parsed.Status);
    return 0;
}

if(!args.Contains("--execute"))
{
    Console.WriteLine("Synthetic demo only, no benchmark access. --execute --backend AutoVulkanCpu|Vulkan|Cpu [--adaptive | --gpu-layers N] [--native-dir DIR] [--model ID] [--model-root DIR] [--context 2048] [--attempts 1..3] [--load-only] [--output FILE]. Adaptive first load includes technical calibration.");
    return 0;
}
string Option(string name,string fallback){int i=Array.IndexOf(args,name);return i>=0&&i+1<args.Length?args[i+1]:fallback;}
var model=PortableCatalog.All.Single(m=>m.Id==Option("--model","09-lfm25-12b-q4-k-m"));
var backend=Enum.Parse<BackendPreference>(Option("--backend","AutoVulkanCpu"),true);
var context=int.Parse(Option("--context","2048"));
var root=Path.GetFullPath(Option("--model-root","../models"));
var folder=Path.GetFullPath(Option("--session-dir","../logs/cross_demo"));
var output=Path.GetFullPath(Option("--output",Path.Combine(folder,$"smoke-{backend}-{DateTime.UtcNow:yyyyMMddTHHmmssfffZ}.json")));
if(File.Exists(output)) throw new IOException("Refusing to overwrite evidence.");
using var cts=new CancellationTokenSource();
Console.CancelKeyPress+=(_,e)=>{e.Cancel=true;cts.Cancel();};
using var store=new ModelStore(Path.Combine(folder,"model-cache"),[root]);
var path=store.FindExisting(model)??throw new FileNotFoundException("No existing model found; this harness never downloads weights.");
Console.WriteLine($"VERIFY {model.Id} {path}");
if(!await store.VerifyAsync(model,path,cts.Token)) throw new InvalidDataException("Model integrity failure.");
if(args.Contains("--unconstrained") && (args.Contains("--adaptive") || args.Contains("--gpu-layers")))
    throw new ArgumentException("Adaptive checks use the production JSON grammar.");
var native=Path.GetFullPath(Option("--native-dir",AppContext.BaseDirectory));
await using IInferenceEngine engine=args.Contains("--adaptive")
    ? new AdaptiveInferenceEngine(_=>new IsolatedInferenceEngine(native,Path.Combine(folder,"workers")),Path.Combine(folder,"profiles"),"synthetic-runtime-check")
    : args.Contains("--gpu-layers") ? new IsolatedInferenceEngine(native,Path.Combine(folder,"workers"))
    : new NativeInferenceEngine(guidedJson:!args.Contains("--unconstrained"));
if(engine is IRuntimeProgress progress)progress.StatusChanged+=Console.WriteLine;
var device=new DeviceProfile(OperatingSystem.IsWindows()?"Windows":"Other",RuntimeInformation.ProcessArchitecture.ToString(),GC.GetGCMemoryInfo().TotalAvailableMemoryBytes,0,new DriveInfo(Path.GetPathRoot(folder)!).AvailableFreeSpace);
var services=new AppServices(device,store,engine,new SessionStore(folder));
Console.WriteLine($"LOAD requested={backend} context={context}");
EngineState state;
if(engine is IPlacementEngine placement)
{
    var inventory=await placement.InspectAsync(path,context,cts.Token);
    var gpu=inventory.Devices.Single(d=>d.Index==int.Parse(Option("--adapter-index","0")));
    var layers=int.Parse(Option("--gpu-layers","1"));
    if(layers<1 || layers>gpu.FullLayers)throw new ArgumentOutOfRangeException("--gpu-layers");
    state=await placement.LoadPlacementAsync(model,path,new(gpu.Index,gpu.Id,layers),context,cts.Token);
}
else state=await engine.LoadAsync(model,path,backend,context,cts.Token);
Console.WriteLine($"BACKEND actual={state.Backend} device={state.Device} offloaded={state.OffloadedLayers} fallback={state.FallbackReason}");
Directory.CreateDirectory(Path.GetDirectoryName(output)!);
if(args.Contains("--load-only"))
{
    await File.WriteAllTextAsync(output,JsonSerializer.Serialize(state,AppJsonContext.Default.EngineState));
}
else
{
    var exercise=ExerciseCatalog.All[0];
    var session=await EvaluationService.EvaluateAsync(services,model,state,exercise,exercise.IncorrectExample,int.Parse(Option("--attempts","1")),null,cts.Token);
    await File.WriteAllTextAsync(output,SessionStore.Serialize(session));
    Console.WriteLine($"RESULT attempts={session.Attempts.Length} usable={session.Usable} parser={session.Attempts[^1].Parsed.Status}");
}
await engine.UnloadAsync();
Console.WriteLine("EVIDENCE "+output);return 0;
