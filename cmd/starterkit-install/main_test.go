package main

import (
	"bytes"
	"errors"
	"strings"
	"testing"

	"github.com/MatLomax/claude-starterkit/internal/plugins"
)

func windowsPlatform() plugins.Platform {
	return plugins.Platform{
		Windows: true, Home: `C:\Users\u`, ClaudeDir: `C:\Users\u\.claude`,
		Getenv:   func(string) string { return "" },
		LookPath: func(string) (string, error) { return "", errors.New("not found") },
	}
}

// Naming a plugin with no installer on this platform must not stop the core install: decide
// accepts it, and installPlugins reports it as a failure without running anything.
func TestUnavailablePluginIsReportedNotFatal(t *testing.T) {
	plat := windowsPlatform()
	opt := options{plugins: []string{"ripwire"}, pluginsSet: true}
	var out bytes.Buffer
	ch, err := decide(opt, plat, false, &out)
	if err != nil {
		t.Fatalf("decide refused an unavailable plugin: %v", err)
	}
	if !ch.worklog || len(ch.plugins) != 1 {
		t.Fatalf("decide = %+v", ch)
	}
	var stdout, stderr bytes.Buffer
	if failed := installPlugins(ch.plugins, opt, plat, false, &stdout, &stderr); !failed {
		t.Fatal("an unavailable plugin was not reported as failed")
	}
	if !strings.Contains(stderr.String(), "no official installer") || !strings.Contains(stderr.String(), "/releases") {
		t.Fatalf("report = %q", stderr.String())
	}
	if strings.Contains(stdout.String(), "installing") {
		t.Fatal("tried to run an installer that does not exist on this platform")
	}
}

// When the list is offered (no --plugins), an unavailable plugin is named with its manual link.
func TestUnavailablePluginIsListedWithLink(t *testing.T) {
	var out bytes.Buffer
	if _, err := decide(options{}, windowsPlatform(), false, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "ripwire has no official installer") || !strings.Contains(out.String(), "/releases") {
		t.Fatalf("out = %q", out.String())
	}
}

// The project-memory add-on is off unless chosen, by flag or environment, even where worklog
// defaults on.
func TestProjectMemoryDefaultsOff(t *testing.T) {
	var out bytes.Buffer
	ch, err := decide(options{pluginsSet: true}, windowsPlatform(), false, &out)
	if err != nil {
		t.Fatal(err)
	}
	if ch.projectMemory || !ch.worklog {
		t.Fatalf("defaults = %+v, want worklog on and project memory off", ch)
	}
	ch, err = decide(options{pluginsSet: true, projectMemory: ptr(true)}, windowsPlatform(), false, &out)
	if err != nil {
		t.Fatal(err)
	}
	if !ch.projectMemory {
		t.Fatal("--with-project-memory did not select the add-on")
	}
}

func TestFlagErrors(t *testing.T) {
	for _, args := range [][]string{
		{"--with-worklog", "--no-worklog"},
		{"--with-project-memory", "--no-project-memory"},
		{"--plugins=ripwire", "--no-plugins"},
		{"--plugins=nope"},
		{"stray"},
	} {
		var stdout, stderr bytes.Buffer
		if code := run(args, &stdout, &stderr); code != 2 {
			t.Errorf("%v: exit %d, want 2 (%s)", args, code, stderr.String())
		}
	}
}
