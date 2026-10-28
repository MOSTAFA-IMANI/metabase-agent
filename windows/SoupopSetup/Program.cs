// Soupop Data Setup for Windows.
//
// Does what the start page (docs/index.html) can only describe: gets the project
// folder, checks Metabase, finds the Codex app, checks and installs Node.js and
// Python, saves and tests the Metabase sign-in, then opens Codex and the start page.
//
//   SoupopSetup.exe                   interactive setup
//   SoupopSetup.exe --check           checks only: no questions, downloads or installs
//   SoupopSetup.exe --folder <path>   use this project folder

using System.ComponentModel;
using System.Diagnostics;
using System.IO.Compression;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace SoupopSetup;

static class Program
{
    const string Repo = "MOSTAFA-IMANI/metabase-agent";
    const string Branch = "main";
    const string CodexDownload = "https://openai.com/codex/";
    const string PythonInstaller = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe";
    const int MinNodeMajor = 18;

    // Files and folders an update never overwrites: the person's own settings and outputs.
    static readonly string[] Keep = { ".env", "soupop-metabase.env", ".workspace-state.json", ".soupop-version", "data", "reports", "sql/snapshot" };
    static readonly string[] EnvKeys = { "METABASE_URL", "METABASE_API_KEY", "METABASE_USERNAME", "METABASE_PASSWORD", "METABASE_SESSION_ID" };

    static bool CheckOnly;
    static readonly HttpClient Http = NewClient(TimeSpan.FromSeconds(20));
    static readonly HttpClient Download = NewClient(TimeSpan.FromMinutes(15));
    static readonly List<(string Step, bool? Ok, string Note)> Summary = new();

    static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        CheckOnly = args.Contains("--check");
        var folderArg = ArgValue(args, "--folder");

        Title("Soupop Data Setup");
        Console.WriteLine(CheckOnly
            ? "Checking this computer (no changes will be made)."
            : "This sets up your computer to ask Codex about Soupop data. Answer the questions; press Enter to accept the suggestion in [brackets].");

        var folder = await Step("1. Project folder", () => ProjectFolder(folderArg));
        var config = LoadConfig(folder);
        var baseUrl = (config?["metabase_url"]?.GetValue<string>() ?? "https://mt.soupop.ir").TrimEnd('/');

        await Step("2. Reach Metabase (VPN)", () => CheckMetabase(baseUrl));
        var codex = await Step("3. Codex app", FindOrInstallCodex);
        await Step("4. Node.js", CheckNode);
        await Step("5. Python", CheckPython);
        if (folder != null)
            await Step("6. Connect to Metabase", () => Connect(folder, baseUrl, config));
        if (folder != null && !CheckOnly)
            await Step("7. Open Codex", () => OpenCodex(folder, codex));

        Title("Summary");
        foreach (var (step, ok, note) in Summary)
            Line(ok, $"{step}: {note}");

        if (CheckOnly)
            return Summary.Any(s => s.Ok == false) ? 1 : 0;

        if (folder != null)
        {
            var page = Path.Combine(folder, "docs", "index.html");
            if (File.Exists(page) && Ask("Open the start page (examples and requests for Codex)?", true))
                Shell(page);
        }
        Console.WriteLine();
        Console.WriteLine("Press Enter to close.");
        if (!Console.IsInputRedirected) Console.ReadLine();
        return 0;
    }

    // ---------- step runner ----------

    record StepResult<T>(bool? Ok, string Note, T? Value);

    static async Task<T?> Step<T>(string name, Func<Task<StepResult<T>>> run)
    {
        Title(name);
        try
        {
            var r = await run();
            Summary.Add((name, r.Ok, r.Note));
            Line(r.Ok, r.Note);
            return r.Value;
        }
        catch (Exception e)
        {
            Summary.Add((name, false, e.Message));
            Line(false, "Something went wrong: " + e.Message);
            return default;
        }
    }

    static StepResult<T> Ok<T>(string note, T? value = default) => new(true, note, value);
    static StepResult<T> Fail<T>(string note, T? value = default) => new(false, note, value);

    // ---------- 1. project folder ----------

    static async Task<StepResult<string>> ProjectFolder(string? folderArg)
    {
        var folder = folderArg ?? FindProjectNearExe()
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "soupop-data");
        var exists = File.Exists(Path.Combine(folder, "workspace.config.json"));
        Console.WriteLine($"Folder: {folder}");

        var latest = await LatestCommit();
        var versionFile = Path.Combine(folder, ".soupop-version");
        var mine = File.Exists(versionFile) ? File.ReadAllText(versionFile).Trim() : null;

        if (exists && (latest == null || latest == mine || Directory.Exists(Path.Combine(folder, ".git"))))
        {
            var note = latest == null ? "found (couldn't check GitHub for updates)" : latest == mine ? "found, up to date" : "found";
            return Ok(note, folder);
        }
        if (CheckOnly)
            return exists ? new StepResult<string>(null, "found; a newer version is on GitHub", folder)
                          : Fail<string>("not downloaded yet; run SoupopSetup.exe without --check");

        var question = exists ? "A newer version of the project is on GitHub. Update it now? Your sign-in and outputs are kept."
                              : "Download the project into this folder now?";
        if (!Ask(question, true))
            return exists ? new StepResult<string>(null, "found, update skipped", folder) : Fail<string>("not downloaded");

        await DownloadProject(folder);
        if (latest != null) File.WriteAllText(versionFile, latest);
        return Ok(exists ? "updated to the latest version" : "downloaded", folder);
    }

    static string? FindProjectNearExe()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; dir != null && i < 3; i++, dir = dir.Parent)
            if (File.Exists(Path.Combine(dir.FullName, "workspace.config.json"))) return dir.FullName;
        return null;
    }

    static async Task<string?> LatestCommit()
    {
        try
        {
            using var doc = JsonDocument.Parse(await Http.GetStringAsync($"https://api.github.com/repos/{Repo}/commits/{Branch}"));
            return doc.RootElement.GetProperty("sha").GetString();
        }
        catch { return null; }
    }

    static async Task DownloadProject(string folder)
    {
        Console.WriteLine("Downloading the project from GitHub…");
        var tmp = Path.Combine(Path.GetTempPath(), "soupop-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tmp);
        try
        {
            var zip = Path.Combine(tmp, "project.zip");
            await DownloadFile($"https://github.com/{Repo}/archive/refs/heads/{Branch}.zip", zip);
            var unzipped = Path.Combine(tmp, "unzipped");
            ZipFile.ExtractToDirectory(zip, unzipped);
            var root = Directory.GetDirectories(unzipped).Single();  // metabase-agent-main
            CopyTree(root, folder);
        }
        finally { TryDelete(tmp); }
    }

    static void CopyTree(string from, string to)
    {
        foreach (var file in Directory.EnumerateFiles(from, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(from, file).Replace('\\', '/');
            if (Keep.Any(k => rel == k || rel.StartsWith(k + "/"))) continue;
            var dest = Path.Combine(to, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
            File.Copy(file, dest, overwrite: true);
        }
    }

    static JsonNode? LoadConfig(string? folder)
    {
        try { return folder == null ? null : JsonNode.Parse(File.ReadAllText(Path.Combine(folder, "workspace.config.json"))); }
        catch { return null; }
    }

    // ---------- 2. Metabase reachable ----------

    static async Task<StepResult<bool>> CheckMetabase(string baseUrl)
    {
        try
        {
            using var res = await Http.GetAsync(baseUrl + "/api/health");
            return Ok($"{baseUrl} answered, so no VPN step is needed", true);
        }
        catch
        {
            return Fail($"no answer from {baseUrl}. Turn on the org VPN (or check your internet) and run this again", false);
        }
    }

    // ---------- 3. Codex app ----------

    record CodexApp(string Name, string? AppId, string? ExePath);

    static async Task<StepResult<CodexApp>> FindOrInstallCodex()
    {
        var app = FindCodex();
        if (app != null) return Ok($"found: {app.Name}", app);
        if (CheckOnly) return Fail<CodexApp>($"not found; install it from {CodexDownload}");

        Console.WriteLine("The Codex app isn't installed. Opening the download page in your browser.");
        Console.WriteLine("Install Codex, open it once and sign in to your OpenAI (ChatGPT) account.");
        Shell(CodexDownload);
        while (true)
        {
            if (!Ask("Done installing Codex? Press Enter to check again, or type n to skip", true))
                return Fail<CodexApp>($"not installed; get it from {CodexDownload}");
            app = FindCodex();
            if (app != null) return Ok($"found: {app.Name}", app);
            Console.WriteLine("Still can't find Codex. If you just installed it, wait a moment and try again.");
        }
    }

    static CodexApp? FindCodex()
    {
        // Start menu entries cover Store apps and normal installers.
        var (_, outp) = PowerShell("Get-StartApps | Where-Object { $_.Name -match 'Codex' } | Select-Object -First 1 | ForEach-Object { $_.Name + '|' + $_.AppID }");
        var line = outp.Split('\n').Select(l => l.Trim()).FirstOrDefault(l => l.Contains('|'));
        if (line != null)
        {
            var parts = line.Split('|', 2);
            return new CodexApp(parts[0], parts[1], null);
        }
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var programs = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        foreach (var exe in new[] {
            Path.Combine(local, "Programs", "Codex", "Codex.exe"),
            Path.Combine(local, "Codex", "Codex.exe"),
            Path.Combine(programs, "Codex", "Codex.exe") })
            if (File.Exists(exe)) return new CodexApp("Codex", null, exe);
        return null;
    }

    // ---------- 4. Node.js ----------

    static async Task<StepResult<string>> CheckNode()
    {
        var version = NodeVersion();
        if (version != null && Major(version) >= MinNodeMajor) return Ok($"installed ({version})", version);

        var why = version == null ? "not installed" : $"too old ({version}); version {MinNodeMajor} or newer is needed";
        if (CheckOnly) return Fail<string>(why);
        if (!Ask($"Node.js is {why}. Install the current LTS version now? Windows may ask for permission.", true))
            return Fail<string>(why + "; install it from https://nodejs.org");

        if (HasWinget())
            RunVisible("winget", "install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements");
        else
            await InstallNodeMsi();
        RefreshPath();

        version = NodeVersion();
        return version != null && Major(version) >= MinNodeMajor
            ? Ok($"installed ({version})", version)
            : Fail<string>("install didn't finish; install it from https://nodejs.org, then run this again");
    }

    static string? NodeVersion()
    {
        foreach (var node in new[] { "node", Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "nodejs", "node.exe") })
        {
            var (code, outp) = Run(node, "-v");
            if (code == 0 && outp.Trim().StartsWith("v")) return outp.Trim();
        }
        return null;
    }

    static async Task InstallNodeMsi()
    {
        Console.WriteLine("Finding the latest Node.js LTS…");
        using var doc = JsonDocument.Parse(await Http.GetStringAsync("https://nodejs.org/dist/index.json"));
        var release = doc.RootElement.EnumerateArray().First(r =>
            r.GetProperty("lts").ValueKind != JsonValueKind.False &&
            r.GetProperty("files").EnumerateArray().Any(f => f.GetString() == "win-x64-msi"));
        var v = release.GetProperty("version").GetString();
        var msi = Path.Combine(Path.GetTempPath(), $"node-{v}-x64.msi");
        await DownloadFile($"https://nodejs.org/dist/{v}/node-{v}-x64.msi", msi);
        RunVisible("msiexec", $"/i \"{msi}\" /passive /norestart");
        TryDelete(msi);
    }

    // ---------- 5. Python ----------

    static async Task<StepResult<string>> CheckPython()
    {
        var version = PythonVersion();
        if (version != null) return Ok($"installed ({version}); Codex uses it for the project's scripts", version);
        if (CheckOnly) return Fail<string>("not installed");
        if (!Ask("Python isn't installed. Codex needs it for the project's scripts. Install Python 3.12 now?", true))
            return Fail<string>("not installed; get it from https://www.python.org/downloads/");

        if (HasWinget())
            RunVisible("winget", "install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements");
        if (PythonVersion() == null)
        {
            var exe = Path.Combine(Path.GetTempPath(), "python-3.12-installer.exe");
            Console.WriteLine("Downloading Python…");
            await DownloadFile(PythonInstaller, exe);
            RunVisible(exe, "/passive InstallAllUsers=0 PrependPath=1 Include_launcher=1");
            TryDelete(exe);
        }
        RefreshPath();
        version = PythonVersion();
        return version != null ? Ok($"installed ({version})", version)
                               : Fail<string>("install didn't finish; get it from https://www.python.org/downloads/");
    }

    static string? PythonVersion()
    {
        // "python" may be the Microsoft Store shortcut, which prints nothing; only a real answer counts.
        foreach (var (file, args) in new[] { ("py", "-3 --version"), ("python", "--version") })
        {
            var (code, outp) = Run(file, args);
            if (code == 0 && outp.Trim().StartsWith("Python 3")) return outp.Trim();
        }
        return null;
    }

    // ---------- 6. Metabase sign-in ----------

    record Connection(bool Ok, string? User, string? Error, Dictionary<string, (string Name, bool Sql)> Sql);

    static async Task<StepResult<bool>> Connect(string folder, string baseUrl, JsonNode? config)
    {
        var envPath = Path.Combine(folder, ".env");
        var env = ReadEnv(envPath, Path.Combine(folder, "soupop-metabase.env"));
        var dbIds = (config?["databases"] as JsonObject)?.Select(kv => kv.Value!.GetValue<int>()).ToArray() ?? new[] { 2, 3 };

        if (env.ContainsKey("METABASE_API_KEY") || env.ContainsKey("METABASE_PASSWORD"))
        {
            Console.WriteLine("Testing the saved sign-in…");
            var saved = await TestLogin(baseUrl, env.GetValueOrDefault("METABASE_API_KEY"),
                                        env.GetValueOrDefault("METABASE_USERNAME"), env.GetValueOrDefault("METABASE_PASSWORD"), dbIds);
            if (!CheckOnly) WriteState(folder, baseUrl, saved);
            if (saved.Ok)
            {
                Line(true, Describe(saved));
                if (CheckOnly || !Ask("Change the saved sign-in?", false)) return SignInResult(saved);
            }
            else Line(false, saved.Error ?? "The saved sign-in didn't work.");
        }
        else if (CheckOnly) return Fail("no sign-in saved yet", false);

        while (true)
        {
            Console.WriteLine();
            Console.WriteLine("How do you want to sign in to Metabase?");
            Console.WriteLine("  1  My Metabase email and password (your own permissions apply)");
            Console.WriteLine("  2  An API key from a Metabase admin");
            var choice = Prompt("Type 1 or 2", "1");
            string? key = null, user = null, pass = null;
            if (choice == "2") key = ReadSecret("Paste the API key (it stays hidden)");
            else { user = Prompt("Metabase email", null); pass = ReadSecret("Metabase password (it stays hidden)"); }

            Console.WriteLine("Checking with Metabase…");
            var conn = await TestLogin(baseUrl, key, user, pass, dbIds);
            if (conn.Ok)
            {
                var values = new Dictionary<string, string> { ["METABASE_URL"] = baseUrl };
                if (key != null) values["METABASE_API_KEY"] = key;
                else { values["METABASE_USERNAME"] = user!; values["METABASE_PASSWORD"] = pass!; }
                SaveEnv(envPath, values);
                TryDelete(Path.Combine(folder, "soupop-metabase.env"));  // it would win over .env
                WriteState(folder, baseUrl, conn);
                Console.WriteLine("Saved in the project folder (.env). It stays on this computer.");
                return SignInResult(conn);
            }
            Line(false, conn.Error ?? "That didn't work.");
            if (!Ask("Try again?", true)) return Fail("not connected", false);
        }
    }

    static StepResult<bool> SignInResult(Connection c)
    {
        var noSql = c.Sql.Values.Where(d => !d.Sql).Select(d => d.Name).ToList();
        return noSql.Count == 0
            ? Ok(Describe(c), true)
            : new StepResult<bool>(false, Describe(c) + ". Ask a Metabase admin to give your group SQL (native query) access to " + string.Join(", ", noSql), true);
    }

    static string Describe(Connection c) =>
        $"signed in as {c.User}; " + string.Join(", ", c.Sql.Values.Select(d => $"{d.Name}: {(d.Sql ? "SQL allowed" : "no SQL access")}"));

    static async Task<Connection> TestLogin(string baseUrl, string? apiKey, string? user, string? pass, int[] dbIds)
    {
        var empty = new Dictionary<string, (string, bool)>();
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/user/current");
            if (!string.IsNullOrEmpty(apiKey)) req.Headers.Add("X-API-Key", apiKey);
            else
            {
                var body = new JsonObject { ["username"] = user, ["password"] = pass }.ToJsonString();
                using var s = await Http.PostAsync(baseUrl + "/api/session", new StringContent(body, Encoding.UTF8, "application/json"));
                if (!s.IsSuccessStatusCode) return new(false, null, "Metabase did not accept that email or password.", empty);
                using var sdoc = JsonDocument.Parse(await s.Content.ReadAsStringAsync());
                req.Headers.Add("X-Metabase-Session", sdoc.RootElement.GetProperty("id").GetString());
            }
            var headers = req.Headers.ToList();
            using var u = await Http.SendAsync(req);
            if (!u.IsSuccessStatusCode) return new(false, null, "Metabase did not accept that API key.", empty);
            using var udoc = JsonDocument.Parse(await u.Content.ReadAsStringAsync());
            var who = udoc.RootElement.TryGetProperty("email", out var e) && e.ValueKind == JsonValueKind.String ? e.GetString() : "API key";

            using var dreq = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/database");
            foreach (var h in headers) dreq.Headers.Add(h.Key, h.Value);
            using var d = await Http.SendAsync(dreq);
            using var ddoc = JsonDocument.Parse(await d.Content.ReadAsStringAsync());
            var list = ddoc.RootElement.ValueKind == JsonValueKind.Array ? ddoc.RootElement
                     : ddoc.RootElement.TryGetProperty("data", out var data) ? data : default;
            var sql = new Dictionary<string, (string Name, bool Sql)>();
            foreach (var id in dbIds)
            {
                (string, bool) entry = ($"Database {id}", false);
                if (list.ValueKind == JsonValueKind.Array)
                    foreach (var db in list.EnumerateArray())
                        if (db.TryGetProperty("id", out var dbId) && dbId.GetInt32() == id)
                            entry = (db.GetProperty("name").GetString() ?? entry.Item1,
                                     db.TryGetProperty("native_permissions", out var np) && np.GetString() == "write");
                sql[id.ToString()] = entry;
            }
            return new(true, who, null, sql);
        }
        catch (Exception ex)
        {
            return new(false, null, "Couldn't reach Metabase: " + ex.Message, empty);
        }
    }

    static Dictionary<string, string> ReadEnv(params string[] paths)
    {
        // Same order as scripts-py/metabase_agent.py: soupop-metabase.env wins over .env.
        var values = new Dictionary<string, string>();
        foreach (var path in paths.Where(File.Exists))
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                var eq = line.IndexOf('=');
                if (line.Length == 0 || line.StartsWith("#") || eq < 1) continue;
                values[line[..eq].Trim()] = line[(eq + 1)..].Trim().Trim('"', '\'');
            }
        return values;
    }

    static void SaveEnv(string path, Dictionary<string, string> values)
    {
        // Keep any other lines; replace only the sign-in lines.
        var kept = File.Exists(path)
            ? File.ReadAllLines(path).Where(l => l.Trim().Length > 0 && !EnvKeys.Any(k => l.StartsWith(k + "=")))
            : Enumerable.Empty<string>();
        File.WriteAllLines(path, values.Select(kv => $"{kv.Key}={kv.Value}").Concat(kept));
    }

    // The start page reads "connection" from this file to show the sign-in status.
    static void WriteState(string folder, string baseUrl, Connection c)
    {
        var path = Path.Combine(folder, ".workspace-state.json");
        JsonObject state;
        try { state = JsonNode.Parse(File.ReadAllText(path)) as JsonObject ?? new(); } catch { state = new(); }
        var now = DateTime.UtcNow.ToString("o");
        var sql = new JsonObject();
        foreach (var (id, d) in c.Sql)
            sql[id] = new JsonObject { ["name"] = d.Name, ["visible"] = true, ["sql"] = d.Sql };
        state["checked_at"] = now;
        state["metabase_url"] = baseUrl;
        state["mode"] = "api";
        state["connection"] = new JsonObject
        {
            ["ok"] = c.Ok, ["user"] = c.User, ["error"] = c.Error, ["checked_at"] = now, ["sql_access"] = sql,
        };
        File.WriteAllText(path, state.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }

    // ---------- 7. open Codex ----------

    static Task<StepResult<bool>> OpenCodex(string folder, CodexApp? codex)
    {
        CopyToClipboard(folder);
        Console.WriteLine("The project folder path is copied:");
        Console.WriteLine("  " + folder);
        Console.WriteLine("In Codex, add a new project (or Open folder), paste the path with Ctrl+V, and keep that project selected when you ask about Soupop data.");
        if (codex == null) return Task.FromResult(Fail("Codex isn't installed, so it wasn't opened", false));
        if (codex.AppId != null) Process.Start("explorer.exe", $"shell:AppsFolder\\{codex.AppId}");
        else Shell(codex.ExePath!);
        return Task.FromResult(Ok("Codex is opening; add the folder above as a project if it isn't there yet", true));
    }

    static void CopyToClipboard(string text) =>
        PowerShell($"Set-Clipboard -Value '{text.Replace("'", "''")}'");

    // ---------- helpers ----------

    static HttpClient NewClient(TimeSpan timeout)
    {
        var c = new HttpClient { Timeout = timeout };
        c.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("SoupopSetup", "1.0"));
        return c;
    }

    static async Task DownloadFile(string url, string path)
    {
        using var res = await Download.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
        res.EnsureSuccessStatusCode();
        await using var file = File.Create(path);
        await res.Content.CopyToAsync(file);
    }

    static (int Code, string Output) Run(string file, string args, int timeoutMs = 30000)
    {
        try
        {
            var psi = new ProcessStartInfo(file, args)
            {
                UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true,
            };
            using var p = Process.Start(psi)!;
            var stdout = p.StandardOutput.ReadToEndAsync();
            var stderr = p.StandardError.ReadToEndAsync();
            if (!p.WaitForExit(timeoutMs)) { try { p.Kill(true); } catch { } return (-1, ""); }
            return (p.ExitCode, stdout.Result + stderr.Result);
        }
        catch (Win32Exception) { return (-1, ""); }  // program not found
    }

    // Installers show their own progress, so they get the console.
    static int RunVisible(string file, string args)
    {
        try
        {
            using var p = Process.Start(new ProcessStartInfo(file, args) { UseShellExecute = false })!;
            p.WaitForExit();
            return p.ExitCode;
        }
        catch (Win32Exception e) { Console.WriteLine($"Couldn't run {file}: {e.Message}"); return -1; }
    }

    static (int Code, string Output) PowerShell(string script)
    {
        var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
        return Run("powershell.exe", $"-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {encoded}");
    }

    static void Shell(string target)
    {
        try { Process.Start(new ProcessStartInfo(target) { UseShellExecute = true }); }
        catch (Exception e) { Console.WriteLine($"Couldn't open {target}: {e.Message}"); }
    }

    static bool HasWinget() => Run("winget", "--version").Code == 0;

    // Installers change PATH for new windows only; reload it so this one sees the new programs.
    static void RefreshPath()
    {
        var machine = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.Machine) ?? "";
        var user = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.User) ?? "";
        Environment.SetEnvironmentVariable("Path", machine + ";" + user);
    }

    static int Major(string version) =>
        int.TryParse(version.TrimStart('v').Split('.')[0], out var m) ? m : 0;

    static void TryDelete(string path)
    {
        try
        {
            if (Directory.Exists(path)) Directory.Delete(path, true);
            else if (File.Exists(path)) File.Delete(path);
        }
        catch { }
    }

    static string? ArgValue(string[] args, string name)
    {
        var i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? Path.GetFullPath(args[i + 1]) : null;
    }

    // ---------- console ----------

    static void Title(string text)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine(text);
        Console.ResetColor();
    }

    static void Line(bool? ok, string text)
    {
        Console.ForegroundColor = ok == true ? ConsoleColor.Green : ok == false ? ConsoleColor.Yellow : ConsoleColor.Gray;
        Console.Write(ok == true ? "  OK   " : ok == false ? "  FIX  " : "  --   ");
        Console.ResetColor();
        Console.WriteLine(text);
    }

    static bool Ask(string question, bool yes)
    {
        if (CheckOnly || Console.IsInputRedirected) return yes;
        Console.Write($"{question} [{(yes ? "Y/n" : "y/N")}] ");
        var a = (Console.ReadLine() ?? "").Trim().ToLowerInvariant();
        return a.Length == 0 ? yes : a.StartsWith("y");
    }

    static string Prompt(string label, string? fallback)
    {
        while (true)
        {
            Console.Write(fallback == null ? $"{label}: " : $"{label} [{fallback}]: ");
            var a = (Console.ReadLine() ?? "").Trim();
            if (a.Length > 0) return a;
            if (fallback != null) return fallback;
        }
    }

    static string ReadSecret(string label)
    {
        Console.Write(label + ": ");
        var sb = new StringBuilder();
        while (true)
        {
            var k = Console.ReadKey(intercept: true);
            if (k.Key == ConsoleKey.Enter) break;
            if (k.Key == ConsoleKey.Backspace) { if (sb.Length > 0) sb.Length--; continue; }
            if (!char.IsControl(k.KeyChar)) sb.Append(k.KeyChar);
        }
        Console.WriteLine();
        return sb.ToString().Trim();
    }
}
