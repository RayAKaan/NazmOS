$repo = "H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED"
$docs = Join-Path $repo "docs"
$out = Join-Path $docs "align_temporal_pwd_actuator_gold1.out"
Remove-Item $out -ErrorAction SilentlyContinue

"=== 1) AUTHORITATIVE: live PG container's own POSTGRES_PASSWORD bytes (verbatim; the one the asyncpg fixture-probe already proved GREEN; no guesses) ===" | Tee-Object $out -Append
$pg = "nazmos_latest_merged-postgres-1"
$envBytes = docker inspect $pg --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
$pwLine = ($envBytes | Where-Object { $_ -match '^POSTGRES_PASSWORD=' }).Trim()
$pw = ($pwLine -replace '^POSTGRES_PASSWORD=', '').Trim()
"live_pw_len=$($pw.Length) live_pw_first4=[$($pw.Substring(0,[Math]::Min(4,$pw.Length)))]" | Tee-Object $out -Append

"=== 2) Temporal container's CURRENT persistence env (the drift site; verbatim) ===" | Tee-Object $out -Append
$t = "nazmos_latest_merged-temporal-1"
$tEnv = docker inspect $t --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
$tEnv | Where-Object { $_ -match '^(POSTGRES_PWD|POSTGRES_PASSWORD|POSTGRES_USER|POSTGRES_SEEDS|DBNAME|VISIBILITY)' } | ForEach-Object { "temporal_env: $_" | Tee-Object $out -Append }

"=== 3) compose env-override file (env-only; aside; idempotent; pins Temporal persistence to the LIVE bytes; nothing else touched) ===" | Tee-Object $out -Append
$override = Join-Path $repo "docker-compose.temporal-pw-fix.yml"
$body = @"
services:
  temporal:
    environment:
      POSTGRES_PWD: "$pw"
      POSTGRES_PASSWORD: "$pw"
"@
Set-Content -LiteralPath $override -Value $body -Encoding UTF8
"override_written=[$override]" | Tee-Object $out -Append
Get-Content $override | ForEach-Object { $_ | Tee-Object $out -Append }

"=== 4) recreate ONLY temporal with the pinned env (PGDATA + money code + other services untouched); bounded ===" | Tee-Object $out -Append
docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.temporal-pw-fix.yml up -d temporal 2>&1 | Select-Object -Last 4 | ForEach-Object { $_ | Tee-Object $out -Append }
"compose_up_temporal_exit=$LASTEXITCODE" | Tee-Object $out -Append

"=== 5) wait Temporal healthy (bounded; 100s) then probe 7233 ===" | Tee-Object $out -Append
$t0 = Get-Date
$healthy = $false
for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Seconds 5
  $h = docker inspect $t --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>$null
  if ($h -eq 'healthy') { $healthy = $true; "temporal_healthy_after_s=$([math]::Round(((Get-Date)-$t0).TotalSeconds,1))" | Tee-Object $out -Append; break }
}
if (-not $healthy) { "temporal_health_timeout h=[$h]" | Tee-Object $out -Append }
$c = New-Object Net.Sockets.TcpClient
try { $c.Connect('127.0.0.1', 7233); 'tcp_7233_open=yes' | Tee-Object $out -Append } catch { 'tcp_7233_open=no' | Tee-Object $out -Append } finally { $c.Dispose() }

Get-Content $out | Select-Object -Last 18
