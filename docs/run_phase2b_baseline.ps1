Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repo = "H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED"
Set-Location "$repo\backend"
$env:PYTHONPATH = "$repo\backend"

$container = "nazmos_latest_merged-postgres-1"
$pwLine = docker inspect $container --format '{{range .Config.Env}}{{println .}}{{end}}' | Where-Object { $_ -match "^POSTGRES_PASSWORD=" }
$pw = ($pwLine -replace "^POSTGRES_PASSWORD=","").Trim()
$uLine = docker inspect $container --format '{{range .Config.Env}}{{println .}}{{end}}' | Where-Object { $_ -match "^POSTGRES_USER=" }
$u = ($uLine -replace "^POSTGRES_USER=","").Trim()
"live_cred: user=[$u] pwlen=$($pw.Length) pw8=[$($pw.Substring(0,[Math]::Min(8,$pw.Length)))]"

$url = "postgresql+asyncpg://" + $u + ":" + $pw + "@localhost:5432/nazmos_test"
$env:DATABASE_URL = $url
$env:TEST_DATABASE_URL = $url

"=== exact on-disk test files (recovery/match/rls/money/decision/integrity) ==="
$tests = Get-ChildItem "$repo\backend\tests" -File -Filter "test_*.py" | Where-Object {
    $_.Name -match "recovery|match|rls|rls_|financial|money|truth|vocab|decision|decision_|integrit|orph|\|procurement|inventory|forecast" } | ForEach-Object { $_.FullName }
$tests | ForEach-Object { $_ -replace [regex]::Escape("$repo\backend\tests\"),"tests\" } | Sort-Object

"=== §2 BASELINE (live PG credential from container, no code change) ==="
& python -m pytest $tests -q --no-header --tb=line --no-summary --no-header -p no:warnings 2>&1 | Select-Object -Last 8
"baseline_exit=$LASTEXITCODE"