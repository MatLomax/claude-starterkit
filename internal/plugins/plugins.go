// Package plugins is the starterkit's list of recommended plugins. None is vendored: installing
// one runs that plugin's own official installer, and a plugin may offer follow-up steps once its
// install succeeds.
package plugins

import (
	"fmt"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strings"
)

// Plugin is one recommended plugin.
type Plugin struct {
	ID          string
	Description string
	Homepage    string
	// Manual is where to get the plugin by hand where it has no official installer.
	Manual string
	// Installer is the official install command, run through bash; "" means the plugin has no
	// official installer on this platform.
	Installer func(p Platform) string
	// NonInteractiveEnv is extra environment for the installer when there is no terminal to
	// answer its own prompts on.
	NonInteractiveEnv []string
	// Installed reports the installed version, or "" when the plugin is not installed.
	Installed func(p Platform) string
	FollowUps []FollowUp
}

// FollowUp is an optional step offered after the plugin installs.
type FollowUp struct {
	ID       string // flag-facing name, e.g. "hook"
	Question string
	// Available reports whether the step can run now and, when it cannot, why (shown to the user).
	Available func(p Platform) (bool, string)
	Command   func(p Platform) []string
}

// Platform is what the plugin definitions need to know about the machine.
type Platform struct {
	Windows   bool
	Home      string
	ClaudeDir string
	Getenv    func(string) string
	LookPath  func(string) (string, error)
}

// Available reports whether the plugin has an official installer on this platform.
func (pl Plugin) Available(p Platform) bool { return pl.Installer(p) != "" }

const (
	ripwireRepo       = "redhat-et/ripwire"
	ripwireInstallURL = "https://raw.githubusercontent.com/" + ripwireRepo + "/main/scripts/install.sh"
)

// Recommended is every recommended plugin, in the order they are offered.
var Recommended = []Plugin{
	{
		ID:          "ripwire",
		Description: "deterministic codebase maps for coding agents (CLI + skills)",
		Homepage:    "https://github.com/" + ripwireRepo,
		Manual:      "https://github.com/" + ripwireRepo + "/releases",
		// ripwire's documented quick install (INSTALL.md), with the script fetched first so a failed
		// or empty download fails the install instead of running an empty script. It has no Windows
		// installer: Windows gets a release zip and a Git Bash skills script, and the installer
		// script recognises only Darwin and Linux.
		Installer: func(p Platform) string {
			if p.Windows {
				return ""
			}
			return `url=` + ripwireInstallURL + `
script=$(curl -fsSL "$url") || { echo "ripwire: could not download its installer from $url" >&2; exit 1; }
if [ -z "$script" ]; then echo "ripwire: its installer at $url is empty" >&2; exit 1; fi
RIPWIRE_REPO=` + ripwireRepo + ` bash -c "$script"`
		},
		// Without a terminal ripwire's installer aborts unless its confirmation is pre-answered.
		NonInteractiveEnv: []string{"RIPWIRE_INSTALL_YES=1"},
		Installed: func(p Platform) string {
			bin, err := p.LookPath("ripwire")
			if err != nil {
				cand := filepath.Join(ripwirePrefix(p), "bin", "ripwire")
				if _, statErr := os.Stat(cand); statErr != nil {
					return ""
				}
				bin = cand
			}
			out, err := exec.Command(bin, "--version").Output()
			if err != nil {
				return "installed"
			}
			fields := strings.Fields(string(out))
			if len(fields) >= 2 {
				return fields[1]
			}
			return "installed"
		},
		FollowUps: []FollowUp{{
			ID:       "hook",
			Question: "Register ripwire's Claude Code hooks (a session-start primer, a prompt router, and a tool-call recorder that never blocks)?",
			Available: func(p Platform) (bool, string) {
				if _, err := p.LookPath("jq"); err != nil {
					return false, "ripwire's hooks need jq, which is not on PATH"
				}
				return true, ""
			},
			Command: func(p Platform) []string {
				return []string{"bash", path.Join(filepath.ToSlash(ripwirePrefix(p)), "share", "ripwire", "skills", "install.sh"), "--hook"}
			},
		}},
	},
}

// ripwirePrefix is where ripwire's installer puts it: $RIPWIRE_INSTALL_PREFIX, else ~/.local.
func ripwirePrefix(p Platform) string {
	if v := p.Getenv("RIPWIRE_INSTALL_PREFIX"); v != "" {
		return v
	}
	return filepath.Join(p.Home, ".local")
}

// Lookup returns the recommended plugin with this id.
func Lookup(id string) (Plugin, bool) {
	for _, pl := range Recommended {
		if pl.ID == id {
			return pl, true
		}
	}
	return Plugin{}, false
}

// ParseList parses a comma-separated plugin list ("ripwire,other"); "none" and "" mean no plugins.
// An unknown id is an error naming the known ones.
func ParseList(s string) ([]string, error) {
	s = strings.TrimSpace(s)
	if s == "" || strings.EqualFold(s, "none") {
		return nil, nil
	}
	var ids []string
	seen := map[string]bool{}
	for _, part := range strings.Split(s, ",") {
		id := strings.ToLower(strings.TrimSpace(part))
		if id == "" || seen[id] {
			continue
		}
		if _, ok := Lookup(id); !ok {
			return nil, fmt.Errorf("unknown plugin %q (recommended plugins: %s)", id, strings.Join(IDs(), ", "))
		}
		seen[id] = true
		ids = append(ids, id)
	}
	return ids, nil
}

// IDs lists every recommended plugin id.
func IDs() []string {
	ids := make([]string, len(Recommended))
	for i, pl := range Recommended {
		ids[i] = pl.ID
	}
	return ids
}
