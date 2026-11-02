# ClothFixer

A small Windows desktop utility for scanning FiveM/GTA V clothing resource folders for repeated drawable slots and repairing the associated asset names before importing the resource into [grzyClothTool](https://github.com/grzybeek/grzyClothTool).

## Features

- Recursively scans clothing resource folders for common freemode component and prop filenames.
- Detects repeated drawable slots by gender and clothing type.
- Previews proposed renames before touching files.
- Renumbers later duplicates into the next free slot (up to 255).
- Renames matching same-stem sidecar files.
- Rewrites drawable names and drawable hashes inside YDD resources.
- Rewrites embedded texture names and hashes inside YDD resources and updates shader texture references.
- Rewrites texture dictionary entry names and hashes inside matching YTD resources.
- Rebuilds the affected GTA resource structures through the CodeWalker parser used by grzyClothTool.
- Creates a timestamped backup of every affected file before applying any change.
- Uses staged file operations and temporary binary outputs so a parser failure does not leave a half-renamed resource.

## Requirements

- Windows 10/11
- Python 3.11 or newer
- .NET 10 SDK
- Git

## Clone

Clone with the parser submodule so the binary helper can read and write GTA resources:

    git clone --recurse-submodules https://github.com/JcDesigns-the-developer/ClothFixer.git
    cd ClothFixer

If the repository was cloned without submodules:

    git submodule update --init --recursive

## Run

    py main.py

When you click **Fix Duplicates**, ClothFixer builds/runs the .NET binary helper. The first run may take longer while .NET restores and compiles CodeWalker.Core.

## What gets renamed inside the binaries

For a duplicate such as jbib_001_u being moved to jbib_002_u, ClothFixer updates matching three-digit slot tokens in:

- Drawable names in the YDD drawable dictionary, including the corresponding drawable hash table.
- Embedded texture names in the YDD texture dictionary, including texture hashes and shader texture references.
- Texture entry names in a matching YTD texture dictionary, including its hash table.

Only entries containing the old three-digit slot token are changed. The binary helper does not modify texture pixel data, geometry, skeletons, or unrelated metadata.

## Safety

ClothFixer backs up every affected file to a sibling ClothFixer_Backups folder before processing. It writes rewritten binaries to temporary files first and only starts renaming originals after all requested binary rewrites succeed. Always test the result in a copy of your resource before using it in a live server.

Encrypted, malformed, or unsupported YDD/YTD files cause the operation to stop rather than silently fall back to filename-only changes.

## Licensing

The Python desktop application remains MIT-licensed. The separate binary helper is GPL-3.0 and uses the pinned grzyClothTool submodule for its CodeWalker parser and resource serialization. See binary_helper/LICENSE and the submodule's license before redistributing the helper or a combined package.
