$repo = "H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED"
$docs = Join-Path $repo "docs"
$out = Join-Path $docs "align_temporal_pg_pwd_env_only_gold13.out"
Remove-Item $out -ErrorAction SilentlyContinue

"=== 1) authoritative live bytes: the Postgres container's own POSTGRES_PASSWORD (the ONE verifier the asyncpg fixture probe GREEN-verified; verbatim; no guess) ===" | Tee-Object $out
$pgContainer = "nazmos_latest_merged-postgres-1"
$pgEnv = docker inspect $pgContainer --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
$pwLine = $pgEnv | Where-Object { $_ -match "^POSTGRES_PASSWORD=" }
$pw = ($pwLine -replace "^POSTGRES_PASSWORD=", "").Trim()
"pg_pw_len=$($pw.Length) pg_pw=[$pw]" | Tee-Object $out -Append

"=== 2) the drift site (verbatim): Temporal container's CURRENT persistence env overrides ===" | Tee-Object $out -Append
$tContainer = "nazmos_latest_merged-temporal-1"
$tEnv = docker inspect $tContainer --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
$tEnv | Where-Object { $_ -match "^POSTGRES_(PWD|USER|SEEDS)|^POSTGRES_PASSWORD" } | ForEach-Object { "temporal_env: $_" | Tee-Object $out -Append }

"=== 3) THE env-only fix (idempotent; nothing else touched): write a compose override that pins Temporal's POSTGRES_PWD/POSTGRES_PASSWORD to the live PG bytes, then recreate ONLY temporal ===" | Tee-Object $out -Append
$override = Join-Path $repo "docker-compose.temporal-pw-override.yml"
$overrideBody = @"
services:
  temporal:
    environment:
      POSTGRES_PWD: "$pw"
      POSTGRES_PASSWORD: "$pw"
"@
Set-Content -LiteralPath $override -Value $overrideBody -Encoding UTF8
Get-Content $override | ForEach-Object { "override: $_" | Tee-Object $out -Append }
$cmd = "docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.temporal-pw-override.yml up -d temporal"
$r = & docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.temporal-pw-override.yml up -d temporal 2>&1
"compose_up_temporal_exit=$LASTEXITCODE" | Tee-Object $out -Append
$r | Select-Object -Last 12 | ForEach-Object { "$_" | Tee-Object $out -Append }

"=== 4) wait Temporal healthy (bounded; 90s cap) ===" | Tee-Object $out -Append
$t0 = Get-Date
$okHealthy = $false
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 3
  $health = docker inspect $tContainer --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" 2>$null
  $running = docker inspect $tContainer --format "{{.State.Running}}" 2>$null
  if ($health -eq "healthy" -and $running -eq "true") { $okHealthy = $true; "temporal_healthy_after_s=$([math]::Round(((Get-Date)-$t0).TotalSeconds,1))" | Tee-Object $out -Append; break }
}
if (-not $okHealthy) { "temporal_NOT_healthy_in_90s (health=[$health] running=[$running])" | Tee-Object $out -Append }

"=== 5) port 7233 TCP bounded probe (the persistence-admin path Temporal's own autosetup + the WhatsApp fixture's Temporal client use) ===" | Tee-Object $out -Append
$c = New-Object Net.Sockets.TcpClient
$t1 = Get-Date
try {
  $c.Connect("127.0.0.1", 7233)
  "tcp_7233_open_wall=$([math]::Round(((Get-Date)-$t1).TotalSeconds,3))s" | Tee-Object $out -Append
} catch {
  "tcp_7233_closed: $($_.Exception.Message)" | Tee-Object $out -Append
} finally { $c.Dispose() }

"=== 6) TEMPORAL LOG FRESH TAIL (bounded; to confirm NO MORE pq/password drift at the visibility queue; persisted) ===" | Tee-Object $out -Append
docker logs $tContainer 2>&1 | Select-Object -Last 40 | Select-String -Pattern "pq:|password authentication|visibility|healthy|started|Registration|namespace" | Select-Object -Last 8 | ForEach-Object { $_.Line | Tee-Object $out -Append }

Get-Content $out | Select-Object -Last 20
