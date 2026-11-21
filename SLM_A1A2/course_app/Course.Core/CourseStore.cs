using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;
using WritingApp.Shared;

namespace Course.Core;

public sealed record CourseSettings(string? ModelId = null, bool AutomaticModel = true,
    BackendPreference Backend = BackendPreference.AutoVulkanCpu, int Context = 2048, int MaximumAttempts = 1,
    string? AdapterId = null, int? GpuLayers = null)
{
    public CourseSettings Validated() => Context is not (2048 or 4096) || MaximumAttempts is < 1 or > 3 || GpuLayers < 0 ||
        !Enum.IsDefined(Backend) || GpuLayers is not null && (Backend != BackendPreference.Vulkan || string.IsNullOrWhiteSpace(AdapterId))
        ? throw new InvalidDataException("Configuración incompatible.") : this;
}
public sealed record HistoryEntry(string Id, string ActivityId, string Kind, DateTimeOffset DateUtc,
    string Status, bool? IsCorrect, string StudentText, string Detail, string? SessionJson);
public sealed record ProgressSnapshot(HashSet<string> Practiced, Dictionary<string, string> Drafts,
    int ClosedPracticed, int ClosedCorrect, HistoryEntry[] History);
public sealed record BackupManifest(int Version, int DatabaseSchema, string CourseId, string CourseVersion,
    DateTimeOffset CreatedUtc, string Sha256);

public interface IProgressStore
{
    Task<ProgressSnapshot> SnapshotAsync();
    Task SaveDraftAsync(string activityId, string text);
    Task SaveClosedAsync(CourseActivity activity, string answer, ClosedResult result);
}

/// <summary>One writer, short-lived connections, synchronous SQLite work on a worker thread.</summary>
public sealed class CourseStore : IProgressStore, IDisposable
{
    private readonly ConcurrentExclusiveSchedulerPair _queue = new(TaskScheduler.Default, maxConcurrencyLevel: 1);
    private bool _initialized;
    public string DatabasePath { get; }
    public CourseStore(string path)
    {
        DatabasePath = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(DatabasePath)!);
    }
    private Task<T> Run<T>(Func<SqliteConnection, T> work) => Task.Factory.StartNew(() =>
    {
        using var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = DatabasePath, Pooling = false }.ToString());
        connection.Open();
        Execute(connection, "PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;");
        if (!_initialized) Initialize(connection);
        return work(connection);
    }, CancellationToken.None, TaskCreationOptions.DenyChildAttach, _queue.ExclusiveScheduler);
    private void Initialize(SqliteConnection db)
    {
        var version = Convert.ToInt32(Scalar(db, "PRAGMA user_version;"));
        if (version > 1) throw new InvalidDataException("Esta base de datos necesita una versión más reciente de la aplicación.");
        Execute(db, "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;");
        if (version == 0)
        {
            using var tx = db.BeginTransaction();
            Execute(db, """
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE drafts(activity_id TEXT PRIMARY KEY,text TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE closed_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,activity_id TEXT NOT NULL,answer TEXT NOT NULL,correct INTEGER NOT NULL,occurred TEXT NOT NULL);
                CREATE TABLE writing_sessions(id TEXT PRIMARY KEY,activity_id TEXT NOT NULL,is_lab INTEGER NOT NULL,started TEXT NOT NULL,status TEXT NOT NULL,student_text TEXT NOT NULL,detail TEXT NOT NULL,session_json TEXT);
                CREATE TABLE writing_attempts(session_id TEXT NOT NULL REFERENCES writing_sessions(id),number INTEGER NOT NULL,seed INTEGER NOT NULL,raw TEXT NOT NULL,finish TEXT NOT NULL,seconds REAL NOT NULL,parsed_status TEXT,PRIMARY KEY(session_id,number));
                PRAGMA user_version=1;
                """, tx);
            tx.Commit();
        }
        Execute(db, "UPDATE writing_sessions SET status='interrupted', detail='La aplicación se cerró antes de completar esta evaluación; se conservan las salidas recibidas.' WHERE status='running';");
        _initialized = true;
    }
    private static SqliteCommand Command(SqliteConnection db, string sql, SqliteTransaction? tx = null, params (string, object?)[] values)
    {
        var command = db.CreateCommand(); command.CommandText = sql; command.Transaction = tx;
        foreach (var (name, value) in values) command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        return command;
    }
    private static void Execute(SqliteConnection db, string sql, SqliteTransaction? tx = null, params (string, object?)[] values)
    { using var command = Command(db, sql, tx, values); command.ExecuteNonQuery(); }
    private static object? Scalar(SqliteConnection db, string sql)
    { using var command = Command(db, sql); return command.ExecuteScalar(); }
    public Task SaveDraftAsync(string activityId, string text) => Run(db =>
    {
        Execute(db, "INSERT INTO drafts VALUES($id,$text,$date) ON CONFLICT(activity_id) DO UPDATE SET text=$text,updated=$date;", null,
            ("$id", activityId), ("$text", text), ("$date", DateTimeOffset.UtcNow.ToString("O"))); return 0;
    });
    public Task SaveClosedAsync(CourseActivity activity, string answer, ClosedResult result) => Run(db =>
    {
        using var tx = db.BeginTransaction();
        Execute(db, "INSERT INTO closed_attempts(activity_id,answer,correct,occurred) VALUES($id,$answer,$correct,$date);", tx,
            ("$id", activity.Id), ("$answer", answer.Trim()), ("$correct", result.Correct ? 1 : 0), ("$date", DateTimeOffset.UtcNow.ToString("O")));
        tx.Commit(); return 0;
    });
    public Task<CourseSettings> SettingsAsync() => Run(db =>
    {
        using var command = Command(db, "SELECT value FROM settings WHERE key='preferences';");
        var value = command.ExecuteScalar() as string;
        return value is null ? new CourseSettings() : (JsonSerializer.Deserialize(value, CourseJsonContext.Default.CourseSettings)
            ?? new CourseSettings()).Validated();
    });
    public Task SaveSettingsAsync(CourseSettings settings) => Run(db =>
    {
        var value = JsonSerializer.Serialize(settings.Validated(), CourseJsonContext.Default.CourseSettings);
        Execute(db, "INSERT INTO settings VALUES('preferences',$value) ON CONFLICT(key) DO UPDATE SET value=$value;", null, ("$value", value)); return 0;
    });
    public Task StartWritingAsync(string id, string activityId, bool laboratory, string text) => Run(db =>
    {
        Execute(db, "INSERT INTO writing_sessions VALUES($id,$activity,$lab,$date,'running',$text,'Evaluación iniciada.',NULL);", null,
            ("$id", id), ("$activity", activityId), ("$lab", laboratory ? 1 : 0), ("$date", DateTimeOffset.UtcNow.ToString("O")), ("$text", text)); return 0;
    });
    public Task AppendRawAsync(string id, int number, int seed, EngineOutput output) => Run(db =>
    {
        Execute(db, "INSERT INTO writing_attempts VALUES($id,$number,$seed,$raw,$finish,$seconds,NULL);", null,
            ("$id", id), ("$number", number), ("$seed", seed), ("$raw", output.Content), ("$finish", output.FinishReason), ("$seconds", output.Seconds)); return 0;
    });
    public Task UpdateAttemptAsync(string id, int number, string status) => Run(db =>
    { Execute(db, "UPDATE writing_attempts SET parsed_status=$status WHERE session_id=$id AND number=$number;", null, ("$status", status), ("$id", id), ("$number", number)); return 0; });
    public Task FinishWritingAsync(string id, string status, string detail, ReviewSession? session) => Run(db =>
    {
        Execute(db, "UPDATE writing_sessions SET status=$status,detail=$detail,session_json=COALESCE($json,session_json) WHERE id=$id;", null,
            ("$status", status), ("$detail", detail), ("$json", session is null ? null : SessionStore.Serialize(session)), ("$id", id)); return 0;
    });
    public Task<ProgressSnapshot> SnapshotAsync() => Run(db =>
    {
        var practiced = new HashSet<string>(StringComparer.Ordinal);
        var drafts = new Dictionary<string, string>(StringComparer.Ordinal);
        int closedCount = 0, correct = 0;
        using (var command = Command(db, "SELECT a.activity_id,a.correct FROM closed_attempts a JOIN (SELECT activity_id,MAX(id) id FROM closed_attempts GROUP BY activity_id) latest ON a.id=latest.id;"))
        using (var reader = command.ExecuteReader()) while (reader.Read()) { practiced.Add(reader.GetString(0)); closedCount++; correct += reader.GetInt32(1); }
        using (var command = Command(db, "SELECT DISTINCT activity_id FROM writing_sessions WHERE is_lab=0 AND status='usable';"))
        using (var reader = command.ExecuteReader()) while (reader.Read()) practiced.Add(reader.GetString(0));
        using (var command = Command(db, "SELECT activity_id,text FROM drafts;"))
        using (var reader = command.ExecuteReader()) while (reader.Read()) drafts[reader.GetString(0)] = reader.GetString(1);
        return new ProgressSnapshot(practiced, drafts, closedCount, correct, History(db));
    });
    private static HistoryEntry[] History(SqliteConnection db)
    {
        var history = new List<HistoryEntry>();
        using (var command = Command(db, "SELECT id,activity_id,answer,correct,occurred FROM closed_attempts ORDER BY id DESC;"))
        using (var reader = command.ExecuteReader()) while (reader.Read())
            history.Add(new(reader.GetInt64(0).ToString(), reader.GetString(1), "closed", DateTimeOffset.Parse(reader.GetString(4)), "checked", reader.GetInt32(3) != 0, reader.GetString(2), "Respuesta cerrada comprobada con la clave del curso.", null));
        using (var command = Command(db, "SELECT id,activity_id,is_lab,started,status,student_text,detail,session_json FROM writing_sessions ORDER BY started DESC;"))
        using (var reader = command.ExecuteReader()) while (reader.Read())
        {
            var json = reader.IsDBNull(7) ? null : reader.GetString(7);
            var session = json is null ? null : JsonSerializer.Deserialize(json, AppJsonContext.Default.ReviewSession);
            history.Add(new(reader.GetString(0), reader.GetString(1), reader.GetInt32(2) == 1 ? "laboratory" : "writing", DateTimeOffset.Parse(reader.GetString(3)),
                reader.GetString(4), session?.Usable == true ? session.Attempts.Last().Parsed.Value?.IsCorrect : null, reader.GetString(5), reader.GetString(6), json));
        }
        return history.OrderByDescending(h => h.DateUtc).ToArray();
    }
    public async Task ExportHistoryAsync(Stream target)
    {
        // Includes interrupted attempts even when no complete ReviewSession was produced.
        var json = await Run(db =>
        {
            using var memory = new MemoryStream(); using (var writer = new Utf8JsonWriter(memory, new() { Indented = true }))
            {
                writer.WriteStartObject(); writer.WriteString("schema", "writing_course_history/1"); writer.WriteString("purpose", "COURSE_PRACTICE_NOT_BENCHMARK");
                writer.WriteString("exportedUtc", DateTimeOffset.UtcNow); writer.WritePropertyName("history");
                JsonSerializer.Serialize(writer, History(db), CourseJsonContext.Default.HistoryEntryArray);
                writer.WritePropertyName("rawAttempts"); writer.WriteStartArray();
                using var command = Command(db, "SELECT session_id,number,seed,raw,finish,seconds,parsed_status FROM writing_attempts ORDER BY session_id,number;");
                using var reader = command.ExecuteReader(); while (reader.Read())
                {
                    writer.WriteStartObject(); writer.WriteString("sessionId", reader.GetString(0)); writer.WriteNumber("number", reader.GetInt32(1));
                    writer.WriteNumber("seed", reader.GetInt32(2)); writer.WriteString("raw", reader.GetString(3)); writer.WriteString("finish", reader.GetString(4));
                    writer.WriteNumber("seconds", reader.GetDouble(5)); writer.WriteString("parseStatus", reader.IsDBNull(6) ? "not_parsed" : reader.GetString(6)); writer.WriteEndObject();
                }
                writer.WriteEndArray(); writer.WriteEndObject();
            }
            return memory.ToArray();
        }).ConfigureAwait(false);
        await target.WriteAsync(json).ConfigureAwait(false);
    }
    public async Task ExportCsvAsync(Stream target)
    {
        var snapshot = await SnapshotAsync().ConfigureAwait(false);
        static string Cell(string text) => "\"" + (text.StartsWith('=') || text.StartsWith('+') || text.StartsWith('-') || text.StartsWith('@') ? "'" : "") + text.Replace("\"", "\"\"") + "\"";
        var csv = new StringBuilder("id,activity_id,kind,date_utc,status,is_correct,student_text\r\n");
        foreach (var h in snapshot.History) csv.AppendLine(string.Join(',', new[] { h.Id, h.ActivityId, h.Kind, h.DateUtc.ToString("O"), h.Status, h.IsCorrect?.ToString() ?? "", h.StudentText }.Select(Cell)));
        await target.WriteAsync(new UTF8Encoding(true).GetBytes(csv.ToString())).ConfigureAwait(false);
    }
    public async Task BackupAsync(Stream target)
    {
        var temporary = Path.Combine(Path.GetTempPath(), "writing-course-" + Guid.NewGuid().ToString("N") + ".db");
        try
        {
            await Run(db => { using var backup = new SqliteConnection($"Data Source={temporary};Pooling=False"); backup.Open(); db.BackupDatabase(backup); return 0; }).ConfigureAwait(false);
            var bytes = await File.ReadAllBytesAsync(temporary).ConfigureAwait(false);
            var manifest = new BackupManifest(1, 1, "writing-local-a1", "1.0.0", DateTimeOffset.UtcNow, Convert.ToHexStringLower(SHA256.HashData(bytes)));
            using var zip = new ZipArchive(target, ZipArchiveMode.Create, leaveOpen: true);
            await using (var entry = zip.CreateEntry("manifest.json").Open()) await JsonSerializer.SerializeAsync(entry, manifest, CourseJsonContext.Default.BackupManifest).ConfigureAwait(false);
            await using (var entry = zip.CreateEntry("course.db").Open()) await entry.WriteAsync(bytes).ConfigureAwait(false);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    public async Task<string> RestoreAsync(Stream source)
    {
        var temporary = Path.Combine(Path.GetTempPath(), "writing-course-restore-" + Guid.NewGuid().ToString("N") + ".db");
        try
        {
            using (var zip = new ZipArchive(source, ZipArchiveMode.Read, leaveOpen: true))
            {
                if (zip.Entries.Count != 2 || zip.GetEntry("manifest.json") is not { Length: <= 32768 } metadata || zip.GetEntry("course.db") is not { Length: > 0 and <= 268435456 } database)
                    throw new InvalidDataException("Respaldo inválido o demasiado grande.");
                await using var manifestStream = metadata.Open();
                var manifest = await JsonSerializer.DeserializeAsync(manifestStream, CourseJsonContext.Default.BackupManifest).ConfigureAwait(false);
                if (manifest is not { Version: 1, DatabaseSchema: 1, CourseId: "writing-local-a1", CourseVersion: "1.0.0" }) throw new InvalidDataException("Versión de respaldo incompatible.");
                await using (var file = File.Create(temporary)) await database.Open().CopyToAsync(file).ConfigureAwait(false);
                await using var check = File.OpenRead(temporary);
                if (Convert.ToHexStringLower(await SHA256.HashDataAsync(check).ConfigureAwait(false)) != manifest.Sha256) throw new InvalidDataException("El respaldo no coincide con su SHA-256.");
            }
            return await Run(db =>
            {
                using var restored = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = temporary, Mode = SqliteOpenMode.ReadOnly, Pooling = false }.ToString()); restored.Open();
                if ((string?)Scalar(restored, "PRAGMA integrity_check;") != "ok" || Convert.ToInt32(Scalar(restored, "PRAGMA user_version;")) != 1) throw new InvalidDataException("Base de datos de respaldo inválida.");
                // Validate required application tables/settings before replacing the live database.
                _ = History(restored);
                using (var statement = Command(restored, "SELECT session_id,number,seed,raw,finish,seconds,parsed_status FROM writing_attempts LIMIT 0;")) using (var rows = statement.ExecuteReader()) { }
                using (var statement = Command(restored, "SELECT value FROM settings WHERE key='preferences';"))
                    if (statement.ExecuteScalar() is string preferences)
                        _ = (JsonSerializer.Deserialize(preferences, CourseJsonContext.Default.CourseSettings) ?? throw new InvalidDataException("Preferencias vacías en el respaldo.")).Validated();
                using (var statement = Command(restored, "SELECT activity_id,text FROM drafts; SELECT key,value FROM settings;")) using (var rows = statement.ExecuteReader()) { while (rows.Read()) { } while (rows.NextResult()) while (rows.Read()) { } }
                var previous = DatabasePath + ".before-restore-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmss") + "-" + Guid.NewGuid().ToString("N") + ".db";
                using (var old = new SqliteConnection($"Data Source={previous};Pooling=False")) { old.Open(); db.BackupDatabase(old); }
                restored.BackupDatabase(db); _initialized = false; return previous;
            }).ConfigureAwait(false);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    public void Dispose() => _queue.Complete();
}
