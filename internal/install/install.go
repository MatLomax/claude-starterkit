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
	"unicode"
)

// Options describes one install run.
type Options struct {
	ClaudeDir     string    // the Claude config directory ($CLAUDE_CONFIG_DIR, else ~/.claude)
	Payload       fs.FS     // the embedded starterkit files
	Worklog       bool      // install and import the worklog add-on
	ProjectMemory bool      // wire the project-memory hook (a project's auto memory in <project>/.claude/memory/)
	Windows       bool      // lay down the Windows variants (statusline .ps1, Python launcher command)
	PyCmd         string    // the command hooks run under ("python3" on Unix; detected on Windows)
	PsExe         string    // Windows only: "pwsh" or "powershell", for the statusline command
	Out           io.Writer // progress lines
	Now           func() time.Time
}

const (
	projectMemoryAddOn = "project-memory"

	ruleset      = "CLAUDE.starterkit.md"
	worklogAddOn = "CLAUDE.starterkit-worklog.md"
	reviewRules  = "review-rules.md"
)

// Files installs the ruleset (and the parts it imports), the optional worklog add-on, the
// hook scripts, the statusline script and the opt-in review rules, and makes sure ~/.claude/CLAUDE.md
// imports what should be imported. The user's CLAUDE.md is never overwritten: only a missing
// import line is appended.
func Files(o Options) error {
	if err := os.MkdirAll(filepath.Join(o.ClaudeDir, "hooks"), 0o777); err != nil {
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
		if err := copyOut(o, f, 0o644, false); err != nil {
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
		if err := copyOut(o, worklogAddOn, 0o644, false); err != nil {
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
		if err := copyOut(o, h, 0o755, true); err != nil {
			return err
		}
	}
	fmt.Fprintf(o.Out, "installed %d hook scripts\n", len(hooks))

	if o.Windows {
		if err := copyOut(o, "statusline-command.ps1", 0o644, false); err != nil {
			return err
		}
		fmt.Fprintln(o.Out, "installed statusline-command.ps1")
	} else {
		if err := copyOut(o, "statusline-command.sh", 0o644, true); err != nil {
			return err
		}
		fmt.Fprintln(o.Out, "installed statusline-command.sh")
	}

	// Installed, never imported: the review rules cost tokens every session, so they apply only
	// where a CLAUDE.md imports @~/.claude/review-rules.md.
	if err := copyOut(o, reviewRules, 0o644, false); err != nil {
		return err
	}
	fmt.Fprintln(o.Out, "installed review-rules.md (opt-in: import @~/.claude/review-rules.md to enable)")
	return nil
}

// copyOut writes the payload file name to the same path under the config dir, with the modes a
// plain cp gives: a new file gets srcMode (the file's mode in the repo) less the umask, and an
// existing file keeps its mode. With exec set it then gets the execute bits chmod +x adds, which
// the umask also limits. On Windows a new file gets exec's mode (0755 or 0644) and nothing is
// chmodded.
func copyOut(o Options, name string, srcMode os.FileMode, exec bool) error {
	data, err := fs.ReadFile(o.Payload, name)
	if err != nil {
		return err
	}
	target := filepath.Join(o.ClaudeDir, filepath.FromSlash(name))
	if o.Windows {
		mode := os.FileMode(0o644)
		if exec {
			mode = 0o755
		}
		return os.WriteFile(target, data, mode)
	}
	if err := os.WriteFile(target, data, srcMode); err != nil {
		return err
	}
	if !exec {
		return nil
	}
	st, err := os.Stat(target)
	if err != nil {
		return err
	}
	keep := st.Mode() & (os.ModePerm | os.ModeSetuid | os.ModeSetgid | os.ModeSticky)
	return os.Chmod(target, keep|os.FileMode(0o111&^umask()))
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
	f, err := os.OpenFile(claudeMD, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o666)
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

// wants reports whether the add-on named addOn is selected; "" names the always-installed core.
func (o Options) wants(addOn string) bool {
	switch addOn {
	case "":
		return true
	case projectMemoryAddOn:
		return o.ProjectMemory
	}
	return false
}

// hooksDir is the hooks directory as it appears inside hook commands: forward slashes on Windows,
// where the command runs through a shell that treats backslashes as escapes.
func (o Options) hooksDir() string {
	if o.Windows {
		return strings.ReplaceAll(filepath.Join(o.ClaudeDir, "hooks"), `\`, "/")
	}
	return path.Join(filepath.ToSlash(o.ClaudeDir), "hooks")
}

// hookCommand is the settings.json command that runs the hook script, its path quoted when needed.
func (o Options) hookCommand(script string) string {
	return o.PyCmd + " " + shellArg(o.hooksDir()+"/"+script, o.Windows)
}

// legacyHookCommand is the command earlier installs wrote for the hook script: the path never
// quoted. It differs from hookCommand only for a path that needs quoting.
func (o Options) legacyHookCommand(script string) string {
	return o.PyCmd + " " + o.hooksDir() + "/" + script
}

// StatuslineCommand is the statusLine command for this platform.
func (o Options) StatuslineCommand() string {
	if o.Windows {
		p := strings.ReplaceAll(filepath.Join(o.ClaudeDir, "statusline-command.ps1"), `\`, "/")
		return fmt.Sprintf(`%s -NoProfile -File "%s"`, o.PsExe, p)
	}
	return "bash " + shellArg(o.unixStatuslinePath(), false)
}

// legacyStatuslineCommand is the statusLine command earlier installs wrote: on Unix the path never
// quoted. On Windows it was always quoted, so it equals StatuslineCommand.
func (o Options) legacyStatuslineCommand() string {
	if o.Windows {
		return o.StatuslineCommand()
	}
	return "bash " + o.unixStatuslinePath()
}

func (o Options) unixStatuslinePath() string {
	return path.Join(filepath.ToSlash(o.ClaudeDir), "statusline-command.sh")
}

// shellArg returns p as one word for the shell a command runs through: sh -c on Unix, Git Bash on
// Windows. A path of only letters, digits and characters no shell treats specially is returned as
// is, so commands for ordinary paths are exactly what earlier installs wrote. Any other path is
// double-quoted, with the characters still special inside double quotes (" \ $ `) escaped by a
// backslash. The double quotes also hold the path together under PowerShell, which Claude Code runs
// hook commands through on Windows when Git Bash is missing; a $ or ` in the path is escaped for
// Git Bash, which PowerShell reads differently.
func shellArg(p string, windows bool) string {
	plain := p != "" && p[0] != '~' && strings.IndexFunc(p, func(r rune) bool {
		// A tilde is literal except at the start of a word (a Windows short name such as RUNNER~1).
		if unicode.IsLetter(r) || unicode.IsDigit(r) || strings.ContainsRune("/._-:+=@%~", r) {
			return false
		}
		// A comma separates array elements in a PowerShell argument; sh reads it literally.
		return windows || r != ','
	}) < 0
	if plain {
		return p
	}
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range p {
		if strings.ContainsRune("\"\\$`", r) {
			b.WriteByte('\\')
		}
		b.WriteRune(r)
	}
	b.WriteByte('"')
	return b.String()
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
