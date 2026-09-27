//go:build unix

package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeCurl puts a curl on PATH that runs body (a sh script) instead of fetching anything, and
// isolates HOME, the config dir and PATH so no real ripwire is found. It returns the fake home.
func fakeCurl(t *testing.T, body string) string {
	t.Helper()
	bin := t.TempDir()
	if err := os.WriteFile(filepath.Join(bin, "curl"), []byte("#!/bin/sh\n"+body+"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	home := t.TempDir()
	t.Setenv("PATH", bin+":/usr/bin:/bin")
	t.Setenv("HOME", home)
	t.Setenv("CLAUDE_CONFIG_DIR", filepath.Join(home, ".claude"))
	t.Setenv("RIPWIRE_INSTALL_PREFIX", "")
	t.Setenv("STARTERKIT_WORKLOG", "")
	t.Setenv("STARTERKIT_PLUGINS", "")
	t.Setenv("STARTERKIT_PLUGIN_HOOKS", "")
	// No terminal on stdin, so nothing prompts even when the tests run in one.
	null, err := os.Open(os.DevNull)
	if err != nil {
		t.Fatal(err)
	}
	stdin := os.Stdin
	os.Stdin = null
	t.Cleanup(func() { os.Stdin = stdin; null.Close() })
	return home
}

// installRipwire runs the installer the way a user does (--plugins=ripwire, no terminal), through
// the real command path: bash runs ripwire's install command, which calls curl from PATH.
func installRipwire(t *testing.T) (int, string, string) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := run([]string{"--no-worklog", "--plugins=ripwire"}, &stdout, &stderr)
	return code, stdout.String(), stderr.String()
}

func TestRipwireFailedDownloadFails(t *testing.T) {
	fakeCurl(t, `echo "curl: (22) The requested URL returned error: 404" >&2; exit 22`)
	code, stdout, stderr := installRipwire(t)
	if code == 0 {
		t.Fatalf("exit 0 after a failed download\nstdout: %s\nstderr: %s", stdout, stderr)
	}
	if !strings.Contains(stderr, "could not download its installer") || !strings.Contains(stderr, "its installer failed") {
		t.Errorf("stderr = %q", stderr)
	}
	if strings.Contains(stdout, "ripwire: installed") {
		t.Errorf("reported installed: %q", stdout)
	}
}

func TestRipwireEmptyDownloadFails(t *testing.T) {
	fakeCurl(t, `exit 0`)
	code, stdout, stderr := installRipwire(t)
	if code == 0 || !strings.Contains(stderr, "is empty") || strings.Contains(stdout, "ripwire: installed") {
		t.Fatalf("exit %d\nstdout: %s\nstderr: %s", code, stdout, stderr)
	}
}

func TestRipwireInstallerThatInstallsNothingFails(t *testing.T) {
	fakeCurl(t, `echo 'echo pretending to install; exit 0'`)
	code, stdout, stderr := installRipwire(t)
	if code == 0 {
		t.Fatalf("exit 0 with ripwire not installed\nstdout: %s\nstderr: %s", stdout, stderr)
	}
	if !strings.Contains(stdout, "pretending to install") {
		t.Errorf("the downloaded installer did not run: %q", stdout)
	}
	if !strings.Contains(stderr, "reported success, but ripwire is not installed") || strings.Contains(stdout, "ripwire: installed") {
		t.Errorf("stdout = %q\nstderr = %q", stdout, stderr)
	}
}

// A download that installs ripwire under ~/.local succeeds; the installer sees RIPWIRE_REPO and,
// with no terminal, RIPWIRE_INSTALL_YES=1.
func TestRipwireInstallSucceeds(t *testing.T) {
	home := fakeCurl(t, `cat <<'SCRIPT'
[ "$RIPWIRE_REPO" = redhat-et/ripwire ] || { echo "RIPWIRE_REPO=$RIPWIRE_REPO" >&2; exit 3; }
[ "$RIPWIRE_INSTALL_YES" = 1 ] || { echo "RIPWIRE_INSTALL_YES=$RIPWIRE_INSTALL_YES" >&2; exit 4; }
mkdir -p "$HOME/.local/bin"
printf '#!/bin/sh\necho "ripwire 9.9.9"\n' > "$HOME/.local/bin/ripwire"
chmod +x "$HOME/.local/bin/ripwire"
SCRIPT`)
	code, stdout, stderr := installRipwire(t)
	if code != 0 || !strings.Contains(stdout, "ripwire: installed (9.9.9)") {
		t.Fatalf("exit %d\nstdout: %s\nstderr: %s", code, stdout, stderr)
	}
	if _, err := os.Stat(filepath.Join(home, ".claude", "CLAUDE.starterkit.md")); err != nil {
		t.Errorf("starterkit not installed: %v", err)
	}
}
