[CmdletBinding(SupportsShouldProcess)]
param()

$workspaceRoot = Join-Path $PSScriptRoot '.script_workspaces'

if (-not (Test-Path -LiteralPath $workspaceRoot -PathType Container)) {
    Write-Verbose "Workspace directory does not exist: $workspaceRoot"
    exit 0
}

Get-ChildItem -LiteralPath $workspaceRoot -Recurse -File -Filter '*.log' -ErrorAction SilentlyContinue |
    ForEach-Object {
        if ($PSCmdlet.ShouldProcess($_.FullName, 'Delete log')) {
            Remove-Item -LiteralPath $_.FullName -Force
        }
    }

Get-ChildItem -LiteralPath $workspaceRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match '^(?:[0-9a-fA-F]{32}|script-[0-9a-fA-F]{32})$' -and
        -not (Get-ChildItem -LiteralPath (Join-Path $_.FullName 'plugins') -File -Filter '*.py' -ErrorAction SilentlyContinue)
    } |
    ForEach-Object {
        if ($PSCmdlet.ShouldProcess($_.FullName, 'Delete script workspace with no UI script')) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }