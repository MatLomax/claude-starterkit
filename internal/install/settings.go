package install

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"sort"

	"github.com/MatLomax/claude-starterkit/internal/ojson"
)

// hook is one hook the starterkit wires into settings.json.
type hook struct {
	matcher string         // "" for no matcher
	script  string         // file name under hooks/
	extra   map[string]any // extra fields on the hook entry (e.g. asyncRewake)
	addOn   string         // "" for always; else the add-on that wires it (see Options.wants)
}

// hookEvent keeps the events in the order they are written into a fresh settings.json.
type hookEvent struct {
	event string
	hooks []hook
}

// Hooks is every hook the starterkit installs, by event.
var Hooks = []hookEvent{
	{"UserPromptSubmit", []hook{
		{script: "icon-reminder.py"},
		{script: "correction-primer.py"},
		{script: "commit-style-primer.py"},
		{script: "notification-guard.py"},
	}},
	{"PreToolUse", []hook{
		{matcher: "AskUserQuestion", script: "deny-askuserquestion.py"},
		{matcher: "Agent", script: "agent-guard.py"},
		{matcher: "Bash", script: "git-guard.py"},
		{matcher: "Bash|PowerShell", script: "sleep-guard.py"},
		{script: "spend-guard.py"},
		{matcher: "Write|Edit", script: "nul-guard.py"},
		{script: "notification-guard.py"},
	}},
	{"PostToolUse", []hook{
		{script: "notification-guard.py"},
	}},
	{"Stop", []hook{
		{script: "tie-break-guard.py"},
		{script: "notification-guard.py"},
	}},
	{"PreCompact", []hook{
		{script: "compact-snapshot.py"},
	}},
	{"SessionStart", []hook{
		{matcher: "compact", script: "compact-resume.py"},
		{script: "project-memory.py", addOn: projectMemoryAddOn},
	}},
	{"PostCompact", []hook{
		{matcher: "manual", script: "compact-continue.py", extra: map[string]any{"asyncRewake": true}},
	}},
	{"MessageDisplay", []hook{
		{script: "notification-guard.py"},
	}},
}

// Opinionated defaults that reinforce the guardrails (no artifacts, no AI co-author line,
// deterministic worktrees, less UI noise (no suggestions, no spinner tips), high effort, automatic
// compaction on, session transcripts kept instead of purged after 30 days). Each is set only when the user has not chosen a value.
func defaults() []struct {
	key string
	val any
} {
	worktree := ojson.NewObject()
	worktree.Set("baseRef", "fresh")
	return []struct {
		key string
		val any
	}{
		{"includeCoAuthoredBy", false},
		{"enableArtifact", false},
		{"askUserQuestionTimeout", "never"},
		{"worktree", worktree},
		{"feedbackDrafts", "off"},
		{"promptSuggestionEnabled", false},
		{"spinnerTipsEnabled", false},
		{"remoteControlAtStartup", false},
		{"effortLevel", "high"},
		{"autoCompactEnabled", true},
		{"cleanupPeriodDays", 36500},
	}
}

// formerOpusPin is the model the kit once pinned the `opus` alias to. A value equal to it is
// removed so the alias resolves to the latest Opus; any other value is the user's own and is kept.
const formerOpusPin = "claude-opus-4-8"

// Settings merges the starterkit's hooks, attribution suppression, statusline, env and config
// defaults into settings.json. An existing file is backed up first (settings.json.bak-<stamp>), and
// nothing the user has set is overwritten or reordered.
func Settings(o Options) error {
	settings := filepath.Join(o.ClaudeDir, "settings.json")
	cfg := ojson.NewObject()
	if data, err := os.ReadFile(settings); err == nil {
		v, err := ojson.Decode(data)
		if err != nil {
			return fmt.Errorf("%s is not valid JSON: %w", settings, err)
		}
		obj, ok := v.(*ojson.Object)
		if !ok {
			return fmt.Errorf("%s is not a JSON object", settings)
		}
		cfg = obj
		if err := backup(settings, settings+".bak-"+o.Now().Format("20060102-150405")); err != nil {
			return err
		}
	} else if !os.IsNotExist(err) {
		return err
	}

	if err := mergeHooks(o, cfg); err != nil {
		return err
	}

	if !cfg.Has("attribution") {
		attr := ojson.NewObject()
		attr.Set("commit", "")
		attr.Set("pr", "")
		attr.Set("sessionUrl", false)
		cfg.Set("attribution", attr)
	}

	// An earlier install's unquoted statusline command for a path with a space never ran: upgrade it.
	if sv, ok := cfg.Get("statusLine"); ok {
		if sl, ok := sv.(*ojson.Object); ok {
			if c, _ := sl.Get("command"); c == o.legacyStatuslineCommand() {
				sl.Set("command", o.StatuslineCommand())
			}
		}
	}
	if !cfg.Has("statusLine") {
		sl := ojson.NewObject()
		sl.Set("type", "command")
		sl.Set("command", o.StatuslineCommand())
		cfg.Set("statusLine", sl)
	}

	env, err := childObject(cfg, "env")
	if err != nil {
		return err
	}
	env.SetDefault("DO_NOT_TRACK", "1")
	if v, ok := env.Get("ANTHROPIC_DEFAULT_OPUS_MODEL"); ok && v == formerOpusPin {
		env.Delete("ANTHROPIC_DEFAULT_OPUS_MODEL")
	}

	for _, d := range defaults() {
		cfg.SetDefault(d.key, d.val)
	}

	// With the worklog add-on, register the matlomax plugin marketplace globally. No plugin is
	// enabled globally; enablement stays per project.
	if o.Worklog {
		mkt, err := childObject(cfg, "extraKnownMarketplaces")
		if err != nil {
			return err
		}
		src := ojson.NewObject()
		src.Set("source", "github")
		src.Set("repo", "MatLomax/claude-plugins")
		entry := ojson.NewObject()
		entry.Set("source", src)
		mkt.SetDefault("matlomax", entry)
	}

	out, err := ojson.Encode(cfg)
	if err != nil {
		return err
	}
	if err := os.WriteFile(settings, out, 0o666); err != nil {
		return err
	}
	fmt.Fprintln(o.Out, "merged hooks + attribution + statusLine + env + config defaults into settings.json")
	return nil
}

// mergeHooks appends each starterkit hook whose command is not already registered under its event.
func mergeHooks(o Options, cfg *ojson.Object) error {
	hooks, err := childObject(cfg, "hooks")
	if err != nil {
		return err
	}
	for _, ev := range Hooks {
		var groups []any
		if v, ok := hooks.Get(ev.event); ok {
			g, ok := v.([]any)
			if !ok {
				return fmt.Errorf("settings.json hooks.%s is not a list", ev.event)
			}
			groups = g
		}
		for _, h := range ev.hooks {
			if !o.wants(h.addOn) {
				continue
			}
			cmd := o.hookCommand(h.script)
			if legacy := o.legacyHookCommand(h.script); legacy != cmd {
				groups = replaceCommand(groups, legacy, cmd)
			}
			if commands(groups)[cmd] {
				continue
			}
			inner := ojson.NewObject()
			inner.Set("type", "command")
			inner.Set("command", cmd)
			for _, k := range sortedKeys(h.extra) {
				inner.Set(k, h.extra[k])
			}
			entry := ojson.NewObject()
			entry.Set("hooks", []any{inner})
			if h.matcher != "" {
				entry.Set("matcher", h.matcher)
			}
			groups = append(groups, entry)
		}
		hooks.Set(ev.event, groups)
	}
	return nil
}

// replaceCommand rewrites each hook entry whose command is old to run cmd instead, in place, so a
// reinstall upgrades the unquoted command an earlier install wrote for a path with a space rather
// than adding a second entry. When cmd is already registered, the old entries are dropped instead,
// along with any group they leave empty.
func replaceCommand(groups []any, old, cmd string) []any {
	drop := commands(groups)[cmd]
	out := groups[:0:0]
	for _, g := range groups {
		gobj, ok := g.(*ojson.Object)
		if !ok {
			out = append(out, g)
			continue
		}
		hv, _ := gobj.Get("hooks")
		list, ok := hv.([]any)
		if !ok {
			out = append(out, g)
			continue
		}
		var kept []any
		removed := false
		for _, x := range list {
			if xobj, ok := x.(*ojson.Object); ok {
				if c, _ := xobj.Get("command"); c == old {
					if drop {
						removed = true
						continue
					}
					xobj.Set("command", cmd)
					drop = true
				}
			}
			kept = append(kept, x)
		}
		if removed {
			if len(kept) == 0 {
				continue
			}
			gobj.Set("hooks", kept)
		}
		out = append(out, g)
	}
	return out
}

// commands collects every hook command already registered in an event's groups.
func commands(groups []any) map[string]bool {
	seen := map[string]bool{}
	for _, g := range groups {
		gobj, ok := g.(*ojson.Object)
		if !ok {
			continue
		}
		hv, _ := gobj.Get("hooks")
		list, _ := hv.([]any)
		for _, x := range list {
			xobj, ok := x.(*ojson.Object)
			if !ok {
				continue
			}
			if c, ok := xobj.Get("command"); ok {
				if s, ok := c.(string); ok && s != "" {
					seen[s] = true
				}
			}
		}
	}
	return seen
}

// childObject returns cfg[key], creating an empty object there when it is absent.
func childObject(cfg *ojson.Object, key string) (*ojson.Object, error) {
	v := cfg.SetDefault(key, ojson.NewObject())
	obj, ok := v.(*ojson.Object)
	if !ok {
		return nil, fmt.Errorf("settings.json %q is not an object", key)
	}
	return obj, nil
}

func sortedKeys(m map[string]any) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

// backup copies src to dst, keeping its mode and modification time.
func backup(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	st, err := in.Stat()
	if err != nil {
		return err
	}
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, st.Mode().Perm())
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	// The backup has exactly the original's mode, which the umask would otherwise trim.
	if runtime.GOOS != "windows" {
		if err := os.Chmod(dst, st.Mode().Perm()); err != nil {
			return err
		}
	}
	return os.Chtimes(dst, st.ModTime(), st.ModTime())
}
