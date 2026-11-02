ClothFixer binary helper

This helper uses the CodeWalker resource parser bundled in the pinned grzyClothTool Git submodule. Its YDD rewrite follows grzyClothTool's resource-aware workflow: edit drawable names and hashes, edit embedded texture names and hashes, update shader texture references, rebuild the texture dictionary, and serialize the resource. YTD files are parsed, their texture dictionary entries and hashes are updated, then serialized.

The helper is a separate GPL-3.0 component because it is based on the GPL-3.0 grzyClothTool codebase and its bundled parser. Preserve the upstream license and attribution when redistributing it.

Build from the repository root:

    git submodule update --init --recursive
    dotnet build ./binary_helper/ClothFixer.Binary.csproj -c Release
