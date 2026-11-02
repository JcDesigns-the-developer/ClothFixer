from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from uuid import uuid4

APP_TITLE = "ClothFixer"
# Supports common freemode clothing names with or without a ped prefix.
NAME_RE = re.compile(
    r"^(?P<ped>mp_[mf]_freemode_01[\^_])?"
    r"(?P<kind>[a-z][a-z0-9]*)_(?P<number>\d{3})_(?P<tail>[a-z0-9]+)$",
    re.IGNORECASE,
)
MAX_SLOT = 255


@dataclass
class Asset:
    path: Path
    relative: Path
    stem: str
    extension: str
    ped_prefix: str
    kind: str
    number: int
    tail: str

    @property
    def group(self):
        # A resource root is treated as one namespace, even when assets are
        # arranged in subdirectories. Gender and drawable type are separate.
        gender = "male" if self.ped_prefix.lower().startswith("mp_m") else (
            "female" if self.ped_prefix.lower().startswith("mp_f") else "unspecified"
        )
        return (gender, self.kind.lower())


@dataclass
class Rename:
    source: Path
    destination: Path
    reason: str


def parse_asset(path: Path, root: Path) -> Asset | None:
    match = NAME_RE.match(path.stem)
    if not match:
        return None
    ped = match.group("ped") or ""
    return Asset(
        path=path,
        relative=path.relative_to(root),
        stem=path.stem,
        extension=path.suffix,
        ped_prefix=ped,
        kind=match.group("kind"),
        number=int(match.group("number")),
        tail=match.group("tail"),
    )


def scan_folder(root: Path) -> tuple[list[Asset], list[Rename]]:
    assets = []
    for path in root.rglob("*"):
        if path.is_file():
            item = parse_asset(path, root)
            if item:
                assets.append(item)

    groups = defaultdict(list)
    for item in assets:
        groups[item.group].append(item)

    changes: list[Rename] = []
    reserved = defaultdict(set)
    for key, items in groups.items():
        for item in items:
            reserved[key].add(item.number)

    # Duplicate slot means more than one YDD drawable file at that number.
    # Sidecar files are associated by relative parent + stem.
    drawable_groups = defaultdict(list)
    for item in assets:
        if item.extension.lower() == ".ydd":
            drawable_groups[(item.group, item.number)].append(item)

    for (group, slot), duplicates in sorted(drawable_groups.items(), key=lambda x: (x[0][0], x[0][1])):
        if len(duplicates) < 2:
            continue
        # Keep the first stable path; move subsequent copies to free slots.
        duplicates.sort(key=lambda x: str(x.relative).lower())
        for duplicate in duplicates[1:]:
            next_slot = next((n for n in range(0, MAX_SLOT + 1) if n not in reserved[group]), None)
            if next_slot is None:
                raise RuntimeError(f"No free drawable slots remain for {group[1]} ({group[0]}).")
            reserved[group].add(next_slot)

            old_stem = duplicate.stem
            new_stem = f"{duplicate.ped_prefix}{duplicate.kind}_{next_slot:03d}_{duplicate.tail}"
            # Move every same-directory sidecar with this exact stem.
            for sibling in duplicate.path.parent.iterdir():
                if sibling.is_file() and sibling.stem.lower() == old_stem.lower():
                    target = sibling.with_name(new_stem + sibling.suffix)
                    changes.append(Rename(sibling, target, f"Duplicate {group[1]} slot {slot:03d} -> {next_slot:03d}"))

    # Protect against duplicate planned targets and pre-existing target files.
    destinations = [r.destination for r in changes]
    if len(set(p.resolve() for p in destinations)) != len(destinations):
        raise RuntimeError("The scan produced conflicting destination names.")
    source_set = {r.source.resolve() for r in changes}
    for change in changes:
        if change.destination.exists() and change.destination.resolve() not in source_set:
            raise RuntimeError(f"Target already exists: {change.destination}")
    return assets, changes


def _binary_helper_project() -> Path:
    return Path(__file__).resolve().parent / "binary_helper" / "ClothFixer.Binary.csproj"


def _run_binary_rewrites(changes: list[Rename], temp_dir: Path) -> tuple[dict[Path, Path], str]:
    """Rewrite embedded names in affected YDD/YTD files into temporary outputs."""
    project = _binary_helper_project()
    vendor_core = Path(__file__).resolve().parent / "vendor" / "grzyClothTool" / "CodeWalker" / "CodeWalker.Core" / "CodeWalker.Core.csproj"
    if not project.exists() or not vendor_core.exists():
        raise RuntimeError(
            "The GTA binary parser is missing. Clone ClothFixer with its submodule: "
            "git clone --recurse-submodules https://github.com/JcDesigns-the-developer/ClothFixer.git"
        )
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError(".NET 10 SDK is required to rewrite embedded GTA asset names. Install the .NET 10 SDK and try again.")

    operations = []
    output_by_source: dict[Path, Path] = {}
    for index, change in enumerate(changes):
        extension = change.source.suffix.lower()
        if extension not in {".ydd", ".ytd"}:
            continue
        old_asset = parse_asset(change.source, change.source.parent)
        new_asset = parse_asset(change.destination, change.destination.parent)
        if old_asset is None or new_asset is None:
            continue
        output = temp_dir / f"rewritten_{index}{extension}"
        operations.append({
            "type": extension[1:],
            "input": str(change.source.resolve()),
            "output": str(output.resolve()),
            "kind": old_asset.kind,
            "oldSlot": old_asset.number,
            "newSlot": new_asset.number,
            "oldDrawableName": f"{old_asset.kind}_{old_asset.number:03d}_{old_asset.tail}",
            "newDrawableName": f"{new_asset.kind}_{new_asset.number:03d}_{new_asset.tail}",
        })
        output_by_source[change.source.resolve()] = output

    if not operations:
        return {}, "No YDD/YTD binaries needed rewriting."

    manifest = temp_dir / "operations.json"
    manifest.write_text(json.dumps(operations, indent=2), encoding="utf-8")
    command = [dotnet, "run", "--project", str(project), "--configuration", "Release", "--", str(manifest)]
    completed = subprocess.run(command, capture_output=True, text=True, cwd=project.parent)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Binary helper failed without a diagnostic.").strip()
        raise RuntimeError(f"Embedded-name rewrite failed. No source files were renamed.\n\n{detail[-5000:]}")

    try:
        results = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        results = []
    drawable_count = sum(int(item.get("drawableNames", 0)) for item in results)
    texture_count = sum(int(item.get("textureNames", 0)) for item in results)
    summary = f"Embedded names updated: {drawable_count} drawable name(s), {texture_count} texture name(s)."
    return output_by_source, summary


def apply_changes(changes: list[Rename], root: Path) -> tuple[Path, str]:
    if not changes:
        raise ValueError("There are no changes to apply.")
    backup_root = root.parent / "ClothFixer_Backups" / (root.name + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup_root.mkdir(parents=True, exist_ok=False)

    for change in changes:
        rel = change.source.relative_to(root)
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(change.source, backup)

    with tempfile.TemporaryDirectory(prefix="clothfixer_binary_") as temp_name:
        binary_outputs, summary = _run_binary_rewrites(changes, Path(temp_name))
        staged: list[tuple[Path, Path, Path]] = []
        try:
            for change in changes:
                temp = change.source.with_name(f".clothfixer_{uuid4().hex}{change.source.suffix}")
                change.source.rename(temp)
                staged.append((temp, change.destination, change.source))

            for staged_path, destination, original in staged:
                rewritten = binary_outputs.get(original.resolve())
                if rewritten is not None:
                    rewritten.replace(destination)
                    staged_path.unlink()
                else:
                    staged_path.rename(destination)
        except Exception:
            for staged_path, destination, original in reversed(staged):
                if destination.exists():
                    destination.unlink()
                if staged_path.exists():
                    staged_path.rename(original)
                else:
                    backup = backup_root / original.relative_to(root)
                    if backup.exists():
                        shutil.copy2(backup, original)
            raise

    return backup_root, summary


class ClothFixerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x620")
        self.minsize(760, 480)
        self.root_folder: Path | None = None
        self.assets: list[Asset] = []
        self.changes: list[Rename] = []
        self._style()
        self._build()

    def _style(self):
        self.configure(bg="#17191d")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#17191d")
        style.configure("TLabel", background="#17191d", foreground="#e7e9ed")
        style.configure("Muted.TLabel", foreground="#9ca3af")
        style.configure("TButton", padding=(12, 8), background="#292d34", foreground="#f3f4f6")
        style.map("TButton", background=[("active", "#383e48")])
        style.configure("Treeview", background="#202329", fieldbackground="#202329",
                        foreground="#e7e9ed", rowheight=27, borderwidth=0)
        style.configure("Treeview.Heading", background="#292d34", foreground="#f3f4f6")
        style.map("Treeview", background=[("selected", "#394454")])

    def _build(self):
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="ClothFixer", font=("Segoe UI Semibold", 22)).pack(anchor="w")
        ttk.Label(outer, text="Repair duplicate clothing slots and update names inside GTA V assets.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 14))

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 12))
        self.folder_var = tk.StringVar(value="No folder selected")
        ttk.Label(top, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Select Folder", command=self.select_folder).pack(side="right")
        ttk.Button(top, text="Scan", command=self.scan).pack(side="right", padx=(0, 8))

        warning = tk.Label(
            outer,
            text="BINARY-AWARE MODE — updates drawable names in .ydd files and texture entries in .ydd/.ytd files.",
            bg="#203b32", fg="#c9f4df", anchor="w", padx=10, pady=8,
            font=("Segoe UI Semibold", 9)
        )
        warning.pack(fill="x", pady=(0, 12))

        columns = ("source", "destination", "reason")
        self.table = ttk.Treeview(outer, columns=columns, show="headings")
        self.table.heading("source", text="Current file")
        self.table.heading("destination", text="Proposed filename")
        self.table.heading("reason", text="Reason")
        self.table.column("source", width=310)
        self.table.column("destination", width=310)
        self.table.column("reason", width=190)
        self.table.pack(fill="both", expand=True)

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(12, 0))
        self.status_var = tk.StringVar(value="Select a folder to begin.")
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        self.apply_button = ttk.Button(bottom, text="Fix Duplicates", command=self.apply, state="disabled")
        self.apply_button.pack(side="right")

    def select_folder(self):
        selected = filedialog.askdirectory(title="Select clothing resource folder")
        if selected:
            self.root_folder = Path(selected)
            self.folder_var.set(str(self.root_folder))
            self.assets, self.changes = [], []
            self._refresh()
            self.status_var.set("Folder selected. Click Scan.")

    def scan(self):
        if not self.root_folder:
            messagebox.showinfo(APP_TITLE, "Select a folder first.")
            return
        try:
            self.assets, self.changes = scan_folder(self.root_folder)
            self._refresh()
            self.status_var.set(f"Scanned {len(self.assets)} matching asset files • {len(self.changes)} file rename(s) proposed.")
        except Exception as exc:
            messagebox.showerror("Scan failed", str(exc))
            self.status_var.set("Scan failed.")
            self.changes = []
            self._refresh()

    def _refresh(self):
        for row in self.table.get_children():
            self.table.delete(row)
        for change in self.changes:
            self.table.insert("", "end", values=(
                str(change.source.relative_to(self.root_folder)),
                str(change.destination.relative_to(self.root_folder)),
                change.reason,
            ))
        self.apply_button.configure(state="normal" if self.changes else "disabled")

    def apply(self):
        if not self.changes or not self.root_folder:
            return
        count = len(self.changes)
        if not messagebox.askyesno(APP_TITLE, f"Rename {count} file(s) and update embedded binary names?\n\nA backup will be created first."):
            return
        try:
            backup, summary = apply_changes(self.changes, self.root_folder)
            messagebox.showinfo(APP_TITLE, f"Finished.\n\n{summary}\n\nBackup: {backup}")
            self.scan()
        except Exception as exc:
            messagebox.showerror("Fix failed", f"{exc}\n\nCheck the folder and backup before retrying.")
            self.status_var.set("Fix failed; inspect files and backup.")


if __name__ == "__main__":
    ClothFixerApp().mainloop()
