// Command starterkit-install installs the Claude Code starterkit (ruleset, guardrail hooks,
// statusline, settings defaults) into a Claude config directory, then offers the recommended
// plugins, each installed by its own official installer.
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/charmbracelet/huh"
	"golang.org/x/term"

	starterkit "github.com/MatLomax/claude-starterkit"
	"github.com/MatLomax/claude-starterkit/internal/install"
	"github.com/MatLomax/claude-starterkit/internal/plugins"
)

// formOut is the terminal the prompts draw on.
var formOut *os.File

// version is set at release build time (-ldflags "-X main.version=X.Y.Z").
var version = "dev"

const usage = `Usage: starterkit-install [flags]

Installs the Claude Code ruleset + guardrail hooks into your Claude config dir, then offers the
recommended plugins. Safe to re-run. Honours $CLAUDE_CONFIG_DIR, else ~/.claude.

The worklog task-log add-on is offered by a prompt that defaults to yes.
  --no-worklog        skip the worklog add-on (no prompt)
  --with-worklog      install it without prompting
  (env STARTERKIT_WORKLOG=0 skips it, =1 installs it; non-interactive runs default to install)

The project-memory add-on keeps each git repo's auto memory in <repo>/.claude/memory/ (excluded
from git), so every path you open the repo from shares it. Offered by a prompt that defaults to no.
  --with-project-memory   install it without prompting
  --no-project-memory     skip it (no prompt)
  (env STARTERKIT_PROJECT_MEMORY=1 installs it, =0 skips it; non-interactive runs default to skip)

Recommended plugins are offered in a multiselect with nothing ticked; each is installed by its own
official installer. Recommended: %s.
  --plugins=LIST      install these plugins without prompting (comma-separated)
  --no-plugins        install no plugins (no prompt)
  --plugin-hooks      also run each installed plugin's follow-up steps (e.g. ripwire's Claude Code
                      hooks) without prompting
  (env STARTERKIT_PLUGINS=LIST|none, STARTERKIT_PLUGIN_HOOKS=1; non-interactive runs install only
  the plugins they name, and run follow-ups only with --plugin-hooks)

  --version           print the version
`

type options struct {
	worklog       *bool
	projectMemory *bool
	plugins       []string
	pluginsSet    bool
	pluginHooks   bool
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("starterkit-install", flag.ContinueOnError)
	fs.SetOutput(stderr)
	fs.Usage = func() { fmt.Fprintf(stderr, usage, strings.Join(plugins.IDs(), ", ")) }
	withWorklog := fs.Bool("with-worklog", false, "")
	noWorklog := fs.Bool("no-worklog", false, "")
	withProjectMemory := fs.Bool("with-project-memory", false, "")
	noProjectMemory := fs.Bool("no-project-memory", false, "")
	pluginList := fs.String("plugins", "", "")
	noPlugins := fs.Bool("no-plugins", false, "")
	pluginHooks := fs.Bool("plugin-hooks", false, "")
	showVersion := fs.Bool("version", false, "")
	if err := fs.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if *showVersion {
		fmt.Fprintln(stdout, "starterkit-install", version)
		return 0
	}
	if fs.NArg() > 0 {
		fmt.Fprintf(stderr, "unexpected argument %q (see --help)\n", fs.Arg(0))
		return 2
	}
	set := map[string]bool{}
	fs.Visit(func(f *flag.Flag) { set[f.Name] = true })

	var opt options
	switch {
	case *withWorklog && *noWorklog:
		fmt.Fprintln(stderr, "--with-worklog and --no-worklog are mutually exclusive")
		return 2
	case *withWorklog:
		opt.worklog = ptr(true)
	case *noWorklog:
		opt.worklog = ptr(false)
	case os.Getenv("STARTERKIT_WORKLOG") != "":
		opt.worklog = ptr(os.Getenv("STARTERKIT_WORKLOG") == "1")
	}

	switch {
	case *withProjectMemory && *noProjectMemory:
		fmt.Fprintln(stderr, "--with-project-memory and --no-project-memory are mutually exclusive")
		return 2
	case *withProjectMemory:
		opt.projectMemory = ptr(true)
	case *noProjectMemory:
		opt.projectMemory = ptr(false)
	case os.Getenv("STARTERKIT_PROJECT_MEMORY") != "":
		opt.projectMemory = ptr(os.Getenv("STARTERKIT_PROJECT_MEMORY") == "1")
	}

	switch {
	case set["plugins"] && *noPlugins:
		fmt.Fprintln(stderr, "--plugins and --no-plugins are mutually exclusive")
		return 2
	case *noPlugins:
		opt.pluginsSet = true
	case set["plugins"]:
		ids, err := plugins.ParseList(*pluginList)
		if err != nil {
			fmt.Fprintln(stderr, err)
			return 2
		}
		opt.plugins, opt.pluginsSet = ids, true
	case os.Getenv("STARTERKIT_PLUGINS") != "":
		ids, err := plugins.ParseList(os.Getenv("STARTERKIT_PLUGINS"))
		if err != nil {
			fmt.Fprintln(stderr, "STARTERKIT_PLUGINS:", err)
			return 2
		}
		opt.plugins, opt.pluginsSet = ids, true
	}
	opt.pluginHooks = *pluginHooks || os.Getenv("STARTERKIT_PLUGIN_HOOKS") == "1"

	return installAll(opt, stdout, stderr)
}

func installAll(opt options, stdout, stderr io.Writer) int {
	// Prompt whenever there is a keyboard (stdin is a terminal), as the old install.sh did. The
	// prompts draw on stdout, or on stderr when only stdout is redirected (`| tee install.log`).
	formOut = os.Stdout
	if !term.IsTerminal(int(os.Stdout.Fd())) {
		formOut = os.Stderr
	}
	interactive := term.IsTerminal(int(os.Stdin.Fd())) && term.IsTerminal(int(formOut.Fd()))
	windows := runtime.GOOS == "windows"

	home, err := os.UserHomeDir()
	if err != nil {
		fmt.Fprintln(stderr, "cannot find your home directory:", err)
		return 1
	}
	claudeDir := os.Getenv("CLAUDE_CONFIG_DIR")
	if claudeDir == "" {
		claudeDir = filepath.Join(home, ".claude")
	}
	plat := plugins.Platform{
		Windows: windows, Home: home, ClaudeDir: claudeDir,
		Getenv: os.Getenv, LookPath: exec.LookPath,
	}

	inst := install.Options{
		ClaudeDir: claudeDir,
		Payload:   starterkit.Payload,
		Windows:   windows,
		PyCmd:     "python3",
		Out:       stdout,
		Now:       time.Now,
	}
	if windows {
		py, err := install.FindPython()
		if err != nil {
			fmt.Fprintln(stderr, err)
			return 1
		}
		inst.PyCmd = py
		inst.PsExe = install.FindPowerShell()
		fmt.Fprintln(stdout, "using Python command:", py)
	}

	// Ask everything up front, so the install then runs without stopping.
	ch, err := decide(opt, plat, interactive, stdout)
	if err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			fmt.Fprintln(stderr, "Cancelled — nothing was installed.")
			return 130
		}
		fmt.Fprintln(stderr, err)
		return 1
	}
	inst.Worklog = ch.worklog
	inst.ProjectMemory = ch.projectMemory

	if err := install.Files(inst); err != nil {
		fmt.Fprintln(stderr, "install failed:", err)
		return 1
	}
	if err := install.Settings(inst); err != nil {
		fmt.Fprintln(stderr, "settings.json merge failed:", err)
		return 1
	}

	failed := installPlugins(ch.plugins, opt, plat, interactive, stdout, stderr)

	fmt.Fprintln(stdout)
	if failed {
		fmt.Fprintln(stdout, "The starterkit is installed, but a plugin step failed (see above).")
	}
	fmt.Fprintln(stdout, "Done. Restart Claude Code (or start a fresh session) for the hooks to take effect.")
	if failed {
		return 1
	}
	return 0
}

// choices is what decide settled: the add-ons and the plugins to install.
type choices struct {
	worklog       bool
	projectMemory bool
	plugins       []string
}

// decide settles the add-ons and the plugin selection, prompting only for what flags and the
// environment left open, and only when there is a terminal.
func decide(opt options, plat plugins.Platform, interactive bool, stdout io.Writer) (choices, error) {
	ch := choices{worklog: true, plugins: opt.plugins}
	if opt.worklog != nil {
		ch.worklog = *opt.worklog
	}
	if opt.projectMemory != nil {
		ch.projectMemory = *opt.projectMemory
	}

	var available []plugins.Plugin
	for _, pl := range plugins.Recommended {
		if pl.Available(plat) {
			available = append(available, pl)
		} else if !opt.pluginsSet {
			fmt.Fprintf(stdout, "recommended plugin %s has no official installer on this platform; see %s\n", pl.ID, pl.Manual)
		}
	}

	if !interactive {
		return ch, nil
	}

	var fields []huh.Field
	if opt.worklog == nil {
		fields = append(fields, huh.NewConfirm().
			Title("Install the worklog task-log add-on?").
			Description("Points the ruleset's task-tracking wording at worklog (needs the worklog MCP tool).").
			Affirmative("Yes").Negative("No").
			Value(&ch.worklog))
	}
	if opt.projectMemory == nil {
		fields = append(fields, huh.NewConfirm().
			Title("Keep each git repo's auto memory inside the repo?").
			Description("Links Claude Code's per-path memory directory to <repo>/.claude/memory/ (excluded from git), so every path you open the repo from shares one memory.").
			Affirmative("Yes").Negative("No").
			Value(&ch.projectMemory))
	}
	if !opt.pluginsSet && len(available) > 0 {
		var opts []huh.Option[string]
		for _, pl := range available {
			label := pl.ID + " — " + pl.Description
			if v := pl.Installed(plat); v != "" {
				label += " (installed: " + v + ")"
			}
			opts = append(opts, huh.NewOption(label, pl.ID))
		}
		fields = append(fields, huh.NewMultiSelect[string]().
			Title("Recommended plugins").
			Description("Nothing is ticked by default. Each runs its own official installer; re-running one updates it.").
			Options(opts...).
			Value(&ch.plugins))
	}
	if len(fields) > 0 {
		if err := huh.NewForm(huh.NewGroup(fields...)).WithOutput(formOut).Run(); err != nil {
			return choices{}, err
		}
	}
	return ch, nil
}

// installPlugins runs each selected plugin's official installer and, on success, its follow-up
// steps. It reports whether any step failed; a failure never stops the other plugins.
func installPlugins(ids []string, opt options, plat plugins.Platform, interactive bool, stdout, stderr io.Writer) bool {
	failed := false
	for _, id := range ids {
		pl, _ := plugins.Lookup(id)
		if !pl.Available(plat) {
			fmt.Fprintf(stderr, "\n%s: no official installer on this platform, so it was not installed; see %s\n", pl.ID, pl.Manual)
			failed = true
			continue
		}
		fmt.Fprintf(stdout, "\n==> installing %s with its official installer\n", pl.ID)
		cmd := exec.Command("bash", "-c", pl.Installer(plat))
		cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, stdout, stderr
		cmd.Env = os.Environ()
		if !interactive {
			cmd.Env = append(cmd.Env, pl.NonInteractiveEnv...)
		}
		if err := cmd.Run(); err != nil {
			fmt.Fprintf(stderr, "%s: its installer failed (%v)\n", pl.ID, err)
			failed = true
			continue
		}
		// The installer's exit status is not enough: the plugin must actually be there now.
		v := pl.Installed(plat)
		if v == "" {
			fmt.Fprintf(stderr, "%s: its installer reported success, but %s is not installed\n", pl.ID, pl.ID)
			failed = true
			continue
		}
		if v == "installed" {
			fmt.Fprintf(stdout, "%s: installed\n", pl.ID)
		} else {
			fmt.Fprintf(stdout, "%s: installed (%s)\n", pl.ID, v)
		}

		for _, fu := range pl.FollowUps {
			ok, why := fu.Available(plat)
			run := opt.pluginHooks
			if interactive && !opt.pluginHooks {
				desc := ""
				if !ok {
					desc = "Note: " + why + "."
				}
				run = ok
				err := huh.NewForm(huh.NewGroup(huh.NewConfirm().
					Title(fu.Question).Description(desc).
					Affirmative("Yes").Negative("No").
					Value(&run))).WithOutput(formOut).Run()
				if err != nil {
					fmt.Fprintf(stdout, "%s: skipped %s step\n", pl.ID, fu.ID)
					continue
				}
			}
			if !run {
				fmt.Fprintf(stdout, "%s: skipped %s step (later: %s)\n", pl.ID, fu.ID, strings.Join(fu.Command(plat), " "))
				continue
			}
			if !ok && !interactive {
				fmt.Fprintf(stderr, "%s: cannot run %s step: %s\n", pl.ID, fu.ID, why)
				failed = true
				continue
			}
			argv := fu.Command(plat)
			c := exec.Command(argv[0], argv[1:]...)
			c.Stdin, c.Stdout, c.Stderr = os.Stdin, stdout, stderr
			if err := c.Run(); err != nil {
				fmt.Fprintf(stderr, "%s: %s step failed (%v)\n", pl.ID, fu.ID, err)
				failed = true
				continue
			}
			fmt.Fprintf(stdout, "%s: %s step done\n", pl.ID, fu.ID)
		}
	}
	return failed
}

func ptr[T any](v T) *T { return &v }
