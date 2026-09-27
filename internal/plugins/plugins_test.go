package plugins

import (
	"errors"
	"strings"
	"testing"
)

func TestParseList(t *testing.T) {
	for _, in := range []string{"", "none", "NONE", " "} {
		if ids, err := ParseList(in); err != nil || ids != nil {
			t.Errorf("ParseList(%q) = %v, %v", in, ids, err)
		}
	}
	ids, err := ParseList(" Ripwire , ripwire,")
	if err != nil || len(ids) != 1 || ids[0] != "ripwire" {
		t.Fatalf("got %v, %v", ids, err)
	}
	if _, err := ParseList("ripwire,nope"); err == nil || !strings.Contains(err.Error(), "ripwire") {
		t.Fatalf("unknown id error = %v", err)
	}
}

func platform(windows bool, env map[string]string, have map[string]bool) Platform {
	return Platform{
		Windows: windows, Home: "/home/u", ClaudeDir: "/home/u/.claude",
		Getenv: func(k string) string { return env[k] },
		LookPath: func(n string) (string, error) {
			if have[n] {
				return "/usr/bin/" + n, nil
			}
			return "", errors.New("not found")
		},
	}
}

func TestRipwire(t *testing.T) {
	rw, ok := Lookup("ripwire")
	if !ok {
		t.Fatal("ripwire is not recommended")
	}
	if rw.Available(platform(true, nil, nil)) {
		t.Error("ripwire offered on Windows, which has no official installer")
	}
	cmd := rw.Installer(platform(false, nil, nil))
	if !strings.Contains(cmd, "RIPWIRE_REPO=redhat-et/ripwire") || !strings.Contains(cmd, "raw.githubusercontent.com/redhat-et/ripwire/main/scripts/install.sh") {
		t.Errorf("not ripwire's documented installer: %s", cmd)
	}

	hook := rw.FollowUps[0]
	if ok, why := hook.Available(platform(false, nil, nil)); ok || !strings.Contains(why, "jq") {
		t.Errorf("hook step without jq: %v %q", ok, why)
	}
	if ok, _ := hook.Available(platform(false, nil, map[string]bool{"jq": true})); !ok {
		t.Error("hook step unavailable with jq present")
	}
	if got := strings.Join(hook.Command(platform(false, nil, nil)), " "); got != "bash /home/u/.local/share/ripwire/skills/install.sh --hook" {
		t.Errorf("hook command = %s", got)
	}
	got := strings.Join(hook.Command(platform(false, map[string]string{"RIPWIRE_INSTALL_PREFIX": "/opt/rw"}, nil)), " ")
	if got != "bash /opt/rw/share/ripwire/skills/install.sh --hook" {
		t.Errorf("hook command with prefix = %s", got)
	}
}
