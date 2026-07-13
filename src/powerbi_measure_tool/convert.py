#!/usr/bin/env python3
"""
Power BI format conversion — .pbix ↔ .pbip (PbixProj/TMDL)

This module is a thin, well-behaved wrapper around the external
`pbi-tools` CLI (https://pbi.tools). It does NOT re-implement the
Power BI / Analysis Services engine — that is impossible in pure
Python — so `pbi-tools` (or `pbi-tools.core`) must be installed and
on PATH (or pointed at via the PBI_TOOLS_PATH environment variable
or the `--pbi-tools` flag).

Honest caveats
──────────────
  • pbix → project
      Uses `pbi-tools extract`. The output is pbi-tools' *PbixProj*
      layout (TMDL model serialization by default). This is source-
      control-equivalent to Microsoft PBIP but not byte-identical to
      the folder structure Power BI Desktop's "Save as .pbip" emits.

  • project → pbix
      Uses `pbi-tools compile`. pbi-tools can only produce a real
      **.pbix** for report-only ("thin") projects. Projects that
      contain a data model compile to a **.pbit** template instead
      (opening it in Desktop triggers a refresh). Regenerating a full
      .pbix with embedded data requires Power BI Desktop and is out of
      scope for an offline tool.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


# ═══════════════════════════════════════════════════════════════
# Errors
# ═══════════════════════════════════════════════════════════════

class PbiToolsNotFoundError(RuntimeError):
    """Raised when the pbi-tools executable cannot be located."""


class ConversionError(RuntimeError):
    """Raised when a pbi-tools conversion command fails."""


# ═══════════════════════════════════════════════════════════════
# pbi-tools discovery
# ═══════════════════════════════════════════════════════════════

# Preference order: the cross-platform Core edition first, then the
# Windows Desktop edition. Both accept the same extract/compile syntax.
_PBI_TOOLS_CANDIDATES = ("pbi-tools.core", "pbi-tools")


def find_pbi_tools(explicit: Optional[str] = None) -> str:
    """
    Locate the pbi-tools executable.

    Resolution order:
      1. `explicit` argument (e.g. from --pbi-tools)
      2. PBI_TOOLS_PATH environment variable
      3. `pbi-tools.core` / `pbi-tools` on PATH

    Raises PbiToolsNotFoundError if nothing usable is found.
    """
    candidates: List[str] = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("PBI_TOOLS_PATH")
    if env:
        candidates.append(env)
    candidates.extend(_PBI_TOOLS_CANDIDATES)

    for cand in candidates:
        # An explicit path to an existing file is used as-is.
        p = Path(cand)
        if p.is_file():
            return str(p)
        found = shutil.which(cand)
        if found:
            return found

    raise PbiToolsNotFoundError(
        "Could not find the 'pbi-tools' executable.\n"
        "   Install it from https://pbi.tools and ensure it is on your PATH,\n"
        "   or pass its location with --pbi-tools / the PBI_TOOLS_PATH env var."
    )


# ═══════════════════════════════════════════════════════════════
# Command builders (pure functions — easy to unit test)
# ═══════════════════════════════════════════════════════════════

MODEL_SERIALIZATION_CHOICES = ("Default", "Raw", "Legacy", "Tmdl")
EXTRACT_MODE_CHOICES = ("Auto", "V3", "Legacy")
COMPILE_FORMAT_CHOICES = ("PBIX", "PBIT")


def build_extract_command(
    exe: str,
    pbix_path: Path,
    out_folder: Optional[Path] = None,
    model_serialization: str = "Tmdl",
    mode: str = "Auto",
) -> List[str]:
    """Build the argument list for `pbi-tools extract`."""
    cmd = [exe, "extract", str(pbix_path)]
    if out_folder is not None:
        cmd += ["-extractFolder", str(out_folder)]
    if mode:
        cmd += ["-mode", mode]
    if model_serialization:
        cmd += ["-modelSerialization", model_serialization]
    return cmd


def build_compile_command(
    exe: str,
    project_folder: Path,
    out_path: Optional[Path] = None,
    fmt: str = "PBIX",
    overwrite: bool = False,
) -> List[str]:
    """Build the argument list for `pbi-tools compile`."""
    cmd = [exe, "compile", str(project_folder)]
    if out_path is not None:
        cmd += ["-outPath", str(out_path)]
    if fmt:
        cmd += ["-format", fmt]
    if overwrite:
        cmd += ["-overwrite"]
    return cmd


# ═══════════════════════════════════════════════════════════════
# Project inspection
# ═══════════════════════════════════════════════════════════════

def project_has_model(project_folder: Path) -> bool:
    """
    Heuristically decide whether a project folder contains a data model
    (as opposed to being a report-only / thin project).

    Recognises both Microsoft PBIP (*.SemanticModel, definition/tables)
    and pbi-tools PbixProj (Model/, DataModelSchema, database.tmdl)
    layouts.
    """
    if not project_folder.is_dir():
        return False

    # Microsoft PBIP: a SemanticModel/Dataset sibling with TMDL tables.
    for child in project_folder.rglob("*"):
        if child.is_dir() and (
            "SemanticModel" in child.name or child.name.endswith(".Dataset")
        ):
            return True

    # pbi-tools PbixProj markers.
    markers = (
        project_folder / "Model",
        project_folder / "DataModelSchema",
        project_folder / "Model" / "database.tmdl",
        project_folder / "definition" / "database.tmdl",
    )
    if any(m.exists() for m in markers):
        return True

    # Any TMDL model file anywhere is a strong signal of a model.
    for pattern in ("database.tmdl", "model.tmdl"):
        if next(project_folder.rglob(pattern), None) is not None:
            return True

    return False


def resolve_compile_format(
    project_folder: Path,
    requested: Optional[str],
) -> str:
    """
    Decide the compile output format.

    `requested` may be None/"auto" (detect), "PBIX", or "PBIT".
    When auto-detecting, a project with a model → PBIT, otherwise PBIX.
    """
    if requested and requested.lower() != "auto":
        return requested.upper()
    return "PBIT" if project_has_model(project_folder) else "PBIX"


# ═══════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════

def _resolve_exe(pbi_tools: Optional[str], execute: bool) -> str:
    """
    Resolve the pbi-tools executable. On a dry run, fall back to the bare
    name "pbi-tools" (with a note) so the intended command can still be
    shown even when the tool is not installed. On execute, a missing
    executable is a hard error.
    """
    try:
        return find_pbi_tools(pbi_tools)
    except PbiToolsNotFoundError:
        if execute:
            raise
        print("  ℹ️   pbi-tools not found on this machine — showing the command "
              "with a placeholder name.")
        return "pbi-tools"


def _run(cmd: List[str]) -> int:
    """
    Run a pbi-tools command, streaming its output to the console.
    Returns the process exit code. Raises ConversionError on non-zero.
    """
    print(f"\n  ▶  {' '.join(cmd)}\n")
    try:
        proc = subprocess.run(cmd)
    except FileNotFoundError as e:
        raise ConversionError(f"Failed to launch pbi-tools: {e}") from e
    if proc.returncode != 0:
        raise ConversionError(
            f"pbi-tools exited with code {proc.returncode}. See output above."
        )
    return proc.returncode


# ═══════════════════════════════════════════════════════════════
# High-level conversions
# ═══════════════════════════════════════════════════════════════

def convert_pbix_to_pbip(
    pbix_path: Path,
    out_folder: Optional[Path] = None,
    model_serialization: str = "Tmdl",
    mode: str = "Auto",
    execute: bool = False,
    pbi_tools: Optional[str] = None,
) -> Optional[Path]:
    """
    Convert a .pbix into an extracted project folder (pbix → pbip).

    Returns the output folder path on success, or None on a dry run.
    """
    pbix_path = Path(pbix_path).resolve()
    if not pbix_path.is_file():
        raise FileNotFoundError(f"PBIX file not found: {pbix_path}")
    if pbix_path.suffix.lower() != ".pbix":
        print(f"  ⚠️   Expected a .pbix file, got: {pbix_path.name}")

    if model_serialization not in MODEL_SERIALIZATION_CHOICES:
        raise ValueError(
            f"model_serialization must be one of {MODEL_SERIALIZATION_CHOICES}"
        )
    if mode not in EXTRACT_MODE_CHOICES:
        raise ValueError(f"mode must be one of {EXTRACT_MODE_CHOICES}")

    resolved_out = Path(out_folder).resolve() if out_folder else None
    exe = _resolve_exe(pbi_tools, execute)
    cmd = build_extract_command(
        exe, pbix_path, resolved_out, model_serialization, mode
    )

    print(f"  📦  pbix → project")
    print(f"      Source : {pbix_path}")
    print(f"      Output : {resolved_out or '(pbi-tools default location)'}")
    print(f"      Model  : {model_serialization}   Mode: {mode}")

    if not execute:
        print(f"\n  🔍  DRY RUN — would run:\n      {' '.join(cmd)}")
        return None

    _run(cmd)
    print("\n  ✅  Extract complete.")
    print("  ⚠️   Output is pbi-tools' PbixProj (TMDL) layout — source-control")
    print("      equivalent to PBIP, but not byte-identical to Desktop's .pbip.")
    return resolved_out


def convert_pbip_to_pbix(
    project_folder: Path,
    out_path: Optional[Path] = None,
    fmt: Optional[str] = None,
    overwrite: bool = False,
    execute: bool = False,
    pbi_tools: Optional[str] = None,
) -> Optional[Path]:
    """
    Compile a project folder back into a .pbix / .pbit (pbip → pbix).

    Returns the output path on success (best-effort — pbi-tools decides
    the exact filename), or None on a dry run.
    """
    project_folder = Path(project_folder).resolve()
    if not project_folder.is_dir():
        raise FileNotFoundError(f"Project folder not found: {project_folder}")

    resolved_format = resolve_compile_format(project_folder, fmt)
    if resolved_format not in COMPILE_FORMAT_CHOICES:
        raise ValueError(f"format must be one of {COMPILE_FORMAT_CHOICES} or 'auto'")

    has_model = project_has_model(project_folder)
    resolved_out = Path(out_path).resolve() if out_path else None
    exe = _resolve_exe(pbi_tools, execute)
    cmd = build_compile_command(
        exe, project_folder, resolved_out, resolved_format, overwrite
    )

    print(f"  📦  project → {resolved_format.lower()}")
    print(f"      Source : {project_folder}")
    print(f"      Output : {resolved_out or '(current directory)'}")
    print(f"      Format : {resolved_format}   Overwrite: {overwrite}")

    if has_model and resolved_format == "PBIX":
        print(
            "\n  ⚠️   This project appears to contain a data model, but PBIX was\n"
            "      requested. pbi-tools only compiles report-only projects to\n"
            "      .pbix — this will likely fail. Use --format PBIT (or omit\n"
            "      --format to auto-detect) for projects with a model."
        )
    elif has_model:
        print(
            "\n  ℹ️   Data model detected → producing a .pbit template.\n"
            "      Full .pbix regeneration with embedded data needs Power BI Desktop."
        )

    if not execute:
        print(f"\n  🔍  DRY RUN — would run:\n      {' '.join(cmd)}")
        return None

    _run(cmd)
    print("\n  ✅  Compile complete.")
    return resolved_out
