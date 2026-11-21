using Avalonia.Controls;
using WritingApp.Shared;

namespace WritingApp.UI;

public partial class MainWindow : Window
{
    public MainWindow() : this(App.ConfiguredServices) { }

    public MainWindow(AppServices services)
    {
        InitializeComponent();
        RootContent.Content = new MainView(services);
        Closed += OnClosed;
    }

    private async void OnClosed(object? sender, EventArgs e)
    {
        if (RootContent.Content is MainView view)
            await view.DisposeServicesAsync();
    }
}
