//go:build unix

package install

import (
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"testing"

	starterkit "github.com/MatLomax/claude-starterkit"
)

// withUmask runs the rest of the test under umask m (inherited by the shell the reference runs in).
func withUmask(t *testing.T, m int) {
	t.Helper()
	old := syscall.Umask(m)
	t.Cleanup(func() { syscall.Umask(old) })
}

// payloadFile is one installed file and how the shell installer (install.sh on main) laid it
// down: cp from a checkout where it has srcMode, then chmod +x when exec is set.
type payloadFile struct {
	name    string
	srcMode os.FileMode
	exec    bool
}

func unixPayload(t *testing.T) []payloadFile {
	t.Helper()
	var files []payloadFile
	parts, _ := fs.Glob(starterkit.Payload, "CLAUDE.starterkit*.md")
	for _, p := range parts {
		files = append(files, payloadFile{p, 0o644, false})
	}
	hooks, _ := fs.Glob(starterkit.Payload, "hooks/*.py")
	for _, h := range hooks {
		files = append(files, payloadFile{h, 0o755, true})
	}
	files = append(files,
		payloadFile{"statusline-command.sh", 0o644, true},
		payloadFile{"review-rules.md", 0o644, false})
	if len(parts) == 0 || len(hooks) == 0 {
		t.Fatal("payload has no ruleset parts or hooks")
	}
	return files
}

// shellMode is the mode install.sh on main gives the file: `cp` over dst (pre-created with
// existing when existing != 0), then `chmod +x` when exec is set, run by a real shell under the
// current umask.
func shellMode(t *testing.T, f payloadFile, existing os.FileMode) os.FileMode {
	t.Helper()
	dir := t.TempDir()
	src, dst := filepath.Join(dir, "src"), filepath.Join(dir, "dst")
	if err := os.WriteFile(src, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(src, f.srcMode); err != nil {
		t.Fatal(err)
	}
	if existing != 0 {
		if err := os.WriteFile(dst, []byte("old"), 0o600); err != nil {
			t.Fatal(err)
		}
		if err := os.Chmod(dst, existing); err != nil {
			t.Fatal(err)
		}
	}
	script := `cp "$1" "$2"`
	if f.exec {
		script += ` && chmod +x "$2"`
	}
	if out, err := exec.Command("sh", "-c", script, "sh", src, dst).CombinedOutput(); err != nil {
		t.Fatalf("reference cp: %v: %s", err, out)
	}
	return modeOf(t, dst)
}

// shellNewFileMode is the mode a shell redirect (and Python's open(..., "w")) gives a new file.
func shellNewFileMode(t *testing.T) os.FileMode {
	t.Helper()
	p := filepath.Join(t.TempDir(), "f")
	if out, err := exec.Command("sh", "-c", `printf x >> "$1"`, "sh", p).CombinedOutput(); err != nil {
		t.Fatalf("%v: %s", err, out)
	}
	return modeOf(t, p)
}

func modeOf(t *testing.T, p string) os.FileMode {
	t.Helper()
	st, err := os.Stat(p)
	if err != nil {
		t.Fatal(err)
	}
	return st.Mode().Perm()
}

// A fresh install under a restrictive umask gives every file the mode install.sh on main gives it
// (with umask 077: 0600 for the markdown, 0700 for hooks and the statusline).
func TestFreshInstallModesFollowUmask(t *testing.T) {
	withUmask(t, 0o077)
	o := opts(t, true)
	if err := Files(o); err != nil {
		t.Fatal(err)
	}
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	for _, f := range unixPayload(t) {
		want := shellMode(t, f, 0)
		if got := modeOf(t, filepath.Join(o.ClaudeDir, f.name)); got != want {
			t.Errorf("%s: mode %o, install.sh gives %o", f.name, got, want)
		}
	}
	if got := modeOf(t, filepath.Join(o.ClaudeDir, "CLAUDE.starterkit.md")); got != 0o600 {
		t.Errorf("ruleset mode %o under umask 077, want 600", got)
	}
	if got := modeOf(t, filepath.Join(o.ClaudeDir, "hooks", "git-guard.py")); got != 0o700 {
		t.Errorf("hook mode %o under umask 077, want 700", got)
	}
	newMode := shellNewFileMode(t)
	for _, p := range []string{"CLAUDE.md", "settings.json"} {
		if got := modeOf(t, filepath.Join(o.ClaudeDir, p)); got != newMode {
			t.Errorf("%s: mode %o, the shell installer gives %o", p, got, newMode)
		}
	}
	if got := modeOf(t, filepath.Join(o.ClaudeDir, "hooks")); got != 0o700 {
		t.Errorf("hooks dir mode %o under umask 077, want 700", got)
	}
}

// Re-installing over existing files keeps their modes, as cp does; hooks and the statusline only
// gain the execute bits chmod +x adds under the umask. A settings.json backup keeps the original's
// mode exactly.
func TestReinstallKeepsExistingModes(t *testing.T) {
	withUmask(t, 0o022)
	o := opts(t, true)
	if err := os.MkdirAll(filepath.Join(o.ClaudeDir, "hooks"), 0o755); err != nil {
		t.Fatal(err)
	}
	odd := []os.FileMode{0o640, 0o600, 0o604, 0o664, 0o750}
	files := unixPayload(t)
	for i, f := range files {
		p := filepath.Join(o.ClaudeDir, f.name)
		if err := os.WriteFile(p, []byte("old"), 0o600); err != nil {
			t.Fatal(err)
		}
		if err := os.Chmod(p, odd[i%len(odd)]); err != nil {
			t.Fatal(err)
		}
	}
	settings := filepath.Join(o.ClaudeDir, "settings.json")
	if err := os.WriteFile(settings, []byte("{}"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(settings, 0o664); err != nil {
		t.Fatal(err)
	}
	withUmask(t, 0o077)
	if err := Files(o); err != nil {
		t.Fatal(err)
	}
	if err := Settings(o); err != nil {
		t.Fatal(err)
	}
	for i, f := range files {
		want := shellMode(t, f, odd[i%len(odd)])
		if got := modeOf(t, filepath.Join(o.ClaudeDir, f.name)); got != want {
			t.Errorf("%s (was %o): mode %o, install.sh gives %o", f.name, odd[i%len(odd)], got, want)
		}
	}
	if got := modeOf(t, settings); got != 0o664 {
		t.Errorf("settings.json mode %o, want its existing 664", got)
	}
	baks, _ := filepath.Glob(settings + ".bak-*")
	if len(baks) != 1 {
		t.Fatalf("backups: %v", baks)
	}
	if got := modeOf(t, baks[0]); got != 0o664 {
		t.Errorf("backup mode %o, want the original's 664", got)
	}
}
