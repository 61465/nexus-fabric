# Nexus Fabric — baseline capture harness.
# Collects xperf ETL trace + 1Hz PerfCounter samples for -DurationSec seconds.
# Writes an ETL file plus a JSON summary to .\reports\.

param(
    [string]$WorkloadName = "Synthetic",
    [int]$DurationSec = 60
)

$ErrorActionPreference = "Stop"

# Resolve xperf: prefer PATH, then the bundled Windows Performance Toolkit
# that ships at D:\project\cyber_pro\Windows Performance Toolkit\xperf.exe.
$xperf = (Get-Command xperf.exe -ErrorAction SilentlyContinue)
if ($xperf) {
    $xperfPath = $xperf.Source
} else {
    $bundled = "D:\project\cyber_pro\Windows Performance Toolkit\xperf.exe"
    if (Test-Path $bundled) {
        $xperfPath = $bundled
    } else {
        Write-Error "xperf.exe not found in PATH and bundled copy missing. Install Windows ADK Performance Toolkit."
        exit 1
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$reportsDir = Join-Path $scriptDir "reports"
New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeName  = ($WorkloadName -replace '[^A-Za-z0-9_-]', '_')
$etlPath   = Join-Path $reportsDir ("baseline_{0}_{1}.etl"  -f $safeName, $timestamp)
$jsonPath  = Join-Path $reportsDir ("baseline_{0}_{1}.json" -f $safeName, $timestamp)

Write-Host "[baseline] starting xperf session (duration=$DurationSec s workload=$WorkloadName)"

& $xperfPath -on PROC_THREAD+LOADER+DISK_IO+DPC+INTERRUPT -stackwalk Profile
if ($LASTEXITCODE -ne 0) {
    Write-Error "xperf failed to start (exit $LASTEXITCODE). Run elevated."
    exit 1
}

$startTime = Get-Date

# Collect PerfCounter samples concurrently with xperf trace.
$counterJob = Start-Job -ScriptBlock {
    param($Duration)
    Get-Counter `
        -Counter '\Processor(_Total)\% Processor Time', '\Memory\Available MBytes' `
        -SampleInterval 1 -MaxSamples $Duration
} -ArgumentList $DurationSec

Start-Sleep -Seconds $DurationSec

& $xperfPath -stop -d $etlPath
$endTime = Get-Date

$counterResult = Receive-Job -Job $counterJob -Wait
Remove-Job -Job $counterJob -Force

$cpu = @(
    $counterResult.CounterSamples |
        Where-Object { $_.Path -like '*processor*' } |
        ForEach-Object { [math]::Round($_.CookedValue, 2) }
)
$ram = @(
    $counterResult.CounterSamples |
        Where-Object { $_.Path -like '*memory*' } |
        ForEach-Object { [math]::Round($_.CookedValue, 0) }
)

$summary = [ordered]@{
    workload_name   = $WorkloadName
    duration_sec    = $DurationSec
    start_time      = $startTime.ToString("o")
    end_time        = $endTime.ToString("o")
    etl_path        = $etlPath
    cpu_samples_pct = $cpu
    ram_available_mb = $ram
    sample_count    = [math]::Min($cpu.Count, $ram.Count)
}

$summary | ConvertTo-Json -Depth 4 | Set-Content -Path $jsonPath -Encoding UTF8

Write-Host "[baseline] done:"
Write-Host "  ETL  : $etlPath"
Write-Host "  JSON : $jsonPath"
Write-Host "  CPU samples: $($cpu.Count)  RAM samples: $($ram.Count)"
