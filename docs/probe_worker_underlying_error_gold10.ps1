$repo = "H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED"
$docs = Join-Path $repo "docs"
$out = Join-Path $docs "probe_worker_underlying_error_gold10.out"
Remove-Item $out -ErrorAction SilentlyContinue

"=== 1) worker-ish running containers (verbatim names; authoritative; no guess) ===" | Tee-Object -FilePath $out -Append
docker ps --filter "status=running" --format "{{.Names}}" | Where-Object { $_ -match "nazm|temporal" } | Tee-Object -FilePath $out -Append

"=== 2) underlying Temporal worker workflow-crash bytes (the kill frame; disk; bounded; verbatim) ===" | Tee-Object -FilePath $out -Append
$cands = @(
  "nazmos_latest_merged-worker-1",
  "nazmos_latest_merged-worker",
  "nazmos_latest_merged-api-1"
)
foreach ($c in $cands) {
  $ok = docker inspect $c --format "OK" 2>$null
  if ($ok -eq "OK") {
    "--- container [$c] ---" | Tee-Object -FilePath $out -Append
    $lines = docker logs $c 2>&1
    $idxs = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
      if ($lines[$i] -match "Traceback|Workflow execution failed|Workflow execution|agent_approval|nazm-execution|something went wrong|temporalio.exceptions|ApplicationError|asyncpg|InvalidPassword|unhandled|ERROR") { $idxs += $i }
    }
    $seen = @{}
    foreach ($i in ($idxs | Select-Object -Last 8)) {
      for ($j = $i; $j -lt [Math]::Min($i + 6, $lines.Count); $j++) {
        if (-not $seen.ContainsKey($j)) { $lines[$j] | Tee-Object -FilePath $out -Append; $seen[$j] = $true }
      }
    }
  }
}
"=== 3) PERSISTED BYTES DONE (money worker) ===" | Tee-Object -FilePath $out -Append
