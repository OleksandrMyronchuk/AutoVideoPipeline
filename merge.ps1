<#
.SYNOPSIS
    Scans the CURRENT directory, but saves the output file based on the Switcher.
#>

# ==========================================
# 1. SWITCHER: WHERE TO SAVE?
# ==========================================

# Set to $true  = Save to the Hardcoded Path below (e.g., A:\)
# Set to $false = Save to the Current Script Directory
$SaveToHardcodedPath = $true

# 2. Hardcoded Path (Only used if Switcher is $true)
$HardcodedPath = "A:\"

# ==========================================
# FILE FILTER CONFIGURATION
# ==========================================

$OutputFileName = "full_py_project_dump.txt"

# Folders to ignore
$ExcludedFolders = @(
    "--delete--", "browser_profile", "puter_profile", "chrome_profile", ".env", ".venv", ".git", ".vs", ".idea", ".vscode", "node_modules", "bin", "obj", 
    "dist", "build", "__pycache__", "vendor", "packages", "debug", "release"
)

# Extensions to ignore
$ExcludedExtensions = @(
    ".ps1", ".gitignore", ".exe", ".dll", ".so", ".bin", ".pdb", ".zip", ".png", ".jpg", ".pdf", 
    ".log", ".lock", ".tmp", ".min.js", ".min.css", ".map"
)

# Files to ignore
$ExcludedFiles = @(
    "package-lock.json", "yarn.lock", $OutputFileName, $MyInvocation.MyCommand.Name
)

# ==========================================
# SCRIPT LOGIC
# ==========================================

# 1. Determine Source (ALWAYS Current Location)
$SourcePath = Get-Location

# 2. Determine Output Destination (Based on Switcher)
if ($SaveToHardcodedPath) {
    if (-not (Test-Path $HardcodedPath)) {
        Write-Error "The hardcoded path '$HardcodedPath' does not exist. Saving to current location instead."
        $DestinationDir = $SourcePath
    } else {
        $DestinationDir = $HardcodedPath
    }
} else {
    $DestinationDir = $SourcePath
}

# Combine destination dir with filename
$FullOutputPath = Join-Path -Path $DestinationDir -ChildPath $OutputFileName

# Visual Feedback
Write-Host "========================================" -ForegroundColor Magenta
Write-Host " SCAN SOURCE:  $SourcePath" -ForegroundColor Cyan
Write-Host " SAVE TARGET:  $FullOutputPath" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Magenta

# Clean up old file
if (Test-Path $FullOutputPath) {
    Remove-Item $FullOutputPath -Force
    Write-Host "Overwriting old dump file..." -ForegroundColor DarkGray
}

$FileCount = 0

# Scan Source
Get-ChildItem -Path $SourcePath -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $File = $_
    
    # Calculate Relative Path for display
    try {
        $RelativePath = $File.FullName.Substring($SourcePath.Path.Length)
        if ($RelativePath.StartsWith("\")) { $RelativePath = $RelativePath.Substring(1) }
    } catch {
        $RelativePath = $File.Name
    }

    # --- FILTERING ---
    
    # 1. Check Folders
    $ParentDirs = $RelativePath.Split([System.IO.Path]::DirectorySeparatorChar)
    $IsExcludedFolder = $false
    foreach ($Dir in $ParentDirs) {
        if ($ExcludedFolders -contains $Dir) { $IsExcludedFolder = $true; break }
    }
    if ($IsExcludedFolder) { return }

    # 2. Check Extension & Name
    if ($ExcludedExtensions -contains $File.Extension.ToLower()) { return }
    if ($ExcludedFiles -contains $File.Name) { return }
    if ($File.Name -match "\.min\.") { return }

    # --- WRITE TO OUTPUT ---
    
    Write-Host "Reading: $RelativePath" -ForegroundColor Green
    
    try {
        $Header = "`n`n" + ("=" * 50) + "`n" + 
                  "PATH: $RelativePath" + "`n" + 
                  ("=" * 50) + "`n"

        $Content = Get-Content -Path $File.FullName -Raw -ErrorAction Stop
        
        # Append to the defined Destination Path
        $Header + $Content | Out-File -FilePath $FullOutputPath -Append -Encoding utf8
        $FileCount++
    }
    catch {
        Write-Host "  [Error] Skipped: $RelativePath" -ForegroundColor Red
    }
}

Write-Host "`nDone! Saved $FileCount files to: $FullOutputPath" -ForegroundColor Cyan