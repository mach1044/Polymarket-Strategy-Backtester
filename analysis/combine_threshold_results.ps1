param(
    [string]$AnalysisDirectory = "data/analysis",
    [double]$StakePerHedge = 100.0
)

$sports = @(
    "fifa",
    "nba",
    "nba_2025",
    "nhl",
    "nhl_2025",
    "mlb",
    "nfl",
    "lol_worlds_2025",
    "wimbledon_2026",
    "ucl_2026"
)

$allResults = foreach ($sport in $sports) {
    $path = Join-Path $AnalysisDirectory "${sport}_threshold_comparison.csv"
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing threshold comparison: $path"
    }

    foreach ($row in Import-Csv -LiteralPath $path) {
        [pscustomobject]@{
            sport              = $sport
            threshold_percent  = [int]$row.threshold_percent
            qualifying_hedges  = [int]$row.qualifying_hedges
            trade_count        = [int]$row.trade_count
            total_pnl          = [double]$row.total_pnl
            pnl_per_hedge      = $row.pnl_per_hedge
            return_on_stake    = $row.return_on_stake
            max_drawdown       = [double]$row.max_drawdown
        }
    }
}

$allResults |
    Sort-Object sport, threshold_percent |
    Export-Csv (
        Join-Path $AnalysisDirectory "all_sports_threshold_comparison.csv"
    ) -NoTypeInformation

$pooledResults = $allResults |
    Group-Object threshold_percent |
    ForEach-Object {
        $hedges = ($_.Group | Measure-Object qualifying_hedges -Sum).Sum
        $trades = ($_.Group | Measure-Object trade_count -Sum).Sum
        $pnl = ($_.Group | Measure-Object total_pnl -Sum).Sum
        $deployedStake = $hedges * $StakePerHedge

        [pscustomobject]@{
            threshold_percent      = [int]$_.Name
            active_sports          = @(
                $_.Group | Where-Object qualifying_hedges -gt 0
            ).Count
            profitable_sports      = @(
                $_.Group | Where-Object total_pnl -gt 0
            ).Count
            qualifying_hedges      = $hedges
            trade_count            = $trades
            total_deployed_stake   = [math]::Round($deployedStake, 6)
            total_pnl              = [math]::Round($pnl, 6)
            pnl_per_hedge          = if ($hedges) {
                [math]::Round($pnl / $hedges, 6)
            } else { $null }
            return_on_stake        = if ($deployedStake) {
                [math]::Round($pnl / $deployedStake, 6)
            } else { $null }
        }
    } |
    Sort-Object threshold_percent

$pooledResults |
    Export-Csv (
        Join-Path $AnalysisDirectory "combined_threshold_comparison.csv"
    ) -NoTypeInformation

$bestBySport = $allResults |
    Where-Object qualifying_hedges -gt 0 |
    Group-Object sport |
    ForEach-Object {
        $best = $_.Group |
            Sort-Object @{ Expression = "total_pnl"; Descending = $true }, `
                        @{ Expression = "threshold_percent"; Descending = $false } |
            Select-Object -First 1

        [pscustomobject]@{
            sport                  = $_.Name
            best_threshold_percent = $best.threshold_percent
            qualifying_hedges      = $best.qualifying_hedges
            total_pnl              = [math]::Round($best.total_pnl, 6)
            pnl_per_hedge          = $best.pnl_per_hedge
            return_on_stake        = $best.return_on_stake
        }
    } |
    Sort-Object sport

$bestBySport |
    Export-Csv (
        Join-Path $AnalysisDirectory "threshold_comparison_summary.csv"
    ) -NoTypeInformation

$bestCombined = $pooledResults |
    Where-Object qualifying_hedges -gt 0 |
    Sort-Object @{ Expression = "total_pnl"; Descending = $true }, `
                @{ Expression = "threshold_percent"; Descending = $false } |
    Select-Object -First 1

Write-Output (
    "Combined best threshold: {0}% | hedges: {1} | P&L: `${2:N2} | return: {3:P2}" -f `
        $bestCombined.threshold_percent,
        $bestCombined.qualifying_hedges,
        $bestCombined.total_pnl,
        $bestCombined.return_on_stake
)
