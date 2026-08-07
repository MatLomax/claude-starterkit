# Claude Code statusLine command (PowerShell port of statusline-command.sh)
# Reads JSON from stdin, outputs:
#   Model | effort | branch[*] | project | used | 3.5/5h <bar> 42% | 5.2/7d <bar> 30%
# (the separator rendered is a middot, and the bars use block glyphs)
#
# Bar colour logic:
#   filled blocks: green < 75%, yellow 75-89%, red >= 90%
#   empty blocks:  always dim (grey)
#
# Label colour logic (the "3.5/5h" / "5.2/7d" elapsed-time labels):
#   amber (yellow) when current burn rate projects hitting the cap before reset
#   red            when the used percentage has reached 98% or higher (red wins over amber)
#
# Source is deliberately ASCII-only: the block/middot glyphs are constructed from code points
# at runtime, so this file renders correctly regardless of how PowerShell decodes the script.

$ErrorActionPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$INV  = [System.Globalization.CultureInfo]::InvariantCulture
$ESC  = [char]27
$BLK  = [char]0x2588   # full block
$SHD  = [char]0x2591   # light shade
$MID  = ' ' + [char]0x00B7 + ' '   # " middot "

# --- read + parse stdin JSON ---
$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { return }
$j = $raw | ConvertFrom-Json

function N($v) { if ($null -eq $v) { 0.0 } else { [double]$v } }

# humanize: 40322 -> 40K, 1000000 -> 1M, 1500000 -> 1.5M
function Get-Hum([double]$n) {
  if ($n -ge 1000000) {
    $v = $n / 1000000.0
    if ($v -eq [math]::Floor($v)) { return ([int]$v).ToString($INV) + 'M' }
    return $v.ToString('0.0', $INV) + 'M'
  } elseif ($n -ge 1000) {
    return ([int][math]::Floor($n / 1000.0 + 0.5)).ToString($INV) + 'K'
  }
  return ([int]$n).ToString($INV)
}

# bar PCT WIDTH -> coloured block bar (empty blocks always dim grey)
function Get-Bar([double]$pct, [int]$w) {
  if ($pct -lt 0)   { $pct = 0 }
  if ($pct -gt 100) { $pct = 100 }
  if     ($pct -ge 90) { $col = "$ESC[31m" }   # red    - near the cap
  elseif ($pct -ge 75) { $col = "$ESC[33m" }   # yellow - approaching cap
  else                 { $col = "$ESC[32m" }   # green
  $dim = "$ESC[90m"; $rst = "$ESC[0m"
  $full = [int][math]::Floor($pct / 100.0 * $w + 0.5)   # round to nearest full block
  if ($full -gt $w) { $full = $w }
  $empties = $w - $full
  $s = $col
  for ($i = 0; $i -lt $full;    $i++) { $s += $BLK }
  $s += $dim
  for ($i = 0; $i -lt $empties; $i++) { $s += $SHD }
  return $s + $rst
}

# label colour for the "x/y" elapsed label, or "" (red >= 98% wins over amber-on-pace)
function Get-LabelColor([double]$pct, [int]$warn) {
  if     ($pct -ge 98) { return "$ESC[31m" }
  elseif ($warn -eq 1) { return "$ESC[33m" }
  return ''
}

# echo 1 if the current burn rate projects exceeding the cap before reset
function Test-Overshoot([double]$pct, [long]$resetsAt, [long]$winSecs) {
  $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $secsLeft = $resetsAt - $now
  if ($secsLeft -le 0) { return 0 }        # window already expired / resetting
  $elapsed = $winSecs - $secsLeft
  if ($elapsed -le 0) { return 0 }         # window just started, no rate yet
  $rate = $pct / $elapsed                  # % per second consumed so far
  $projected = $pct + $rate * $secsLeft
  if ($projected -gt 100) { return 1 } else { return 0 }
}

# elapsed wall-clock time since the window opened, in units, one decimal, trailing .0 trimmed
function Get-Elapsed([long]$resetsAt, [long]$winSecs, [long]$unit) {
  $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $secsLeft = $resetsAt - $now
  if ($secsLeft -lt 0)        { $secsLeft = 0 }         # window resetting now
  if ($secsLeft -gt $winSecs) { $secsLeft = $winSecs }  # clamp clock skew
  $elapsed = $winSecs - $secsLeft
  $s = ($elapsed / [double]$unit).ToString('0.0', $INV)
  if ($s.EndsWith('0')) { $s = $s -replace '\.0$', '' }  # 3.0 -> 3, 3.5 stays
  return $s
}

# --- model display name (strip trailing " (NM context)" suffix) ---
$model = ''
if ($j.model -and $j.model.display_name) { $model = [string]$j.model.display_name }
$model = $model -replace ' \(\d*[KMG] context\)$', ''

# --- effort level ---
$effort = ''
if ($j.effort -and $j.effort.level) { $effort = [string]$j.effort.level }

# --- project folder name (basename only) ---
$projectDir = ''; $cwd = ''
if ($j.workspace) {
  if ($j.workspace.project_dir) { $projectDir = [string]$j.workspace.project_dir }
  if ($j.workspace.current_dir) { $cwd        = [string]$j.workspace.current_dir }
}
$base = if ($projectDir) { $projectDir } else { $cwd }
$dir = ''
if ($base) { $dir = ($base -split '[\\/]') | Where-Object { $_ -ne '' } | Select-Object -Last 1 }

# --- git branch + dirty marker ---
$branch = ''
if ($cwd -and (Get-Command git -ErrorAction SilentlyContinue)) {
  $branch = (git -C $cwd symbolic-ref --short HEAD 2>$null)
  if (-not $branch) { $branch = (git -C $cwd rev-parse --short HEAD 2>$null) }
  if ($branch) {
    $branch = ([string]$branch).Trim()
    $dirty = $false
    git -C $cwd diff --quiet --no-optional-locks 2>$null
    if ($LASTEXITCODE -ne 0) { $dirty = $true }
    if (-not $dirty) {
      git -C $cwd diff --cached --quiet --no-optional-locks 2>$null
      if ($LASTEXITCODE -ne 0) { $dirty = $true }
    }
    if (-not $dirty) {
      $untracked = git -C $cwd ls-files --others --exclude-standard 2>$null
      if ($untracked) { $dirty = $true }
    }
    if ($dirty) { $branch = "$branch*" }
  }
}

# --- context usage as humanized used-token count (omit if no context_window) ---
$ctx = ''
if ($j.context_window) {
  $cu = $j.context_window.current_usage
  $used = (N $cu.input_tokens) + (N $cu.cache_creation_input_tokens) `
        + (N $cu.cache_read_input_tokens) + (N $cu.output_tokens)
  $ctx = Get-Hum $used
}

# --- rate-limit progress bars (5-hour + 7-day windows) ---
$BARW = 5
$rate = ''
$rl = $j.rate_limits

if ($rl -and $rl.five_hour -and ($null -ne $rl.five_hour.used_percentage)) {
  $p5 = [double]$rl.five_hour.used_percentage
  $rst5 = $rl.five_hour.resets_at
  $warn5 = 0; $used5 = ''
  if ($null -ne $rst5) {
    $warn5 = Test-Overshoot $p5 ([long]$rst5) 18000     # 5h = 18000s
    $used5 = Get-Elapsed ([long]$rst5) 18000 3600       # elapsed hours
  }
  $pct5 = ([int][math]::Round($p5, [MidpointRounding]::ToEven)).ToString($INV)  # match printf %.0f
  $lbl5 = ''
  if ($used5 -ne '') {
    $lc = Get-LabelColor $p5 $warn5
    if ($lc -ne '') { $lbl5 = "$lc$used5/5h$ESC[0m " } else { $lbl5 = "$used5/5h " }
  }
  $rate = "$lbl5$(Get-Bar $p5 $BARW) $pct5%"
}

if ($rl -and $rl.seven_day -and ($null -ne $rl.seven_day.used_percentage)) {
  $p7 = [double]$rl.seven_day.used_percentage
  $rst7 = $rl.seven_day.resets_at
  $warn7 = 0; $used7 = ''
  if ($null -ne $rst7) {
    $warn7 = Test-Overshoot $p7 ([long]$rst7) 604800    # 7d = 604800s
    $used7 = Get-Elapsed ([long]$rst7) 604800 86400     # elapsed days
  }
  $pct7 = ([int][math]::Round($p7, [MidpointRounding]::ToEven)).ToString($INV)  # match printf %.0f
  $lbl7 = ''
  if ($used7 -ne '') {
    $lc = Get-LabelColor $p7 $warn7
    if ($lc -ne '') { $lbl7 = "$lc$used7/7d$ESC[0m " } else { $lbl7 = "$used7/7d " }
  }
  $seg = "$lbl7$(Get-Bar $p7 $BARW) $pct7%"
  if ($rate -ne '') { $rate = "$rate$MID$seg" } else { $rate = $seg }
}

# --- assemble single status line ---
$out = $model
if ($effort -ne '') { $out = "$out$MID$effort" }
if ($branch -ne '') { $out = "$out$MID$branch" }
if ($dir    -ne '') { $out = "$out$MID$dir" }
if ($ctx    -ne '') { $out = "$out$MID$ctx" }
if ($rate   -ne '') { $out = "$out$MID$rate" }

[Console]::Out.Write($out)
