using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WritingApp.Shared;
using WritingDemo.Core;

const string Valid="{\"is_correct\":true,\"corrected_text\":\"I wake up at seven. I eat breakfast at home.\",\"errors\":[],\"feedback\":\"\"}";
var tests=new (string,Func<Task>)[]
{
    ("portable catalog preserves separate local and downloadable identities",Catalog),
    ("measured backend requires usable output and a material speedup",Calibration),
    ("memory recommendation is conservative and permits an explicit override",Recommendation),
    ("model cache rejects traversal and absolute Windows paths",Paths),
    ("download verifies SHA and reuses the cache without a second request",Download),
    ("hash mismatch removes only the partial and never publishes it",BadHash),
    ("existing wrong file is preserved and never replaced",ExistingWrong),
    ("valid external copy is usable despite corrupt private cache",ExternalRecovery),
    ("verified explicit import archives corrupt cache without deleting it",ImportRecovery),
    ("cancelled import removes its own partial",CancelledDownload),
    ("HTTP 429 does not retry",RateLimit),
    ("first usable JSON stops without quality-driven retries",FirstUsable),
    ("unusable format retries with traced seeds and preserved attempts",Retries),
    ("all unusable attempts finish visibly at the fixed limit",RetryLimit),
    ("technical generation failure never retries",TechnicalFailure),
    ("source-generated session serialization works with reflection disabled",Serialization)
}.Concat(DownloadRegression.Cases).Concat(AdaptiveRuntimeTests.Cases).ToArray();
int failures=0;
foreach(var (name,run) in tests)
{
    try{await run();Console.WriteLine("PASS "+name);}
    catch(Exception e){failures++;Console.WriteLine("FAIL "+name+": "+e);}
}
Console.WriteLine($"{tests.Length-failures}/{tests.Length} checks passed.");return failures==0?0:1;

static void Assert(bool value,string reason){if(!value)throw new Exception(reason);}
static Task Calibration()
{
    var cpu = Enumerable.Range(0,3).Select(_ => new BackendTrial("CPU",10,80,"stop","STRICT",null)).ToArray();
    var fast = cpu.Select(t => t with { Backend="Vulkan", Seconds=8 }).ToArray();
    Assert(BackendCalibrationPolicy.Decide(cpu,fast).UseVulkan,"complete fast backend");
    Assert(!BackendCalibrationPolicy.Decide(cpu,fast.Select(t=>t with{Seconds=9.5}).ToArray()).UseVulkan,"small speedup");
    Assert(!BackendCalibrationPolicy.Decide(cpu,fast.Take(2).ToArray()).UseVulkan,"incomplete comparison");
    Assert(!BackendCalibrationPolicy.Decide(cpu,fast.Select(t=>t with{ParserStatus="INCONSISTENT"}).ToArray()).UseVulkan,"inconsistent output");
    Assert(!BackendCalibrationPolicy.Decide(cpu,fast.Select(t=>t with{FinishReason="length"}).ToArray()).UseVulkan,"exhausted budget");
    Assert(!BackendCalibrationPolicy.Decide(cpu,fast.Select(t=>t with{Seconds=double.NaN}).ToArray()).UseVulkan,"invalid timing");
    Assert(!BackendCalibrationPolicy.Decide(cpu,fast.Select(t=>t with{Failure="timeout"}).ToArray()).UseVulkan,"failed generation");
    return Task.CompletedTask;
}
static Task Catalog()
{
    var models=PortableCatalog.All;Assert(models.Count==15,"catalog count");
    Assert(models.Single(m=>m.Id=="11-qwen35-4b-q4-k-m").DownloadUrl is null,"local Qwen requires exact import");
    Assert(models.Count(m=>m.Id.StartsWith("portable-"))==2,"downloadable Qwen must have separate ids");
    Assert(models.All(m=>m.DownloadUrl is null||!m.DownloadUrl.Contains("/main/")),"all downloads revision-pinned");
    Assert(PortablePrompt.For(models.Single(m=>m.Id.StartsWith("09-"))).Length>100,"LFM baseline resource");
    Assert(PortablePrompt.For(models.Single(m=>m.Id.StartsWith("06-"))).Contains("Optional writing suggestion"),"review appendix");
    return Task.CompletedTask;
}
static Task Recommendation()
{
    var device=new DeviceProfile("Android","arm64",4L<<30,2L<<30,8L<<30);
    var rec=ModelRecommender.Recommend(PortableCatalog.All,device);
    Assert(rec.ModelId=="09-lfm25-12b-q4-k-m","small model for constrained memory");
    var roomy=ModelRecommender.Recommend(PortableCatalog.All,device with{TotalMemoryBytes=16L<<30,AvailableMemoryBytes=12L<<30});
    Assert(roomy.ModelId=="13-gemma4-e2b-ud-q4-k-xl","prefer Gemma when its memory estimate fits");
    var noRoom=ModelRecommender.Recommend(PortableCatalog.All,device with{AvailableMemoryBytes=100,FreeStorageBytes=100});
    Assert(!noRoom.FitsEstimate,"must not claim a safe fit");
    Assert(PortableCatalog.All.Any(m=>m.Id=="15-lfm25-26b-q8-0"),"override remains in catalog");return Task.CompletedTask;
}
static Task Paths()
{
    foreach(var path in new[]{"../x","C:/x","/tmp/x","a/../x","a\\..\\x","a//x"})
    {
        try{ModelStore.SafePath(Path.GetTempPath(),path);throw new Exception("Accepted unsafe path "+path);}
        catch(ArgumentException){}
    }
    return Task.CompletedTask;
}
static byte[] Bytes()=>Encoding.UTF8.GetBytes("GGUF synthetic fixture, not an actual model");
static ModelEntry Fixture()=>PortableCatalog.All[0] with{Id="fixture",RelativePath="fixture/test.gguf",SizeBytes=Bytes().Length,Sha256=Convert.ToHexStringLower(SHA256.HashData(Bytes())),DownloadUrl="https://huggingface.co/fixture/resolve/pin/test.gguf"};
static async Task Download()
{
    using var temp=new Temp();var handler=new FakeHttp(_=>new(HttpStatusCode.OK){Content=new ByteArrayContent(Bytes())});
    using var store=new ModelStore(temp.Path,handler:handler);var m=Fixture();
    var p=await store.EnsureAsync(m,null,CancellationToken.None);Assert(await store.VerifyAsync(m,p,CancellationToken.None),"verified download");
    Assert(await store.EnsureAsync(m,null,CancellationToken.None)==p && handler.Calls==1,"cache reuse");
}
static async Task BadHash()
{
    using var temp=new Temp();using var store=new ModelStore(temp.Path,handler:new FakeHttp(_=>new(HttpStatusCode.OK){Content=new ByteArrayContent(Bytes())}));
    try{await store.EnsureAsync(Fixture() with{Sha256=new string('0',64)},null,CancellationToken.None);throw new Exception("accepted mismatch");}catch(InvalidDataException){}
    Assert(!Directory.EnumerateFiles(temp.Path,"*",SearchOption.AllDirectories).Any(),"partial cleanup");
}
static async Task ExistingWrong()
{
    using var temp=new Temp();var m=Fixture();var p=ModelStore.SafePath(temp.Path,m.RelativePath);Directory.CreateDirectory(System.IO.Path.GetDirectoryName(p)!);await File.WriteAllTextAsync(p,"keep");
    var handler=new FakeHttp(_=>throw new Exception("must not fetch"));using var store=new ModelStore(temp.Path,handler:handler);
    try{await store.EnsureAsync(m,null,CancellationToken.None);throw new Exception("accepted wrong file");}catch(InvalidDataException){}
    Assert(await File.ReadAllTextAsync(p)=="keep" && handler.Calls==0,"original preserved");
}
static async Task CancelledDownload()
{
    using var temp=new Temp();using var cts=new CancellationTokenSource();using var store=new ModelStore(temp.Path);
    using var input=new CancelStream(Bytes(),cts);
    try{await store.ImportAsync(Fixture(),input,null,cts.Token);throw new Exception("accepted cancel");}catch(OperationCanceledException){}
    Assert(!Directory.EnumerateFiles(temp.Path,"*",SearchOption.AllDirectories).Any(),"cancel partial cleanup");
}
static async Task ExternalRecovery()
{
    using var cache=new Temp();using var external=new Temp();var m=Fixture();
    var bad=ModelStore.SafePath(cache.Path,m.RelativePath);Directory.CreateDirectory(System.IO.Path.GetDirectoryName(bad)!);await File.WriteAllTextAsync(bad,"preserve corrupt");
    var good=ModelStore.SafePath(external.Path,m.RelativePath);Directory.CreateDirectory(System.IO.Path.GetDirectoryName(good)!);await File.WriteAllBytesAsync(good,Bytes());
    using var store=new ModelStore(cache.Path,[external.Path],new FakeHttp(_=>throw new Exception("must not fetch")));
    Assert(await store.EnsureAsync(m,null,CancellationToken.None)==good,"external resolution");
    Assert(await File.ReadAllTextAsync(bad)=="preserve corrupt","corrupt copy preserved");
}
static async Task ImportRecovery()
{
    using var temp=new Temp();var m=Fixture();var p=ModelStore.SafePath(temp.Path,m.RelativePath);Directory.CreateDirectory(System.IO.Path.GetDirectoryName(p)!);await File.WriteAllTextAsync(p,"preserve corrupt");
    using var store=new ModelStore(temp.Path);using var stream=new MemoryStream(Bytes());
    Assert(await store.ImportAsync(m,stream,null,CancellationToken.None)==p,"import destination");
    Assert(await store.VerifyAsync(m,p,CancellationToken.None),"new import verified");
    var archive=Directory.GetFiles(System.IO.Path.GetDirectoryName(p)!,"*.unverified-*").Single();
    Assert(await File.ReadAllTextAsync(archive)=="preserve corrupt","original bytes archived");
}
static async Task RateLimit()
{
    using var temp=new Temp();var handler=new FakeHttp(_=>new(HttpStatusCode.TooManyRequests));using var store=new ModelStore(temp.Path,handler:handler);
    try{await store.EnsureAsync(Fixture(),null,CancellationToken.None);throw new Exception("accepted 429");}catch(HttpRequestException e){Assert(e.StatusCode==HttpStatusCode.TooManyRequests,"status");}
    Assert(handler.Calls==1,"no retry");
}
static async Task<ReviewSession> Run(FakeEngine engine,int max,Temp temp)
{
    var services=new AppServices(new("Android","arm64",8L<<30,4L<<30,8L<<30),new ModelStore(temp.Path),engine,new SessionStore(System.IO.Path.Combine(temp.Path,"sessions")));
    return await EvaluationService.EvaluateAsync(services,PortableCatalog.All[0],new(BackendPreference.Cpu,"CPU",null,0,null,2048),ExerciseCatalog.All[0],ExerciseCatalog.All[0].CorrectExample,max,null,CancellationToken.None);
}
static async Task FirstUsable()
{
    using var temp=new Temp();var engine=new FakeEngine([Valid,"bad"]);var session=await Run(engine,3,temp);
    Assert(session.Usable && session.Attempts.Length==1 && engine.Calls==1,"usable stop");
}
static async Task Retries()
{
    using var temp=new Temp();var engine=new FakeEngine(["broken",Valid]);var session=await Run(engine,3,temp);
    Assert(session.Usable && session.Attempts.Length==2 && engine.Seeds.SequenceEqual(new[]{42,43}),"trace attempts");
    Assert(session.Attempts[0].Output.Content=="broken","original raw retained");
    Assert(Directory.GetFiles(System.IO.Path.Combine(temp.Path,"sessions")).Length==2,"checkpoint every returned attempt");
}
static async Task RetryLimit()
{
    using var temp=new Temp();var engine=new FakeEngine(["x","y","z"]);var session=await Run(engine,3,temp);
    Assert(!session.Usable && session.Attempts.Length==3 && engine.Calls==3,"bounded retries");
}
static async Task TechnicalFailure()
{
    using var temp=new Temp();var engine=new FakeEngine([]){Throw=true};
    try{await Run(engine,3,temp);throw new Exception("accepted failure");}catch(IOException){}
    Assert(engine.Calls==1,"technical no retry");
}
static async Task Serialization()
{
    using var temp=new Temp();var session=await Run(new FakeEngine([Valid]),1,temp);var serialized=SessionStore.Serialize(session);
    using var j=JsonDocument.Parse(serialized);Assert(j.RootElement.GetProperty("Purpose").GetString()=="INTERACTIVE_DEMO_NOT_BENCHMARK","purpose");
    Assert(!JsonSerializer.IsReflectionEnabledByDefault,"reflection serialization must remain disabled");
}
sealed class FakeHttp(Func<HttpRequestMessage,HttpResponseMessage> send):HttpMessageHandler
{
    public int Calls;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct){ct.ThrowIfCancellationRequested();Calls++;return Task.FromResult(send(request));}
}
sealed class FakeEngine(string[] outputs):IInferenceEngine
{
    public int Calls;public bool Throw;public List<int> Seeds=[];
    public Task<EngineState> LoadAsync(ModelEntry m,string p,BackendPreference b,int c,CancellationToken ct)=>Task.FromResult(new EngineState(b,"CPU",null,0,null,c));
    public Task<EngineOutput> GenerateAsync(WritingExercise e,string s,int seed,CancellationToken ct)
    {Calls++;Seeds.Add(seed);if(Throw)throw new IOException("technical");return Task.FromResult(new EngineOutput(outputs[Calls-1],"stop",0.1));}
    public Task UnloadAsync()=>Task.CompletedTask;public ValueTask DisposeAsync()=>ValueTask.CompletedTask;
}
sealed class CancelStream(byte[] bytes,CancellationTokenSource cts):MemoryStream(bytes)
{
    public override ValueTask<int> ReadAsync(Memory<byte> buffer,CancellationToken ct=default){cts.Cancel();ct.ThrowIfCancellationRequested();return base.ReadAsync(buffer,ct);}
}
sealed class Temp:IDisposable
{
    public string Path{get;}=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"writing-cross-tests-"+Guid.NewGuid().ToString("N"));
    public Temp()=>Directory.CreateDirectory(Path);
    public void Dispose(){var full=System.IO.Path.GetFullPath(Path);if(!full.StartsWith(System.IO.Path.GetTempPath(),StringComparison.OrdinalIgnoreCase))throw new Exception("Unsafe fixture cleanup");Directory.Delete(full,true);}
}
