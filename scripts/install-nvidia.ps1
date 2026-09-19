param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [string]$DataDirectory = (Join-Path $env:APPDATA "io.github.amreetkumarkhuntia.eraseit")
)
$ErrorActionPreference = "Stop"
$AppVersion = "1.0.0"
if (Get-Process -Name "erase-it", "erase-it-worker" -ErrorAction SilentlyContinue) {
    throw "Close erase-it before installing the NVIDIA pack."
}
$Archive = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Archive)
$ChecksumPath = "$Archive.sha256"
if (!(Test-Path $ChecksumPath)) { throw "Keep the .zip.sha256 file beside the downloaded archive." }
$Expected = ((Get-Content $ChecksumPath -Raw).Trim() -split '\s+')[0]
$JoinedArchive = $null
$RuntimeDirectory = Join-Path $DataDirectory "runtimes"
New-Item -ItemType Directory -Path $RuntimeDirectory -Force | Out-Null
$Staging = Join-Path $RuntimeDirectory ("staging-" + [Guid]::NewGuid().ToString("N"))
$Destination = Join-Path $RuntimeDirectory "nvidia"
$Backup = Join-Path $RuntimeDirectory "nvidia-previous"
try {
    if (!(Test-Path -LiteralPath $Archive)) {
        $Parts = @(Get-ChildItem -LiteralPath (Split-Path $Archive) -File | Where-Object {
            $_.Name -match ('^' + [regex]::Escape((Split-Path $Archive -Leaf)) + '\.\d{3}$')
        } | Sort-Object Name)
        if (!$Parts.Count) { throw "Download the ZIP or all its numbered parts before installing." }
        $JoinedArchive = Join-Path $RuntimeDirectory ("download-" + [Guid]::NewGuid().ToString("N") + ".zip")
        $Output = [IO.File]::Create($JoinedArchive)
        try {
            for ($Index = 0; $Index -lt $Parts.Count; $Index++) {
                if (!$Parts[$Index].Name.EndsWith(('.{0:D3}' -f ($Index + 1)))) { throw "A numbered ZIP part is missing. Download every part." }
                $InputFile = [IO.File]::OpenRead($Parts[$Index].FullName)
                try { $InputFile.CopyTo($Output) } finally { $InputFile.Dispose() }
            }
        } finally { $Output.Dispose() }
        $Archive = $JoinedArchive
    }
    if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLower() -ne $Expected.ToLower()) {
        throw "Runtime pack checksum mismatch. Download the ZIP or every numbered part again."
    }
    Expand-Archive -LiteralPath $Archive -DestinationPath $Staging
    $Manifest = Get-Content (Join-Path $Staging "runtime-manifest.json") -Raw | ConvertFrom-Json
    if ($Manifest.app_version -ne $AppVersion -or $Manifest.platform -ne "windows-x64") { throw "This runtime pack does not match erase-it $AppVersion for Windows x64." }
    foreach ($Entry in $Manifest.files.PSObject.Properties) {
        $File = [IO.Path]::GetFullPath((Join-Path $Staging $Entry.Name))
        if (!$File.StartsWith($Staging + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Invalid path in runtime pack." }
        if ((Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLower() -ne $Entry.Value) { throw "Runtime file verification failed: $($Entry.Name)" }
    }
    if (!(Test-Path (Join-Path $Staging "erase-it-worker.exe"))) { throw "Missing runtime executable." }
    if (Test-Path $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }
    if (Test-Path $Destination) { Move-Item -LiteralPath $Destination -Destination $Backup }
    try { Move-Item -LiteralPath $Staging -Destination $Destination }
    catch { if (Test-Path $Backup) { Move-Item -LiteralPath $Backup -Destination $Destination }; throw }
    if (Test-Path $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }
    Write-Host "NVIDIA runtime installed. Open erase-it and leave Processor set to Automatic."
} finally {
    if (Test-Path $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
    if ($JoinedArchive -and (Test-Path $JoinedArchive)) { Remove-Item -LiteralPath $JoinedArchive -Force }
}
