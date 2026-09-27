// Package install lays the starterkit payload into a Claude config directory and merges its
// settings into settings.json without clobbering anything the user has set.
package install

import (
	"bytes"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// Options describes one install run.
type Options struct {
	ClaudeDir string    // the Claude config directory ($CLAUDE_CONFIG_DIR, else ~/.claude)
	Payload   fs.FS     // the embedded starterkit files
	Worklog   bool      // install and import the worklog add-on
	Windows   bool      // lay down the Windows variants (statusline .ps1, Python launcher command)
	PyCmd     string    // the command hooks run under ("python3" on Unix; detected on Windows)
	PsExe     string    // Windows only: "pwsh" or "powershell", for the statusline command
	Out       io.Writer // progress lines
	Now       func() time.Time
}

const (
	ruleset      = "CLAUDE.starterkit.md"
	worklogAddOn = "CLAUDE.starterkit-worklog.md"
	reviewRules  = "review-rules.md"
)

// Files installs the ruleset (and the parts it imports), the optional worklog add-on, the
// hook scripts, the statusline script and the opt-in review rules, and makes sure ~/.claude/CLAUDE.md
// imports what should be imported. The user's CLAUDE.md is never overwritten: only a missing
// import line is appended.
func Files(o Options) error {
	if err := os.MkdirAll(filepath.Join(o.ClaudeDir, "hooks"), 0o755); err != nil {
		return err
	}

	// The ruleset and the parts it imports itself (every CLAUDE.starterkit*.md except the optional
	// worklog add-on). Only the ruleset is imported from CLAUDE.md.
	parts, err := fs.Glob(o.Payload, "CLAUDE.starterkit*.md")
	if err != nil {
		return err
	}
	sort.Strings(parts)
	var names []string
	for _, f := range parts {
		if f == worklogAddOn {
			continue
		}
		if err := copyOut(o, f, f, 0o644); err != nil {
			return err
		}
		if f != ruleset {
			names = append(names, f)
		}
	}
	if len(names) > 0 {
		fmt.Fprintf(o.Out, "installed %s + %s (imported by the ruleset)\n", ruleset, strings.Join(names, ", "))
	} else {
		fmt.Fprintf(o.Out, "installed %s\n", ruleset)
	}
	claudeMD := filepath.Join(o.ClaudeDir, "CLAUDE.md")
	if err := ensureImport(o, claudeMD, "@./"+ruleset, ruleset, ""); err != nil {
		return err
	}

	if o.Worklog {
		if err := copyOut(o, worklogAddOn, worklogAddOn, 0o644); err != nil {
			return err
		}
		if err := ensureImport(o, claudeMD, "@./"+worklogAddOn, worklogAddOn, " (worklog add-on)"); err != nil {
			return err
		}
	} else {
		fmt.Fprintln(o.Out, "skipping worklog add-on (--no-worklog / STARTERKIT_WORKLOG=0)")
	}

	hooks, err := fs.Glob(o.Payload, "hooks/*.py")
	if err != nil {
		return err
	}
	sort.Strings(hooks)
	for _, h := range hooks {
		if err := copyOut(o, h, h, 0o755); err != nil {
			return err
		}
	}
	fmt.Fprintf(o.Out, "installed %d hook scripts\n", len(hooks))

	if o.Windows {
		if err := copyOut(o, "statusline-command.ps1", "statusline-command.ps1", 0o644); err != nil {
			return err
		}
		fmt.Fprintln(o.Out, "installed statusline-command.ps1")
	} else {
		if err := copyOut(o, "statusline-command.sh", "statusline-command.sh", 0o755); err != nil {
			return err
		}
		fmt.Fprintln(o.Out, "installed statusline-command.sh")
	}

	// Installed, never imported: the review rules cost tokens every session, so they apply only
	// where a CLAUDE.md imports @~/.claude/review-rules.md.
	if err := copyOut(o, reviewRules, reviewRules, 0o644); err != nil {
		return err
	}
	fmt.Fprintln(o.Out, "installed review-rules.md (opt-in: import @~/.claude/review-rules.md to enable)")
	return nil
}

// copyOut writes the payload file src to dst (relative to the config dir) with the given mode.
func copyOut(o Options, src, dst string, mode os.FileMode) error {
	data, err := fs.ReadFile(o.Payload, src)
	if err != nil {
		return err
	}
	target := filepath.Join(o.ClaudeDir, filepath.FromSlash(dst))
	if err := os.WriteFile(target, data, mode); err != nil {
		return err
	}
	// WriteFile keeps an existing file's mode; set it so a re-run repairs it.
	if !o.Windows {
		return os.Chmod(target, mode)
	}
	return nil
}

// ensureImport appends line to CLAUDE.md unless it is already there, separated from any existing
// content by a newline.
func ensureImport(o Options, claudeMD, line, name, note string) error {
	existing, err := os.ReadFile(claudeMD)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	if bytes.Contains(existing, []byte(line)) {
		fmt.Fprintf(o.Out, "CLAUDE.md already imports %s\n", name)
		return nil
	}
	f, err := os.OpenFile(claudeMD, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	var add string
	if len(existing) > 0 {
		add = "\n"
	}
	add += line + "\n"
	if _, err := f.WriteString(add); err != nil {
		return err
	}
	fmt.Fprintf(o.Out, "appended '%s' to CLAUDE.md%s\n", line, note)
	return nil
}

// hooksDir is the hooks directory as it appears inside hook commands: forward slashes on Windows,
// where the command runs through a shell that treats backslashes as escapes.
func (o Options) hooksDir() string {
	d := filepath.Join(o.ClaudeDir, "hooks")
	if o.Windows {
		return strings.ReplaceAll(d, `\`, "/")
	}
	return d
}

// StatuslineCommand is the statusLine command for this platform.
func (o Options) StatuslineCommand() string {
	if o.Windows {
		p := strings.ReplaceAll(filepath.Join(o.ClaudeDir, "statusline-command.ps1"), `\`, "/")
		return fmt.Sprintf(`%s -NoProfile -File "%s"`, o.PsExe, p)
	}
	return "bash " + path.Join(filepath.ToSlash(o.ClaudeDir), "statusline-command.sh")
}

// FindPython returns the first Python command that runs, trying the Windows launcher first
// (Windows rarely has a bare python3).
func FindPython() (string, error) {
	for _, cand := range []string{"py -3", "python", "python3"} {
		parts := strings.Fields(cand)
		cmd := exec.Command(parts[0], append(parts[1:], "--version")...)
		if cmd.Run() == nil {
			return cand, nil
		}
	}
	return "", fmt.Errorf("no Python found on PATH (tried 'py -3', 'python', 'python3'). The hooks are Python scripts and need it. Install Python 3 from python.org or the Microsoft Store, then re-run")
}

// FindPowerShell returns "pwsh" when PowerShell 7+ is on PATH, else "powershell".
func FindPowerShell() string {
	if _, err := exec.LookPath("pwsh"); err == nil {
		return "pwsh"
	}
	return "powershell"
}
