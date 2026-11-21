namespace WritingApp.Shared;

public static class ModelRecommender
{
    private const long MiB=1024*1024;
    public static long Estimate(ModelEntry model,int context=2048) => checked((long)(model.SizeBytes*1.45)+384*MiB+(long)context*64*1024);
    public static ModelRecommendation Recommend(IReadOnlyList<ModelEntry> models,DeviceProfile device)
    {
        if(models.Count==0) throw new ArgumentException("Empty model catalog.");
        var available=device.AvailableMemoryBytes>0 ? device.AvailableMemoryBytes : device.TotalMemoryBytes/3;
        var budget=Math.Min(available*3/4,device.TotalMemoryBytes*45/100);
        var context=device.Platform=="Android"?2048:4096;
        // Resource fallback order; Qwen remains a manual quality-oriented choice,
        // whose actual CPU/GPU placement is measured once its weights are available.
        string[] preferred = ["13-gemma4-e2b-ud-q4-k-xl", "06-minicpm5-2b-q4-k-m", "09-lfm25-12b-q4-k-m"];
        ModelEntry? selected=null;
        foreach(var id in preferred)
        {
            var candidate=models.FirstOrDefault(m=>m.Id==id && m.DownloadUrl is not null);
            if(candidate is not null && Estimate(candidate,context)<=budget && (device.FreeStorageBytes<=0 || candidate.SizeBytes+256*MiB<device.FreeStorageBytes))
            {selected=candidate;break;}
        }
        selected??=models.OrderBy(m=>m.SizeBytes).First();
        var estimate=Estimate(selected,context);
        var fits=estimate<=budget && (device.FreeStorageBytes<=0 || selected.SizeBytes+256*MiB<device.FreeStorageBytes);
        var reason=$"Estimación inicial: {estimate/1e9:F2} GB de RAM para {context} tokens; presupuesto conservador {budget/1e9:F2} GB. RAM libre y compatibilidad pueden cambiar. No es una clasificación de calidad; puedes elegir otro modelo.";
        reason="Se propone Gemma si hay memoria, después MiniCPM y LFM1.2. Qwen está disponible por elección manual; Auto mide CPU y Vulkan con los pesos locales. "+reason;
        if(!fits) reason="Ningún candidato preferido cabe en la estimación conservadora. No se garantiza una carga exitosa. "+reason;
        return new(selected.Id,estimate,fits,reason);
    }
}
