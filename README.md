# ClothFixer

A small Windows desktop utility for scanning FiveM/GTA V clothing resource folders for repeated drawable slots and preparing safe filename renumbering before importing the resource into [grzyClothTool](https://github.com/grzybeek/grzyClothTool).

## Current scope

- Recursively scans a selected folder for clothing asset filenames such as `mp_m_freemode_01^jbib_001_u.ydd` and `jbib_001_u.ydd`.
- Detects repeated drawable slot numbers by gender, component/prop type, and resource folder.
- Previews proposed renames before touching files.
- Renumbers later duplicates into the next free slot (up to 255).
- Renames matching sidecar files with the same stem (for example, `.ytd`, `.yld`, and other same-stem files) together.
- Creates a timestamped backup copy of every file before applying changes.
- Uses a two-phase rename to avoid filename collisions.

## Important limitation

This first version changes **filenames only**. It does not rewrite names embedded inside binary `.ydd` or `.ytd` assets, nor does it edit texture dictionary entries inside those files. A filename-only pass cannot safely guarantee that internal drawable/texture names are repaired. The app labels this clearly and keeps originals backed up. Binary asset editing requires a compatible GTA V drawable/texture parser and format-aware writer.

## Run

Requires Python 3.11+ (standard library only).

```powershell
py main.py
```

## Safety

Always test the output in a copy of your resource. ClothFixer never deletes originals intentionally; backups are stored in a sibling `ClothFixer_Backups` folder.

## License

MIT
