#!/usr/bin/env bash
# Claude Code statusLine command
# Reads JSON from stdin, outputs:
#   Model · effort · branch[*] · project · used · 3.5/5h <bar> 42% · 5.2/7d <bar> 30%
#
# Bar colour logic:
#   filled blocks: green < 75%, yellow 75-89%, red >= 90%
#   empty blocks:  always dim (grey)
#
# Label colour logic (the "3.5/5h" / "5.2/7d" elapsed-time labels):
#   amber (yellow) when current burn rate projects hitting the cap before reset
#   red            when the used percentage has reached 98% or higher (red wins over amber)

input=$(cat)

# --- model display name (strip trailing " (NM context)" suffix) ---
model=$(echo "$input" | jq -r '.model.display_name // empty' | sed 's/ ([0-9]*[KMG] context)$//')

# --- effort level (own segment) ---
effort=$(echo "$input" | jq -r '.effort.level // empty')

# --- project folder name (basename only) ---
project_dir=$(echo "$input" | jq -r '.workspace.project_dir // empty')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // empty')
dir=$(basename "${project_dir:-${cwd}}")

# --- git branch + dirty marker ---
branch=""
if command -v git >/dev/null 2>&1 && [ -n "$cwd" ]; then
  branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
           || git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
  if [ -n "$branch" ]; then
    # --no-optional-locks avoids stale lock contention in background calls
    if ! git -C "$cwd" diff --quiet --no-optional-locks 2>/dev/null \
         || ! git -C "$cwd" diff --cached --quiet --no-optional-locks 2>/dev/null \
         || [ -n "$(git -C "$cwd" ls-files --others --exclude-standard 2>/dev/null)" ]; then
      branch="${branch}*"
    fi
  fi
fi

# --- context usage as actual tokens: used / window size (omit if absent) ---
# used = the tokens occupying the window right now (input + cache + output)
used=$(echo "$input" | jq -r '
  if .context_window then
    ( (.context_window.current_usage.input_tokens              // 0)
    + (.context_window.current_usage.cache_creation_input_tokens // 0)
    + (.context_window.current_usage.cache_read_input_tokens     // 0)
    + (.context_window.current_usage.output_tokens             // 0) )
  else empty end')
winsize=$(echo "$input" | jq -r '.context_window.context_window_size // empty')

# humanize: 40322 -> 40K, 1000000 -> 1M, 1500000 -> 1.5M
hum() {
  awk -v n="$1" 'BEGIN{
    if (n >= 1000000) { v=n/1000000; if (v==int(v)) printf "%dM", v; else printf "%.1fM", v }
    else if (n >= 1000) { printf "%dK", int(n/1000 + 0.5) }
    else { printf "%d", n }
  }'
}

ctx=""
if [ -n "$used" ]; then
  ctx="$(hum "$used")"
fi

# --- rate-limit progress bars (5-hour + 7-day windows) ---
# bar PCT WIDTH  ->  coloured block bar (empty blocks always dim grey)
#   PCT        = 0-100 used percentage
#   WIDTH      = number of block characters
ESC=$(printf '\033')
bar() {
  awk -v pct="$1" -v w="$2" -v e="$ESC" 'BEGIN{
    if (pct < 0) pct=0; if (pct > 100) pct=100;
    if      (pct >= 90) col=e"[31m";   # red   — near the cap
    else if (pct >= 75) col=e"[33m";   # yellow — approaching cap
    else                col=e"[32m";   # green
    dim  = e"[90m";
    rst  = e"[0m";
    eighths = pct/100.0 * w * 8;
    full = int(eighths/8 + 0.5);   # round to nearest full block
    if (full > w) full=w;
    empties = w - full;
    s = col;
    for (i=0; i<full;   i++) s = s "█";
    s = s dim;
    for (i=0; i<empties; i++) s = s "░";
    printf "%s%s", s, rst;
  }'
}

# label_color PCT WARN  ->  ANSI colour escape for the "x/y" elapsed label, or empty
#   PCT  = used_percentage (0-100)
#   WARN = 1 if on pace to overshoot the cap before reset, 0 otherwise
#   red (>= 98% used) wins over amber (on pace to overshoot)
label_color() {
  awk -v pct="$1" -v warn="$2" -v e="$ESC" 'BEGIN{
    if      (pct+0 >= 98) printf "%s", e"[31m";
    else if (warn == 1)   printf "%s", e"[33m";
    else                  printf "%s", "";
  }'
}

# on_pace_to_overshoot PCT RESETS_AT WINDOW_SECONDS -> echo 1 if burn rate will exceed cap
# Logic: elapsed = window_seconds - seconds_until_reset
#        rate    = pct / elapsed  (percent per second)
#        projected_pct_at_reset = pct + rate * seconds_until_reset
#        overshoot if projected > 100
on_pace_to_overshoot() {
  local pct="$1"        # used_percentage (0-100)
  local resets_at="$2"  # unix epoch seconds
  local win_secs="$3"   # total window in seconds

  awk -v pct="$pct" -v resets_at="$resets_at" -v win_secs="$win_secs" 'BEGIN{
    now = int(systime());
    secs_left = resets_at - now;
    if (secs_left <= 0) { print 0; exit }   # window already expired / resetting
    elapsed = win_secs - secs_left;
    if (elapsed <= 0) { print 0; exit }     # window just started, no rate yet
    rate_per_sec = pct / elapsed;           # % per second consumed so far
    projected = pct + rate_per_sec * secs_left;
    print (projected > 100) ? 1 : 0;
  }'
}

# fmt_elapsed RESETS_AT WINDOW_SECONDS UNIT_SECONDS -> elapsed clock time in units
#   (e.g. UNIT_SECONDS=3600 -> hours, 86400 -> days), one decimal, trailing .0 trimmed.
#   elapsed = window - (resets_at - now); this is real wall-clock time since the
#   window opened, NOT a rescaling of the usage percentage.
fmt_elapsed() {
  awk -v resets_at="$1" -v win_secs="$2" -v unit="$3" 'BEGIN{
    now = int(systime());
    secs_left = resets_at - now;
    if (secs_left < 0)        secs_left = 0;        # window resetting now
    if (secs_left > win_secs) secs_left = win_secs; # clamp clock skew
    elapsed = win_secs - secs_left;
    v = elapsed / unit;
    s = sprintf("%.1f", v);
    if (substr(s, length(s), 1) == "0") sub(/\.0$/, "", s);  # 3.0 -> 3, 3.5 stays
    printf "%s", s;
  }'
}

BARW=5
now_epoch=$(date +%s)

rl5_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
rl5_rst=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at       // empty')
rl7_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
rl7_rst=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at       // empty')

rate=""

if [ -n "$rl5_pct" ]; then
  warn5=0
  used5=""
  if [ -n "$rl5_rst" ]; then
    warn5=$(on_pace_to_overshoot "$rl5_pct" "$rl5_rst" 18000)  # 5h = 18000s
    used5=$(fmt_elapsed "$rl5_rst" 18000 3600)                 # elapsed hours
  fi
  pct5=$(printf '%.0f' "$rl5_pct")
  lbl5=""
  if [ -n "$used5" ]; then
    lcol5=$(label_color "$rl5_pct" "$warn5")
    if [ -n "$lcol5" ]; then
      lbl5="${lcol5}${used5}/5h${ESC}[0m "
    else
      lbl5="${used5}/5h "
    fi
  fi
  rate="${lbl5}$(bar "$rl5_pct" "$BARW") ${pct5}%"
fi

if [ -n "$rl7_pct" ]; then
  warn7=0
  used7=""
  if [ -n "$rl7_rst" ]; then
    warn7=$(on_pace_to_overshoot "$rl7_pct" "$rl7_rst" 604800)  # 7d = 604800s
    used7=$(fmt_elapsed "$rl7_rst" 604800 86400)                # elapsed days
  fi
  pct7=$(printf '%.0f' "$rl7_pct")
  lbl7=""
  if [ -n "$used7" ]; then
    lcol7=$(label_color "$rl7_pct" "$warn7")
    if [ -n "$lcol7" ]; then
      lbl7="${lcol7}${used7}/7d${ESC}[0m "
    else
      lbl7="${used7}/7d "
    fi
  fi
  seg="${lbl7}$(bar "$rl7_pct" "$BARW") ${pct7}%"
  rate="${rate:+$rate · }$seg"
fi

# --- assemble single status line ---
sep=" · "

out="${model}"
[ -n "$effort" ] && out="${out}${sep}${effort}"
[ -n "$branch" ] && out="${out}${sep}${branch}"
[ -n "$dir"    ] && out="${out}${sep}${dir}"
[ -n "$ctx"    ] && out="${out}${sep}${ctx}"
[ -n "$rate"   ] && out="${out}${sep}${rate}"

printf '%s' "$out"
