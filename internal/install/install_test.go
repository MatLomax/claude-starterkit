package install

import (
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	starterkit "github.com/MatLomax/claude-starterkit"
	"github.com/MatLomax/claude-starterkit/internal/ojson"
)

// opts runs the installer the way it runs on this OS: Windows mode on Windows, Unix elsewhere.
func opts(t *testing.T, worklog bool) Options {
	t.Helper()
	o := Options{
		ClaudeDir: t.TempDir(),
		Payload:   starterkit.Payload,
		Worklog:   worklog,
		PyCmd:     "python3",
		Out:       io.Discard,
		Now:       func() time.Time { return time.Date(2026, 9, 27, 12, 0, 0, 0, time.Local) },
	}
	if runtime.GOOS == "windows" {
		o.Windows, o.PyCmd, o.PsExe = true, "py -3", "pwsh"
	}
	return o
}

// statusline is the statusline script this OS gets; the other one must not be installed.
func statusline(o Options) (want, not string) {
	if o.Windows {
		return "statusline-command.ps1", "statusline-command.sh"
	}
	return "statusline-command.sh", "statusline-command.ps1"
}

func read(t *testing.T, p string) string {
	t.Helper()
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestFilesInstallsPayloadAndImportsOnce(t *testing.T) {
	o := opts(t, true)
	md := filepath.Join(o.ClaudeDir, "CLAUDE.md")
	if err := os.WriteFile(md, []byte("# mine\nkeep this"), 0o644); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if err := Files(o); err != nil {
			t.Fatal(err)
		}
	}
	got := read(t, md)
	want := "# mine\nkeep this\n@./CLAUDE.starterkit.md\n\n@./CLAUDE.starterkit-worklog.md\n"
	if got != want {
		t.Fatalf("CLAUDE.md = %q, want %q", got, want)
	}

	// Every payload file lands with its content; on Unix, hooks and the statusline are executable.
	sl, notSL := statusline(o)
	err := fs.WalkDir(starterkit.Payload, ".", func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() || p == notSL {
			return err
		}
		want, _ := fs.ReadFile(starterkit.Payload, p)
		if got := read(t, filepath.Join(o.ClaudeDir, p)); got != string(want) {
			t.Errorf("%s differs from the payload", p)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if !o.Windows {
		for _, p := range []string{"hooks/git-guard.py", sl} {
			st, err := os.Stat(filepath.Join(o.ClaudeDir, p))
			if err != nil {
				t.Fatal(err)
			}
			if st.Mode().Perm()&0o111 == 0 {
				t.Errorf("%s is not executable", p)
			}
		}
	}
	if _, err := os.Stat(filepath.Join(o.ClaudeDir, notSL)); !os.IsNotExist(err) {
		t.Errorf("installed %s, which is for the other OS", notSL)
	}
}

func TestFilesWithoutWorklog(t *testing.T) {
	o := opts(t, false)
	if err := Files(o); err != nil {
		t.Fatal(err)
	}
	if got := read(t, filepath.Join(o.ClaudeDir, "CLAUDE.md")); got != "@./CLAUDE.starterkit.md\n" {
		t.Fatalf("CLAUDE.md = %q", got)
	}
	if _, err := os.Stat(filepath.Join(o.ClaudeDir, "CLAUDE.starterkit-worklog.md")); !os.IsNotExist(err) {
		t.Fatal("worklog add-on installed without being asked for")
	}
	parts, _ := fs.Glob(starterkit.Payload, "CLAUDE.starterkit*.md")
	for _, p := range parts {
		if p == "CLAUDE.starterkit-worklog.md" {
			continue
		}
		if _, err := os.Stat(filepath.Join(o.ClaudeDir, p)); err != nil {
			t.Errorf("ruleset part %s not installed", p)
		}
	}
}

func settingsOf(t *testing.T, o Options) *ojson.Object {
	t.Helper()
	v, err := ojson.Decode([]byte(read(t, filepath.Join(o.ClaudeDir, "settings.json"))))
	if err != nil {
		t.Fatal(err)
	}
	return v.(*ojson.Object)
}

func TestSettingsFreshInstall(t *testing.T) {
	o := opts(t, true)
	o.ProjectMemory = true
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	cfg := settingsOf(t, o)
	want := []string{"hooks", "attribution", "statusLine", "env", "includeCoAuthoredBy", "enableArtifact",
		"askUserQuestionTimeout", "worktree", "feedbackDrafts", "promptSuggestionEnabled",
		"spinnerTipsEnabled", "remoteControlAtStartup", "effortLevel", "autoCompactEnabled", "cleanupPeriodDays", "extraKnownMarketplaces"}
	if got := strings.Join(cfg.Keys(), ","); got != strings.Join(want, ",") {
		t.Fatalf("keys = %s", got)
	}
	s := read(t, filepath.Join(o.ClaudeDir, "settings.json"))
	for _, ev := range Hooks {
		for _, h := range ev.hooks {
			cmd := o.PyCmd + " " + o.hooksDir() + "/" + h.script
			if !strings.Contains(s, quoted(cmd)) {
				t.Errorf("missing hook %s", cmd)
			}
			if _, err := fs.Stat(starterkit.Payload, "hooks/"+h.script); err != nil {
				t.Errorf("hook table names %s, which is not in the payload", h.script)
			}
		}
	}
	if !strings.Contains(s, `"asyncRewake": true`) {
		t.Error("PostCompact hook lost its asyncRewake field")
	}
	if !strings.Contains(s, quoted(o.StatuslineCommand())) {
		t.Error("statusLine command wrong")
	}
	if !o.Windows && o.StatuslineCommand() != "bash "+filepath.Join(o.ClaudeDir, "statusline-command.sh") {
		t.Errorf("Unix statusLine = %q", o.StatuslineCommand())
	}
	if !strings.Contains(s, `"cleanupPeriodDays": 36500`) {
		t.Error("cleanupPeriodDays not written as a number")
	}
}

// The project-memory hook is wired only when its add-on is chosen, and then once per event: a
// SessionStart hook with no matcher, so it runs however the session starts, and a PreToolUse hook on
// Write|Edit|Bash|PowerShell, so the first memory saved lands in the project and a shell command
// cannot write one unseen.
func TestProjectMemoryHookOnlyWhenChosen(t *testing.T) {
	o := opts(t, false)
	cmd := o.hookCommand("project-memory.py")
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	if n := hookEntries(t, o, cmd); n != 0 {
		t.Fatalf("project-memory hook wired without the add-on (%d entries)", n)
	}
	o.ProjectMemory = true
	for run := 0; run < 2; run++ {
		if err := Settings(o); err != nil {
			t.Fatal(err)
		}
		if n := hookEntries(t, o, cmd); n != 2 {
			t.Fatalf("run %d: %d project-memory entries, want 2", run, n)
		}
	}
	hv, _ := settingsOf(t, o).Get("hooks")
	want := map[string]string{"SessionStart": "", "PreToolUse": "Write|Edit|Bash|PowerShell"}
	for ev, matcher := range want {
		groups, _ := hv.(*ojson.Object).Get(ev)
		found := false
		for _, g := range groups.([]any) {
			gobj := g.(*ojson.Object)
			list, _ := gobj.Get("hooks")
			if c, _ := list.([]any)[0].(*ojson.Object).Get("command"); c != cmd {
				continue
			}
			found = true
			m, _ := gobj.Get("matcher")
			if got, _ := m.(string); got != matcher {
				t.Fatalf("%s project-memory matcher = %q, want %q", ev, got, matcher)
			}
		}
		if !found {
			t.Fatalf("project-memory hook not wired under %s", ev)
		}
	}
}

// quoted is how a settings.json command value appears in the written file.
func quoted(cmd string) string {
	var b strings.Builder
	encodeForTest(&b, cmd)
	return `"command": ` + b.String()
}

func encodeForTest(b *strings.Builder, s string) {
	out, _ := ojson.Encode(s)
	b.WriteString(strings.TrimSuffix(string(out), "\n"))
}

func TestSettingsMergeKeepsUserValuesAndIsIdempotent(t *testing.T) {
	o := opts(t, false)
	path := filepath.Join(o.ClaudeDir, "settings.json")
	user := `{
  "model": "opus",
  "env": {
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-8",
    "MY_VAR": "x",
    "DO_NOT_TRACK": "0"
  },
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "my-stop-hook"
          }
        ]
      }
    ]
  },
  "statusLine": {
    "type": "command",
    "command": "mine"
  },
  "effortLevel": "medium"
}
`
	if err := os.WriteFile(path, []byte(user), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	if got := read(t, path+".bak-20260927-120000"); got != user {
		t.Fatal("backup does not hold the original settings")
	}
	first := read(t, path)
	cfg := settingsOf(t, o)
	if k := cfg.Keys(); k[0] != "model" || k[1] != "env" || k[2] != "hooks" || k[3] != "statusLine" || k[4] != "effortLevel" {
		t.Fatalf("user keys reordered: %v", k)
	}
	env, _ := cfg.Get("env")
	e := env.(*ojson.Object)
	if e.Has("ANTHROPIC_DEFAULT_OPUS_MODEL") {
		t.Error("former kit opus pin not removed")
	}
	if v, _ := e.Get("DO_NOT_TRACK"); v != "0" {
		t.Error("user's DO_NOT_TRACK overwritten")
	}
	if v, _ := cfg.Get("effortLevel"); v != "medium" {
		t.Error("user's effortLevel overwritten")
	}
	if strings.Contains(first, "extraKnownMarketplaces") {
		t.Error("marketplace registered without the worklog add-on")
	}
	if !strings.Contains(first, `"command": "my-stop-hook"`) || !strings.Contains(first, `"command": "mine"`) {
		t.Error("user's hook or statusline lost")
	}

	// A second run changes nothing and adds no duplicates.
	o.Now = func() time.Time { return time.Date(2026, 9, 27, 12, 0, 1, 0, time.Local) }
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	if second := read(t, path); second != first {
		t.Fatalf("second run changed settings.json:\n%s", second)
	}
}

func TestSettingsKeepsOtherOpusPin(t *testing.T) {
	o := opts(t, false)
	path := filepath.Join(o.ClaudeDir, "settings.json")
	os.WriteFile(path, []byte(`{"env": {"ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-9"}}`), 0o644)
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(read(t, path), `"ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-9"`) {
		t.Fatal("a user-chosen opus pin was removed")
	}
}

func TestSettingsRejectsBrokenJSON(t *testing.T) {
	o := opts(t, false)
	path := filepath.Join(o.ClaudeDir, "settings.json")
	os.WriteFile(path, []byte(`{"a": `), 0o644)
	if err := Settings(o); err == nil {
		t.Fatal("expected an error")
	}
	if read(t, path) != `{"a": ` {
		t.Fatal("broken settings.json was rewritten")
	}
}

func TestWindowsCommandsUseForwardSlashes(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows paths are only built on Windows")
	}
	o := Options{ClaudeDir: `C:\Users\me\.claude`, Windows: true, PyCmd: "py -3", PsExe: "pwsh"}
	if got := o.hooksDir(); got != "C:/Users/me/.claude/hooks" {
		t.Fatalf("hooksDir = %q", got)
	}
	if got := o.StatuslineCommand(); got != `pwsh -NoProfile -File "C:/Users/me/.claude/statusline-command.ps1"` {
		t.Fatalf("statusline = %q", got)
	}
}

func TestShellArgQuotesOnlyWhenNeeded(t *testing.T) {
	for _, c := range []struct {
		in      string
		windows bool
		want    string
	}{
		{"/home/me/.claude/hooks/git-guard.py", false, "/home/me/.claude/hooks/git-guard.py"},
		{"/home/jose.müller+x@corp/.claude/hooks/a-b_c.py", false, "/home/jose.müller+x@corp/.claude/hooks/a-b_c.py"},
		{"C:/Users/me/.claude/hooks/git-guard.py", true, "C:/Users/me/.claude/hooks/git-guard.py"},
		{"/Users/John Smith/.claude/hooks/git-guard.py", false, `"/Users/John Smith/.claude/hooks/git-guard.py"`},
		{"C:/Users/John Smith/.claude/hooks/git-guard.py", true, `"C:/Users/John Smith/.claude/hooks/git-guard.py"`},
		{"/home/a,b/x.py", false, "/home/a,b/x.py"},
		{"C:/Users/RUNNER~1/.claude/hooks/x.py", true, "C:/Users/RUNNER~1/.claude/hooks/x.py"},
		{"~/x.py", false, `"~/x.py"`},
		{"C:/Users/a,b/x.py", true, `"C:/Users/a,b/x.py"`},
		{"/home/o'brien/x.py", false, `"/home/o'brien/x.py"`},
		{"/home/a$b`c\"d\\e/x.py", false, `"/home/a\$b\` + "`" + `c\"d\\e/x.py"`},
	} {
		if got := shellArg(c.in, c.windows); got != c.want {
			t.Errorf("shellArg(%q, windows=%v) = %s, want %s", c.in, c.windows, got, c.want)
		}
	}
}

func TestCommandsQuoteAPathWithASpace(t *testing.T) {
	unix := Options{ClaudeDir: "/Users/John Smith/.claude", PyCmd: "python3"}
	if got := unix.hookCommand("git-guard.py"); got != `python3 "/Users/John Smith/.claude/hooks/git-guard.py"` {
		t.Errorf("Unix hook = %s", got)
	}
	if got := unix.StatuslineCommand(); got != `bash "/Users/John Smith/.claude/statusline-command.sh"` {
		t.Errorf("Unix statusLine = %s", got)
	}
	win := Options{ClaudeDir: "C:/Users/John Smith/.claude", Windows: true, PyCmd: "py -3", PsExe: "pwsh"}
	if got := win.hookCommand("git-guard.py"); got != `py -3 "C:/Users/John Smith/.claude/hooks/git-guard.py"` {
		t.Errorf("Windows hook = %s", got)
	}
	if got := win.StatuslineCommand(); got != `pwsh -NoProfile -File "C:/Users/John Smith/.claude/statusline-command.ps1"` {
		t.Errorf("Windows statusLine = %s", got)
	}

	// An ordinary path is written exactly as earlier installs wrote it.
	plain := Options{ClaudeDir: "/home/me/.claude", PyCmd: "python3"}
	if got := plain.hookCommand("git-guard.py"); got != "python3 /home/me/.claude/hooks/git-guard.py" {
		t.Errorf("plain hook = %s", got)
	}
	if got := plain.StatuslineCommand(); got != "bash /home/me/.claude/statusline-command.sh" {
		t.Errorf("plain statusLine = %s", got)
	}
}

// hookEntries counts the hook entries in settings.json running cmd, across every event.
func hookEntries(t *testing.T, o Options, cmd string) int {
	t.Helper()
	hv, _ := settingsOf(t, o).Get("hooks")
	n := 0
	for _, ev := range hv.(*ojson.Object).Keys() {
		gv, _ := hv.(*ojson.Object).Get(ev)
		for _, g := range gv.([]any) {
			list, _ := g.(*ojson.Object).Get("hooks")
			for _, x := range list.([]any) {
				if c, _ := x.(*ojson.Object).Get("command"); c == cmd {
					n++
				}
			}
		}
	}
	return n
}

// registrations is how many events the hook table registers script under (a hook such as
// notification-guard.py runs on more than one).
func registrations(script string) int {
	n := 0
	for _, ev := range Hooks {
		for _, h := range ev.hooks {
			if h.script == script {
				n++
			}
		}
	}
	return n
}

func TestSettingsReplacesLegacyUnquotedCommands(t *testing.T) {
	for _, windows := range []bool{false, true} {
		o := opts(t, false)
		o.ProjectMemory = true
		o.Windows, o.PyCmd, o.PsExe = windows, "python3", "pwsh"
		if windows {
			o.PyCmd = "py -3"
		}
		o.ClaudeDir = filepath.Join(o.ClaudeDir, "John Smith", ".claude")
		if err := os.MkdirAll(o.ClaudeDir, 0o755); err != nil {
			t.Fatal(err)
		}

		// A settings.json as an earlier install left it: every hook unquoted, in its own group, plus
		// git-guard's unquoted entry sharing a group with a user hook, and nul-guard registered both
		// unquoted and quoted.
		cfg := ojson.NewObject()
		hooks := ojson.NewObject()
		entry := func(cmds ...string) *ojson.Object {
			var list []any
			for _, c := range cmds {
				x := ojson.NewObject()
				x.Set("type", "command")
				x.Set("command", c)
				list = append(list, x)
			}
			g := ojson.NewObject()
			g.Set("hooks", list)
			return g
		}
		for _, ev := range Hooks {
			var groups []any
			for _, h := range ev.hooks {
				switch h.script {
				case "git-guard.py":
					groups = append(groups, entry("my-hook", o.legacyHookCommand(h.script)))
				case "nul-guard.py":
					groups = append(groups, entry(o.legacyHookCommand(h.script)), entry(o.hookCommand(h.script)))
				default:
					groups = append(groups, entry(o.legacyHookCommand(h.script)))
				}
			}
			hooks.Set(ev.event, groups)
		}
		cfg.Set("hooks", hooks)
		sl := ojson.NewObject()
		sl.Set("type", "command")
		sl.Set("command", o.legacyStatuslineCommand())
		cfg.Set("statusLine", sl)
		data, _ := ojson.Encode(cfg)
		if err := os.WriteFile(filepath.Join(o.ClaudeDir, "settings.json"), data, 0o644); err != nil {
			t.Fatal(err)
		}

		for run := 0; run < 2; run++ {
			if err := Settings(o); err != nil {
				t.Fatal(err)
			}
			for _, ev := range Hooks {
				for _, h := range ev.hooks {
					if o.legacyHookCommand(h.script) == o.hookCommand(h.script) {
						t.Fatalf("windows=%v: %s needs no quoting, so the test proves nothing", windows, h.script)
					}
					if n, want := hookEntries(t, o, o.hookCommand(h.script)), registrations(h.script); n != want {
						t.Errorf("windows=%v run %d: %d entries for %s, want %d", windows, run, n, o.hookCommand(h.script), want)
					}
					if n := hookEntries(t, o, o.legacyHookCommand(h.script)); n != 0 {
						t.Errorf("windows=%v run %d: legacy %s left behind", windows, run, o.legacyHookCommand(h.script))
					}
				}
			}
			if n := hookEntries(t, o, "my-hook"); n != 1 {
				t.Errorf("windows=%v: user hook sharing a group with a legacy entry lost", windows)
			}
			s := settingsOf(t, o)
			slv, _ := s.Get("statusLine")
			if c, _ := slv.(*ojson.Object).Get("command"); c != o.StatuslineCommand() {
				t.Errorf("windows=%v: statusLine = %v, want %s", windows, c, o.StatuslineCommand())
			}
		}
	}
}

// The commands run the way Claude Code runs a hook or statusline command on Unix: the whole
// string through `sh -c`. With the interpreter swapped for cat, the output is the script itself
// only if the shell resolved the quoted path to the installed file.
func TestCommandsRunThroughShWithAnAwkwardPath(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("sh -c is the Unix execution path")
	}
	o := opts(t, false)
	o.ClaudeDir = filepath.Join(o.ClaudeDir, "John Smith's $HOME `x` \"q\" \\b", ".claude")
	if err := os.MkdirAll(o.ClaudeDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := Files(o); err != nil {
		t.Fatal(err)
	}
	o.PyCmd = "cat"
	run := func(cmd, file string) {
		t.Helper()
		out, err := exec.Command("sh", "-c", cmd).CombinedOutput()
		if err != nil {
			t.Fatalf("sh -c %s: %v\n%s", cmd, err, out)
		}
		if want := read(t, filepath.Join(o.ClaudeDir, file)); string(out) != want {
			t.Fatalf("sh -c %s did not read %s", cmd, file)
		}
	}
	for _, ev := range Hooks {
		for _, h := range ev.hooks {
			run(o.hookCommand(h.script), filepath.Join("hooks", h.script))
		}
	}
	sl := o.StatuslineCommand()
	if !strings.HasPrefix(sl, "bash ") {
		t.Fatalf("statusLine = %s", sl)
	}
	run("cat "+strings.TrimPrefix(sl, "bash "), "statusline-command.sh")
}
