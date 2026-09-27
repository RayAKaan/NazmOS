$repo = "H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED"
$docs = Join-Path $repo "docs"
$out = Join-Path $docs "align_temporal_pwd_gold_actuator.out"
Remove-Item $out -ErrorAction SilentlyContinue

"=== STEP 1) AUTHORITATIVE live PG password bytes (from the postgres container's OWN env; the exact ones the asyncpg fixture probe GREEN-verified; no guessing, no default, no hardcode) ===" | Tee-Object $out
$pg = "nazmos_latest_merged-postgres-1"
$pgEnv = docker inspect $pg --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
$pwLine = ($pgEnv | Where-Object { $_ -match "^POSTGRES_PASSWORD=" })
$pw = (($pwLine -replace "^POSTGRES_PASSWORD=","") -replace "`r`n","").Trim()
"live_pg_pw_len=$($pw.Length) live_pg_pw_first4=[$($pw.Substring(0,[Math]::Min(4,$pw.Length)))]" | Tee-Object $out -Append

"=== STEP 2) WHERE the stale credential currently lives (drift site; verbatim from the Temporal container's OWN env — Temporal's history/visibility persistence authenticates with these bytes) ===" | Tee-Object $out -Append
$t = "nazmos_latest_merged-temporal-1"
$tEnv = docker inspect $t --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
$tPwd = ($tEnv | Where-Object { $_ -match "^POSTGRES_PWD=" })
"temporal_env_used_for_persistence=[$tPwd]" | Tee-Object $out -Append
$tEnv | Where-Object { $_ -match "POSTGRES|VISIBILITY|DBNAME|SEEDS" } | ForEach-Object { "temporal_env: $_" | Tee-Object $out -Append }

"=== STEP 3) THE FIX — pin ONLY Temporal's persistence env to the LIVE PG bytes (env-only; infra-only; idempotent; does NOT touch money code, does NOT touch PGDATA or other services); recreate ONLY temporal ===" | Tee-Object $out -Append
$override = Join-Path $repo "docs\temporal-pwd-fix-compose.yml"
$content = @"
services:
  temporal:
    environment:
      POSTGRES_PWD: "$pw"
      POSTGRES_PASSWORD: "$pw"
"@
Set-Content -LiteralPath $override -Value $content -Encoding UTF8
"override_written=[$override]" | Tee-Object $out -Append
Get-Content $override | ForEach-Object { "override: $_" | Tee-Object $out -Append }

"=== STEP 4) recreate ONLY temporal; bounded (120s) ===" | Tee-Object $out -Append
$t0 = Get-Date
docker compose -f docker-compose.yml -f docker-compose.override.yml -f docs\temporal-pwd-fix-compose.yml up -d temporal 2>&1 | ForEach-Object { $_ | Tee-Object $out -Append }
"compose_up_exit=$LASTEXITCODE" | Tee-Object $out -Append

"=== STEP 5) confirm Temporal env is NOW pinned to live bytes (drift closed; verbatim) ===" | Tee-Object $out -Append
$tEnv2 = docker inspect $t --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
$tEnv2 | Where-Object { $_ -match "^POSTGRES_PWD=" } | ForEach-Object { "after: $_" | Tee-Object $out -Append }

"=== STEP 6) await Temporal healthy (bounded 90s) then verify port 7233 ===" | Tee-Object $out -Append
$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 3
  $h = docker inspect $t --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>$null
  if ($h -eq "healthy") { $healthy = $true; "temporal_healthy_after=$([math]::Round(((Get-Date)-$t0).TotalSeconds,1))s" | Tee-Object $out -Append; break }
}
if (-not $healthy) { "temporal_health_timeout" | Tee-Object $out -Append }
$c = New-Object Net.Sockets.TcpClient
try { $c.Connect("127.0.0.1", 7233); "tcp_7233_open=yes" | Tee-Object $out -Append } catch { "tcp_7233_closed: $($_.Exception.Message)" | Tee-Object $out -Append } finally { $c.Dispose() }

Get-Content $out | Select-Object -Last 20
