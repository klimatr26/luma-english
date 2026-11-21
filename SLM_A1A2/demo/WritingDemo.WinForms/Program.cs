using WritingDemo.Core;

namespace WritingDemo.WinForms;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        try
        {
            var index = Array.IndexOf(args, "--workspace");
            if (index >= 0 && (index + 1 >= args.Length || string.IsNullOrWhiteSpace(args[index + 1])))
                throw new ArgumentException("Indica la carpeta del proyecto después de --workspace.");
            var paths = DemoPaths.Locate(index >= 0 && index + 1 < args.Length ? args[index + 1] : null);
            Application.Run(new MainForm(paths));
        }
        catch (Exception ex) { MessageBox.Show(ex.Message, "Writing local · Inicio", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
}
