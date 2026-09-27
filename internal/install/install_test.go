package install

import (
	"io"
	"io/fs"
	"os"
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
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	cfg := settingsOf(t, o)
	want := []string{"hooks", "attribution", "statusLine", "env", "includeCoAuthoredBy", "enableArtifact",
		"askUserQuestionTimeout", "worktree", "feedbackDrafts", "promptSuggestionEnabled",
		"remoteControlAtStartup", "effortLevel", "cleanupPeriodDays", "extraKnownMarketplaces"}
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
