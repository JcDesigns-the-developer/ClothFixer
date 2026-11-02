$ErrorActionPreference = "Stop"

git submodule update --init --recursive

dotnet build .\binary_helper\ClothFixer.Binary.csproj --configuration Release

Write-Host "ClothFixer binary helper built successfully."
