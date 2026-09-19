# Used by the embedded installer helper. Download metadata is pinned inside setup.
function Test-NvidiaFile($File, $Size, $Digest) {
    return ((Test-Path -LiteralPath $File) -and
        (Get-Item -LiteralPath $File).Length -eq $Size -and
        (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash -eq $Digest)
}

function Get-NvidiaPart($Uri, $Destination, $Size, $Digest) {
    if (Test-NvidiaFile $Destination $Size $Digest) {
        Write-Host "Reusing verified download: $([IO.Path]::GetFileName($Destination))"
        return
    }
    $Partial = "$Destination.partial"
    $Offset = 0L
    if (Test-Path -LiteralPath $Partial) { $Offset = (Get-Item -LiteralPath $Partial).Length }
    if ($Offset -ge $Size) {
        if (Test-NvidiaFile $Partial $Size $Digest) {
            Move-Item -LiteralPath $Partial -Destination $Destination -Force
            return
        }
        Remove-Item -LiteralPath $Partial -Force
        $Offset = 0L
    }
    $Request = [Net.HttpWebRequest]::Create($Uri)
    $Request.UserAgent = 'erase-it-setup'
    $Request.Timeout = 30000
    $Request.ReadWriteTimeout = 120000
    if ($Offset) { $Request.AddRange([long]$Offset) }
    $Response = $null
    $InputStream = $null
    $OutputStream = $null
    try {
        $Response = $Request.GetResponse()
        if ($Response.StatusCode -eq 206) {
            if ($Response.Headers['Content-Range'] -notmatch ('^bytes ' + $Offset + '-\d+/' + $Size + '$')) {
                throw 'The server returned an unexpected download range. Retry setup.'
            }
        } elseif ($Response.StatusCode -eq 200) {
            $Offset = 0L
        } else { throw "Unexpected download response: $($Response.StatusCode)" }
        $Mode = if ($Offset) { [IO.FileMode]::Append } else { [IO.FileMode]::Create }
        $OutputStream = [IO.File]::Open($Partial, $Mode, [IO.FileAccess]::Write)
        $InputStream = $Response.GetResponseStream()
        $Buffer = New-Object byte[] (1024 * 1024)
        $LastReported = -1
        while (($Read = $InputStream.Read($Buffer, 0, $Buffer.Length)) -gt 0) {
            $Offset += $Read
            if ($Offset -gt $Size) { throw 'The download is larger than expected. Retry setup.' }
            $OutputStream.Write($Buffer, 0, $Read)
            $Percent = [int][Math]::Floor(100 * $Offset / $Size)
            if ($Percent -ge $LastReported + 5) {
                Write-Host "Downloading $([IO.Path]::GetFileName($Destination)): $Percent%"
                $LastReported = $Percent
            }
        }
    } finally {
        if ($InputStream) { $InputStream.Dispose() }
        if ($OutputStream) { $OutputStream.Dispose() }
        if ($Response) { $Response.Dispose() }
    }
    if (!(Test-NvidiaFile $Partial $Size $Digest)) {
        # Keep an interrupted prefix for retry, but discard corrupt complete files.
        if ((Get-Item -LiteralPath $Partial).Length -ge $Size) { Remove-Item -LiteralPath $Partial -Force }
        throw 'Download verification failed. Check your connection and retry setup.'
    }
    Move-Item -LiteralPath $Partial -Destination $Destination -Force
}

function Get-NvidiaRuntime($ManifestPath, $DataDirectory, $Version) {
    $Metadata = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $ArchiveName = "erase-it-nvidia-$Version-windows-x64.zip"
    if ($Metadata.app_version -cne $Version -or $Metadata.platform -cne 'windows-x64' -or
        $Metadata.archive.name -cne $ArchiveName -or $Metadata.archive.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
        $Metadata.archive.size -le 0 -or $Metadata.unpacked_size -le 0) {
        throw 'The bundled NVIDIA download information does not match this app version. Download setup again.'
    }
    $BaseUri = [Uri]$Metadata.base_url
    if (!$BaseUri.IsAbsoluteUri -or ($BaseUri.Scheme -ne 'https' -and !($BaseUri.Scheme -eq 'http' -and $BaseUri.IsLoopback))) {
        throw 'Invalid NVIDIA download address.'
    }
    $Parts = @($Metadata.files)
    if (!$Parts.Count -or $Parts.Count -gt 999) { throw 'Invalid NVIDIA download file list.' }
    $Total = 0L
    for ($Index = 0; $Index -lt $Parts.Count; $Index++) {
        $Part = $Parts[$Index]
        $ExpectedName = if ($Parts.Count -eq 1) { $ArchiveName } else { $ArchiveName + ('.{0:D3}' -f ($Index + 1)) }
        if ($Part.name -cne $ExpectedName -or $Part.size -le 0 -or
            $Part.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid NVIDIA download file list.' }
        $Total += [long]$Part.size
    }
    if ($Total -ne $Metadata.archive.size) { throw 'Invalid NVIDIA archive size.' }
    $CacheDirectory = Join-Path $DataDirectory "runtimes\downloads\$Version"
    New-Item -ItemType Directory -Path $CacheDirectory -Force | Out-Null
    $CacheDirectory = [IO.Path]::GetFullPath($CacheDirectory)
    $Drive = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($CacheDirectory))
    $Needed = [long]$Metadata.unpacked_size + [long]$Metadata.archive.size + 512MB
    foreach ($Part in $Parts) {
        $Existing = Join-Path $CacheDirectory $Part.name
        if (!(Test-NvidiaFile $Existing $Part.size $Part.sha256)) { $Needed += [long]$Part.size }
    }
    if ($Drive.AvailableFreeSpace -lt $Needed) {
        throw "NVIDIA setup needs about $([Math]::Ceiling($Needed / 1GB)) GB of free space. Free space and retry, or continue with CPU processing."
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    for ($Index = 0; $Index -lt $Parts.Count; $Index++) {
        $Part = $Parts[$Index]
        Write-Host "NVIDIA download $($Index + 1) of $($Parts.Count)"
        Get-NvidiaPart ([Uri]::new($BaseUri, $Part.name)) (Join-Path $CacheDirectory $Part.name) $Part.size $Part.sha256
    }
    $Archive = Join-Path $CacheDirectory $ArchiveName
    [IO.File]::WriteAllText("$Archive.sha256", "$($Metadata.archive.sha256)  $ArchiveName`n")
    return @{ Archive = $Archive; CacheDirectory = $CacheDirectory }
}
