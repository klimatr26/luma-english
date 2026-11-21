using Android.App;
using Android.OS;
using Android.Runtime;
using Avalonia.Android;
using Course.Core;
using Course.UI;
using WritingApp.Shared;
using WritingApp.Android;

namespace Luma.AndroidApp;

#if COURSE_AUTOMATION
[Application(Debuggable = true)]
#else
[Application(Debuggable = false)]
#endif
public sealed class AndroidApplication : AvaloniaAndroidApplication<App>, IModelDownloadHost
{
    public BackgroundModelDownloads Downloads => Platform.Downloads;
    internal AndroidPlatform Platform { get; private set; } = null!;
    internal CourseStore Store { get; private set; } = null!;
    public AndroidApplication(IntPtr reference, JniHandleOwnership transfer) : base(reference, transfer) { }
    public override void OnCreate()
    {
        Platform = new(this);
        Store = new(Path.Combine(FilesDir!.AbsolutePath, "Course", "course.db"));
        App.ViewModel = new(new EmbeddedCourse(), Store, Platform.Runtime);
        base.OnCreate();
    }
}
