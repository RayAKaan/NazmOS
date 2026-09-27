$repo = "H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED"
$docs = Join-Path $repo "docs"
$out = Join-Path $docs "worker_underlying_crash_gold11.out"
Remove-Item $out -ErrorAction SilentlyContinue

"=== 1) authoritative running-worker container (compose label; verbatim; no guessing) ===" | Tee-Object $out
$ps = docker ps --filter "status=running" --format "{{.Names}}|{{.Label `"com.docker.compose.project`"}}|{{.Label `"com.docker.compose.service`"}}"
$ps | Where-Object { $_ -match "nazm" } | Tee-Object $out -Append

"=== 2) dump that container's FULL recent bytes to a persisted .log (bounded tail); then grep disk for the underlying Temporal/workflow Traceback (verbatim bytes) ===" | Tee-Object $out -Append
$target = $null
foreach ($pl in $ps) {
  if ($pl -match "nazm" -and $pl -match "worker") { $target = ($pl -split "\|")[0]; break }
}
if (-not $target) {
  # latest_merged compose names the worker service; find by grep of 'temporal' worker
  foreach ($pl in $ps) {
    if ($pl -match "nazm" -and $pl -match "api") { $target = ($pl -split "\|")[0]; break }
  }
}
"target_container=[$target]" | Tee-Object $out -Append
if ($target) {
  $logf = Join-Path $docs "worker_underlying_crash_gold11_$($target -replace '[^a-z0-9]','_').log"
  docker logs $target 2>&1 | Select-Object -Last 500 | Set-Content $logf
  "log_persisted=[$logf]" | Tee-Object $out -Append
  $L = Get-Content $logf
  "--- underlying crash frames (last 12; verbatim; disk) ---" | Tee-Object $out -Append
  $rx = 'Traceback|File "|line [0-9]+|Error|error|execution|Execution|activity|Activity|workflow|Workflow|nazm|Tensor|payload|attribute|encode|decode|serialize|worker_start'
  $L | Select-String -Pattern $rx | Select-Object -Last 14 | ForEach-Object { $_.Line | Tee-Object $out -Append }
}

"=== 3) final tail of the persisted .out (verbatim) ===" | Tee-Object $out -Append
Get-Content $out