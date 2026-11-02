$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VendorRoot = Join-Path $RepoRoot "vendor"
$ParserPath = Join-Path $VendorRoot "grzyClothTool"
$ParserCommit = "6b118754e332414e7026b694b7559bfff56984a4"
$ParserProject = Join-Path $ParserPath "CodeWalker\CodeWalker.Core\CodeWalker.Core.csproj"

New-Item -ItemType Directory -Force -Path $VendorRoot | Out-Null

if (-not (Test-Path $ParserProject)) {
    Write-Host "CodeWalker parser is missing. Downloading the pinned grzyClothTool source..."

    $Archive = Join-Path $env:TEMP "grzyClothTool-$ParserCommit.zip"
    $ExtractRoot = Join-Path $env:TEMP "grzyClothTool-$ParserCommit"
    $ArchiveUrl = "https://github.com/grzybeek/grzyClothTool/archive/$ParserCommit.zip"

    if (Test-Path $ExtractRoot) {
        Remove-Item -Recurse -Force $ExtractRoot
    }

    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $Archive
    Expand-Archive -Path $Archive -DestinationPath $ExtractRoot -Force

    $ExtractedParser = Get-ChildItem -Path $ExtractRoot -Directory | Select-Object -First 1
    if (-not $ExtractedParser) {
        throw "The parser source archive downloaded, but its extracted folder was not found."
    }

    if (Test-Path $ParserPath) {
        Remove-Item -Recurse -Force $ParserPath
    }

    Move-Item -Path $ExtractedParser.FullName -Destination $ParserPath
}

if (-not (Test-Path $ParserProject)) {
    throw "CodeWalker project was not found at: $ParserProject"
}

$Dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $Dotnet) {
    throw ".NET 10 SDK is required. Install it from https://dotnet.microsoft.com/download/dotnet/10.0"
}

Write-Host "Restoring and building ClothFixer binary helper..."
Push-Location $RepoRoot
try {
    & dotnet build ".\binary_helper\ClothFixer.Binary.csproj" --configuration Release
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "ClothFixer binary helper built successfully."
