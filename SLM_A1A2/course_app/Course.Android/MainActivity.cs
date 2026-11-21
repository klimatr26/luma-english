using Android.App;
using Android.Content.PM;
using Android.Views;
using System.ComponentModel;
using Avalonia.Android;
using Course.UI;
using WritingApp.Android;

namespace Luma.AndroidApp;

[Activity(Name = "org.kevinlima.writinglab.MainActivity", Label = "Luma English", MainLauncher = true,
    Exported = true, Theme = "@style/LumaTheme.NoActionBar",
    WindowSoftInputMode = SoftInput.AdjustResize,
    ConfigurationChanges = ConfigChanges.Orientation | ConfigChanges.ScreenSize | ConfigChanges.UiMode)]
public sealed class MainActivity : AvaloniaMainActivity
{
    internal static WeakReference<MainActivity>? Current { get; private set; }
    private CourseViewModel? _screenVm;
    protected override void OnResume()
    {
        base.OnResume();
        Current = new(this);
        _screenVm = App.ViewModel;
        if (_screenVm is not null) _screenVm.PropertyChanged += ViewModelChanged;
        UpdateScreenPolicy();
#if COURSE_AUTOMATION
        PhoneVerificationActivity.MainResumed(this);
#endif
        ModelDownloadFinalizer.Schedule(this);
    }
    protected override void OnPause()
    {
        if (_screenVm is not null) _screenVm.PropertyChanged -= ViewModelChanged;
        _screenVm = null; Window?.ClearFlags(WindowManagerFlags.KeepScreenOn);
#if COURSE_AUTOMATION
        PhoneVerificationActivity.MainPaused();
#endif
        // Persist drafts without cancelling DownloadManager jobs or a rotation/file picker.
        if (App.ViewModel is { } vm) _ = SaveDraftsAsync(vm);
        base.OnPause();
    }
    private void ViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(CourseViewModel.KeepsDisplayAwake)) RunOnUiThread(UpdateScreenPolicy);
    }
    private void UpdateScreenPolicy()
    {
        var keep = _screenVm?.KeepsDisplayAwake == true;
#if COURSE_AUTOMATION
        keep |= PhoneVerificationActivity.KeepScreenAwake;
#endif
        if (keep) Window?.AddFlags(WindowManagerFlags.KeepScreenOn);
        else Window?.ClearFlags(WindowManagerFlags.KeepScreenOn);
    }
    private static async Task SaveDraftsAsync(CourseViewModel vm)
    {
        try { await vm.FlushDraftsAsync(); }
        catch (Exception e) { global::Android.Util.Log.Warn("LumaCourse", e.Message); }
    }
}
