// Package starterkit carries the files the installer lays down, embedded at build time so the
// installer binary is the whole install.
package starterkit

import "embed"

// Payload holds the ruleset and every part it imports (CLAUDE.starterkit*.md, including the
// optional worklog add-on), the opt-in review rules, both statusline scripts and every hook script,
// at the same relative paths they have in the repo.
//
//go:embed CLAUDE.starterkit*.md review-rules.md statusline-command.sh statusline-command.ps1
//go:embed hooks/*.py
var Payload embed.FS
