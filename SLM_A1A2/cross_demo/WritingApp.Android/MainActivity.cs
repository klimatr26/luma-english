using Android.App;
using Android.Content.PM;
using Avalonia.Android;

namespace WritingApp.Android;

[Activity(
    Label = "Writing Lab",
    MainLauncher = true,
    Exported = true,
    Theme = "@style/WritingLabTheme.NoActionBar",
    ConfigurationChanges = ConfigChanges.Orientation | ConfigChanges.ScreenSize | ConfigChanges.UiMode)]
public sealed class MainActivity : AvaloniaMainActivity
{
    protected override void OnResume()
    {
        base.OnResume();
        ModelDownloadFinalizer.Schedule(this);
    }
}
