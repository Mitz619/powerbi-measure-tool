#!/usr/bin/env python3
"""
Power BI PBIP Measure Tool — Cleaner + Copier

Modes
─────
  1. Analyse / Remove unused measures   (default)
  2. Copy measures between PBIP projects or tables   (--copy)

Examples
────────
  # Show unused measures (dry run):
  pbi-measure ./MyWorkspace

  # Delete unused measures:
  pbi-measure ./MyWorkspace --execute

  # Copy measures — interactive selection, auto-detect target structure:
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace

  # Copy specific measures by name:
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace \\
      --measures "Total Revenue" "Gross Profit"

  # Copy ALL measures from the source SemanticModel:
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace --all-measures

  # Copy all + overwrite if measures already exist in the target:
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace --all-measures --overwrite --execute
"""

import re
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import argparse


# ═══════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════

class Measure:
    def __init__(
        self,
        name: str,
        table: str,
        expression: str,
        source: str,
        file_path: Optional[Path] = None,
        format_string: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self.name = name
        self.table = table
        self.expression = expression
        self.source = source            # "semantic_model" | "report_level"
        self.file_path = file_path
        self.format_string = format_string
        self.description = description
        self.is_used: Optional[bool] = None

    def __repr__(self) -> str:
        return f"[{self.table}].[{self.name}]"


# ═══════════════════════════════════════════════════════════════
# Path resolution
# ═══════════════════════════════════════════════════════════════

def resolve_paths(input_path: str) -> Tuple[Path, Optional[Path]]:
    p = Path(input_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")

    if (p / "definition" / "report.json").exists() or p.name.endswith(".Report"):
        report_path = p
    else:
        reports = [f for f in p.iterdir() if f.is_dir() and f.name.endswith(".Report")]
        if not reports:
            raise FileNotFoundError(f"No .Report folder found in: {p}")
        report_path = reports[0]

    parent = report_path.parent
    sm_candidates = [
        f for f in parent.iterdir()
        if f.is_dir() and ("SemanticModel" in f.name or f.name.endswith(".Dataset"))
    ]
    sm_path = sm_candidates[0] if sm_candidates else None
    return report_path, sm_path


# ═══════════════════════════════════════════════════════════════
# TMDL parser
# ═══════════════════════════════════════════════════════════════

def parse_tmdl_table_name(content: str) -> str:
    """Extract the table name from the first 'table ...' line of a .tmdl file."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("table "):
            return line[len("table "):].strip().strip("'")
    return "Unknown"


_TMDL_META_PREFIXES = (
    "formatString:",
    "description:",
    "lineageTag:",
    "summarizeBy:",
    "isHidden:",
    "displayFolder:",
    "annotation ",
    "changedProperty ",
)

_META_PROP_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*\s*:")


def parse_tmdl_measures(tmdl_path: Path) -> List[dict]:
    """
    Parse a .tmdl file and return a list of measure dicts:
      {table, name, expression, format_string, description}
    """
    try:
        content = tmdl_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        print(f"⚠️  Could not read {tmdl_path.name}: {e}")
        return []

    table_name = parse_tmdl_table_name(content)
    lines = content.splitlines()
    results: List[dict] = []

    measure_header_re = re.compile(r"^\tmeasure\s+(.+?)\s*=\s*(.*)")

    i = 0
    while i < len(lines):
        line = lines[i]
        m = measure_header_re.match(line)

        if m:
            raw_name = m.group(1).strip("'").strip('"')
            inline_expr = m.group(2).strip()

            expr_lines: List[str] = []
            if inline_expr:
                expr_lines.append(inline_expr)

            format_string: Optional[str] = None
            description: Optional[str] = None

            i += 1
            while i < len(lines):
                next_line = lines[i]

                if next_line.strip() == "":
                    i += 1
                    continue

                if next_line.startswith("\t\t"):
                    stripped = next_line.strip()

                    if stripped.startswith("formatString:"):
                        format_string = stripped[len("formatString:"):].strip().strip('"')
                        i += 1
                        continue

                    if stripped.startswith("description:"):
                        description = stripped[len("description:"):].strip().strip('"')
                        i += 1
                        continue

                    is_known_meta = any(stripped.startswith(p) for p in _TMDL_META_PREFIXES)
                    is_heuristic_meta = (
                        _META_PROP_RE.match(stripped)
                        and "=" not in stripped
                        and "(" not in stripped
                        and not stripped.startswith("//")
                    )
                    if is_known_meta or is_heuristic_meta:
                        i += 1
                        continue

                    expr_lines.append(stripped)
                    i += 1
                else:
                    break

            expression = "\n".join(expr_lines).strip()
            results.append({
                "table": table_name,
                "name": raw_name,
                "expression": expression,
                "format_string": format_string,
                "description": description,
            })
        else:
            i += 1

    return results


# ═══════════════════════════════════════════════════════════════
# Measure readers
# ═══════════════════════════════════════════════════════════════

def read_semantic_model_measures(sm_path: Optional[Path]) -> List[Measure]:
    if sm_path is None:
        return []

    tables_path = sm_path / "definition" / "tables"
    if not tables_path.exists():
        print(f"⚠️  No 'definition/tables' folder found in SemanticModel: {sm_path}")
        return []

    measures: List[Measure] = []
    for tmdl_file in sorted(tables_path.glob("*.tmdl")):
        for d in parse_tmdl_measures(tmdl_file):
            measures.append(Measure(
                name=d["name"],
                table=d["table"],
                expression=d["expression"],
                source="semantic_model",
                file_path=tmdl_file,
                format_string=d.get("format_string"),
                description=d.get("description"),
            ))
    return measures


def read_report_level_measures(report_path: Path) -> List[Measure]:
    ext_path = report_path / "definition" / "reportExtensions.json"
    if not ext_path.exists():
        return []

    try:
        with open(ext_path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️  Could not read reportExtensions.json: {e}")
        return []

    measures: List[Measure] = []
    entities = data.get("entities", data.get("extensions", []))
    for entity in entities:
        table_name = entity.get("name", "Unknown")
        for m in entity.get("measures", []):
            expr = m.get("expression", "")
            if isinstance(expr, list):
                expr = "\n".join(expr)
            measures.append(Measure(
                name=m.get("name", ""),
                table=table_name,
                expression=expr,
                source="report_level",
                file_path=ext_path,
                format_string=m.get("formatString"),
            ))
    return measures


# ═══════════════════════════════════════════════════════════════
# Report scanner
# ═══════════════════════════════════════════════════════════════

def load_json_file(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def load_report_parts(report_path: Path) -> List[dict]:
    parts: List[dict] = []
    definition = report_path / "definition"

    def add(p: Path) -> None:
        parts.append({"path": str(p), "data": load_json_file(p)})

    rj = definition / "report.json"
    if rj.exists():
        add(rj)

    pages_path = definition / "pages"
    if pages_path.exists():
        for page_folder in pages_path.iterdir():
            if not page_folder.is_dir():
                continue
            pj = page_folder / "page.json"
            if pj.exists():
                add(pj)
            vp = page_folder / "visuals"
            if vp.exists():
                for vf in vp.iterdir():
                    if vf.is_dir():
                        vj = vf / "visual.json"
                        if vj.exists():
                            add(vj)

    bm_path = definition / "bookmarks"
    if bm_path.exists():
        for bf in bm_path.glob("*.bookmark.json"):
            add(bf)

    return parts


def is_referenced_in(
    data,
    measure_name: str,
    table_name: str,
    dax_pattern: re.Pattern,
    path: str = "",
    ignore_unapplied_filters: bool = False,
) -> bool:
    if isinstance(data, dict):
        if "Measure" in data and isinstance(data["Measure"], dict):
            m = data["Measure"]
            if (m.get("Property") == measure_name and
                    m.get("Expression", {}).get("SourceRef", {}).get("Entity") == table_name):
                if ignore_unapplied_filters and "filterConfig" in path:
                    return "filter" in data
                return True

        if "Expression" in data and isinstance(data["Expression"], str):
            if dax_pattern.search(data["Expression"]):
                return True

        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            if is_referenced_in(value, measure_name, table_name,
                                 dax_pattern, new_path, ignore_unapplied_filters):
                return True

    elif isinstance(data, list):
        for item in data:
            if is_referenced_in(item, measure_name, table_name,
                                 dax_pattern, path, ignore_unapplied_filters):
                return True

    return False


# ═══════════════════════════════════════════════════════════════
# Usage analysis
# ═══════════════════════════════════════════════════════════════

def analyse_usage(
    measures: List[Measure],
    report_parts: List[dict],
    ignore_unapplied_filters: bool = False,
) -> None:
    max_passes = 15

    for _ in range(max_passes):
        changed = False

        for m in measures:
            if m.is_used:
                continue

            dax_pattern = re.compile(r"\[" + re.escape(m.name) + r"\]")
            used = False

            for part in report_parts:
                if is_referenced_in(part["data"], m.name, m.table,
                                    dax_pattern,
                                    ignore_unapplied_filters=ignore_unapplied_filters):
                    used = True
                    break

            if not used:
                for other in measures:
                    if other.name == m.name and other.table == m.table:
                        continue
                    if other.is_used is True and dax_pattern.search(other.expression or ""):
                        used = True
                        break

            if used:
                m.is_used = True
                changed = True

        if not changed:
            break

    for m in measures:
        if m.is_used is None:
            m.is_used = False


# ═══════════════════════════════════════════════════════════════
# Display
# ═══════════════════════════════════════════════════════════════

def print_summary(measures: List[Measure]) -> None:
    if not measures:
        return

    used   = sorted([m for m in measures if m.is_used],     key=lambda x: (x.table, x.name))
    unused = sorted([m for m in measures if not m.is_used], key=lambda x: (x.table, x.name))

    name_w  = max(len(m.name)  for m in measures) + 2
    table_w = max(len(m.table) for m in measures) + 2

    sep    = "─" * (12 + table_w + name_w + 18)
    header = f"  {'Status':<12}{'Table':<{table_w}}{'Measure':<{name_w}}Source"

    print(f"\n{sep}")
    print(header)
    print(sep)

    for m in used:
        print(f"  {'✅ USED':<12}{m.table:<{table_w}}{m.name:<{name_w}}{m.source}")

    if unused:
        print()
        for m in unused:
            print(f"  {'❌ UNUSED':<12}{m.table:<{table_w}}{m.name:<{name_w}}{m.source}")

    print(sep)
    print(f"\n  Total: {len(measures)}  |  ✅ Used: {len(used)}  |  ❌ Unused: {len(unused)}")


# ═══════════════════════════════════════════════════════════════
# Deletion
# ═══════════════════════════════════════════════════════════════

def remove_measure_from_tmdl(tmdl_path: Path, measure_names: List[str]) -> int:
    try:
        content = tmdl_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        print(f"⚠️  Could not read {tmdl_path}: {e}")
        return 0

    lines = content.splitlines(keepends=True)
    names_to_remove = set(measure_names)
    measure_start_re = re.compile(r"^\tmeasure\s+'?(.+?)'?\s*=")

    result_lines: List[str] = []
    removed = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        m = measure_start_re.match(line)

        if m:
            raw_name = m.group(1).strip("'").strip('"')
            if raw_name in names_to_remove:
                removed += 1
                i += 1
                while i < len(lines):
                    nl = lines[i]
                    if nl.strip() == "" or nl.startswith("\t\t"):
                        i += 1
                    else:
                        break
                continue

        result_lines.append(line)
        i += 1

    tmdl_path.write_text("".join(result_lines), encoding="utf-8")
    return removed


def remove_measures(unused: List[Measure], report_path: Path) -> None:
    tmdl_groups: Dict[Path, List[str]] = {}
    for m in unused:
        if m.source == "semantic_model" and m.file_path:
            tmdl_groups.setdefault(m.file_path, []).append(m.name)

    for tmdl_path, names in tmdl_groups.items():
        remove_measure_from_tmdl(tmdl_path, names)
        table = parse_tmdl_table_name(tmdl_path.read_text(encoding="utf-8-sig"))
        for name in names:
            print(f"   🗑️  Removed [{table}].[{name}] from {tmdl_path.name}")

    report_level = [m for m in unused if m.source == "report_level"]
    if report_level:
        ext_path = report_path / "definition" / "reportExtensions.json"
        if ext_path.exists():
            with open(ext_path, encoding="utf-8-sig") as f:
                data = json.load(f)
            names_to_remove = {m.name for m in report_level}
            key = "entities" if "entities" in data else "extensions"
            for entity in data.get(key, []):
                entity["measures"] = [
                    m for m in entity.get("measures", [])
                    if m.get("name") not in names_to_remove
                ]
            data[key] = [e for e in data[key] if e.get("measures")]
            if data[key]:
                with open(ext_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                ext_path.unlink()
                print("   🗑️  Deleted reportExtensions.json (no measures remaining)")
            for m in report_level:
                print(f"   🗑️  Removed [Report-level].[{m.name}]")


# ═══════════════════════════════════════════════════════════════
# Step 3 — DAX Formatter
# ═══════════════════════════════════════════════════════════════

def format_dax(expression: str) -> str:
    """
    Cleans a raw DAX expression for tidy TMDL output:
      - Strips trailing whitespace per line
      - Dedents to column 0 (TMDL re-indents on write)
      - Collapses consecutive blank lines to one
      - Trims leading/trailing blank lines
    DAX logic is never modified — whitespace only.
    """
    if not expression:
        return ""

    lines = [l.rstrip() for l in expression.splitlines()]

    non_empty = [l for l in lines if l.strip()]
    if non_empty:
        min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
        if min_indent > 0:
            lines = [l[min_indent:] if len(l) >= min_indent else l.lstrip()
                     for l in lines]

    result: List[str] = []
    prev_blank = False
    for l in lines:
        is_blank = l.strip() == ""
        if is_blank and prev_blank:
            continue
        result.append(l)
        prev_blank = is_blank

    while result and result[0].strip() == "":
        result.pop(0)
    while result and result[-1].strip() == "":
        result.pop()

    return "\n".join(result)


def build_tmdl_measure_block(measure: Measure) -> str:
    """Render a Measure as a properly indented TMDL block string."""
    expr  = format_dax(measure.expression)
    lines = expr.splitlines() if expr else [""]

    if len(lines) == 1:
        block = f"\tmeasure '{measure.name}' = {lines[0]}\n"
    else:
        indented = "\n".join(f"\t\t{l}" for l in lines)
        block = f"\tmeasure '{measure.name}' =\n{indented}\n"

    if measure.format_string:
        block += f"\t\tformatString: {measure.format_string}\n"
    if measure.description:
        block += f"\t\tdescription: {json.dumps(measure.description)}\n"

    return block


# ═══════════════════════════════════════════════════════════════
# Step 1 — Interactive measure selection
# ═══════════════════════════════════════════════════════════════

def _parse_selection_token(token: str, max_idx: int) -> Set[int]:
    result: Set[int] = set()
    if "-" in token:
        parts = token.split("-", 1)
        try:
            start, end = int(parts[0]), int(parts[1])
            result.update(i for i in range(start - 1, end) if 0 <= i < max_idx)
        except ValueError:
            pass
    else:
        try:
            n = int(token)
            if 1 <= n <= max_idx:
                result.add(n - 1)
        except ValueError:
            pass
    return result


def select_measures_interactive(measures: List[Measure]) -> List[Measure]:
    """
    Interactive numbered list grouped by table.
    Accepts: single (3), range (3-7), list (1,3,5-8), or 'all'.
    """
    print("\n┌──────────────────────────────────────────────────────────┐")
    print("│           Step 1 — Select Measures to Copy              │")
    print("└──────────────────────────────────────────────────────────┘")

    indexed: List[Measure] = sorted(measures, key=lambda m: (m.table, m.name))
    current_table: Optional[str] = None

    for idx, m in enumerate(indexed, 1):
        if m.table != current_table:
            print(f"\n  📋  {m.table}")
            current_table = m.table
        fmt_hint = f"  ({m.format_string})" if m.format_string else ""
        print(f"    [{idx:>3}]  {m.name}{fmt_hint}")

    print()
    print("  Syntax: single (3), range (3-7), list (1,3,5-8), or 'all'")
    print("  Enter 'q' to quit.\n")

    while True:
        try:
            raw = input("  Your selection: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(0)

        if raw.lower() == "q":
            print("  Cancelled.")
            sys.exit(0)

        if raw.lower() == "all":
            print(f"\n  ✅  All {len(indexed)} measures selected.")
            return indexed

        selected_indices: Set[int] = set()
        for token in re.split(r"[,\s]+", raw):
            token = token.strip()
            if token:
                selected_indices |= _parse_selection_token(token, len(indexed))

        if not selected_indices:
            print("  ⚠️   No valid selection — try again.")
            continue

        selected = [indexed[i] for i in sorted(selected_indices)]
        print(f"\n  ✅  {len(selected)} measure(s) selected:")
        for m in selected:
            print(f"       • [{m.table}].[{m.name}]")

        try:
            confirm = input("\n  Confirm? (y / n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if confirm == "y":
            return selected
        print("  Re-enter your selection.\n")


# ═══════════════════════════════════════════════════════════════
# Step 2 — Target structure detection
# ═══════════════════════════════════════════════════════════════

SCENARIO_SAME_PROJECT  = "same_project_diff_table"
SCENARIO_DIFF_SAME_TBL = "diff_project_same_tables"
SCENARIO_DIFF_DIFF_TBL = "diff_project_diff_tables"

_SCENARIO_LABELS = {
    SCENARIO_SAME_PROJECT:  "Same project — reorganising to a different table",
    SCENARIO_DIFF_SAME_TBL: "Different project — matching table structure",
    SCENARIO_DIFF_DIFF_TBL: "Different project — different table structure",
}


def get_table_map(sm_path: Optional[Path]) -> Dict[str, Path]:
    """Return {table_name: tmdl_path} for every table in a SemanticModel."""
    if sm_path is None:
        return {}
    tables_path = sm_path / "definition" / "tables"
    if not tables_path.exists():
        return {}

    result: Dict[str, Path] = {}
    for tmdl_file in tables_path.glob("*.tmdl"):
        try:
            content = tmdl_file.read_text(encoding="utf-8-sig")
            result[parse_tmdl_table_name(content)] = tmdl_file
        except Exception:
            pass
    return result


def detect_scenario(
    source_report: Path,
    source_sm: Optional[Path],
    target_report: Path,
    target_sm: Optional[Path],
) -> str:
    if source_report.parent.resolve() == target_report.parent.resolve():
        return SCENARIO_SAME_PROJECT

    src_tables = set(get_table_map(source_sm).keys())
    tgt_tables = set(get_table_map(target_sm).keys())

    if src_tables and tgt_tables and src_tables == tgt_tables:
        return SCENARIO_DIFF_SAME_TBL

    return SCENARIO_DIFF_DIFF_TBL


def _print_step2_banner(scenario: str) -> None:
    label = _SCENARIO_LABELS.get(scenario, scenario)
    print(f"\n┌──────────────────────────────────────────────────────────┐")
    print(f"│  Step 2 — Target detected:                               │")
    print(f"│  {label:<58}│")
    print(f"└──────────────────────────────────────────────────────────┘")


# ═══════════════════════════════════════════════════════════════
# Step 2 — Table mapping
# ═══════════════════════════════════════════════════════════════

def _prompt_target_table(
    source_table: str,
    target_tables: Dict[str, Path],
    default: Optional[str] = None,
) -> str:
    table_list = sorted(target_tables.keys())
    print(f"\n  Source table  →  [{source_table}]")
    print("  Available target tables:")
    for i, t in enumerate(table_list, 1):
        hint = "   ← suggested" if t == default else ""
        print(f"    [{i:>2}]  {t}{hint}")

    while True:
        try:
            raw = input(f"\n  Map [{source_table}] to (number or name): ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if not raw:
            continue

        try:
            n = int(raw)
            if 1 <= n <= len(table_list):
                chosen = table_list[n - 1]
                print(f"  ✅  Mapped → [{chosen}]")
                return chosen
        except ValueError:
            pass

        if raw in target_tables:
            print(f"  ✅  Mapped → [{raw}]")
            return raw

        matches = [t for t in table_list if raw.lower() in t.lower()]
        if len(matches) == 1:
            print(f"  ✅  Matched → [{matches[0]}]")
            return matches[0]
        elif len(matches) > 1:
            print(f"  ⚠️   Ambiguous ({', '.join(matches)}) — be more specific.")
        else:
            print("  ⚠️   Not found — try again.")


def build_table_mapping(
    source_tables: List[str],
    target_tables: Dict[str, Path],
    scenario: str,
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    if scenario == SCENARIO_DIFF_SAME_TBL:
        print("\n  ✅  Auto-mapping tables (identical structure detected):")
        for st in source_tables:
            if st in target_tables:
                print(f"      [{st}]  →  [{st}]")
                mapping[st] = st
            else:
                print(f"  ⚠️   Table [{st}] not found in target — manual mapping required.")
                mapping[st] = _prompt_target_table(st, target_tables)
        return mapping

    if scenario == SCENARIO_DIFF_DIFF_TBL:
        print("\n  Map each source table to a target table:")
        for st in source_tables:
            default = st if st in target_tables else None
            mapping[st] = _prompt_target_table(st, target_tables, default=default)
        return mapping

    # SCENARIO_SAME_PROJECT
    print("\n  Reorganising within the same project.")
    print("  Choose a target table for each source table:\n")
    for st in source_tables:
        available = {k: v for k, v in target_tables.items() if k != st}
        if not available:
            print(f"  ⚠️   No other tables found for [{st}]; keeping in same table.")
            mapping[st] = st
        else:
            mapping[st] = _prompt_target_table(st, available)
    return mapping


# ═══════════════════════════════════════════════════════════════
# TMDL writer
# ═══════════════════════════════════════════════════════════════

def measure_exists_in_tmdl(tmdl_path: Path, measure_name: str) -> bool:
    try:
        content = tmdl_path.read_text(encoding="utf-8-sig")
    except Exception:
        return False
    pattern = re.compile(
        r"^\tmeasure\s+'?" + re.escape(measure_name) + r"'?\s*=",
        re.MULTILINE,
    )
    return bool(pattern.search(content))


def append_measure_to_tmdl(tmdl_path: Path, measure: Measure) -> bool:
    try:
        content = tmdl_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        print(f"⚠️   Cannot read {tmdl_path}: {e}")
        return False

    block = build_tmdl_measure_block(measure)
    new_content = content.rstrip("\n") + "\n\n" + block + "\n"

    try:
        tmdl_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"⚠️   Cannot write {tmdl_path}: {e}")
        return False


def overwrite_measure_in_tmdl(tmdl_path: Path, measure: Measure) -> bool:
    removed = remove_measure_from_tmdl(tmdl_path, [measure.name])
    if removed == 0:
        print(f"⚠️   Could not locate [{measure.name}] in {tmdl_path.name} to overwrite.")
        return False
    return append_measure_to_tmdl(tmdl_path, measure)


# ═══════════════════════════════════════════════════════════════
# Copy workflow
# ═══════════════════════════════════════════════════════════════

def copy_measures_workflow(
    measures_to_copy: List[Measure],
    target_sm: Optional[Path],
    target_report: Path,
    scenario: str,
    execute: bool,
    overwrite: bool,
) -> None:
    target_table_map = get_table_map(target_sm)
    if not target_table_map:
        print("⚠️   No tables found in target SemanticModel. Cannot continue.")
        return

    _print_step2_banner(scenario)
    unique_source_tables = list(dict.fromkeys(m.table for m in measures_to_copy))
    table_mapping = build_table_mapping(unique_source_tables, target_table_map, scenario)

    print("\n┌──────────────────────────────────────────────────────────┐")
    print("│        Step 3 — Format DAX & Copy Measures               │")
    print("└──────────────────────────────────────────────────────────┘\n")

    counters = {"copied": 0, "overwritten": 0, "skipped_exists": 0,
                "skipped_no_table": 0, "failed": 0}

    for m in measures_to_copy:
        target_table_name = table_mapping.get(m.table)
        if not target_table_name:
            print(f"  ⚠️   No mapping for [{m.table}] — skipping [{m.name}]")
            counters["skipped_no_table"] += 1
            continue

        tmdl_path = target_table_map.get(target_table_name)
        if not tmdl_path:
            print(f"  ⚠️   Target table [{target_table_name}] has no .tmdl — skipping [{m.name}]")
            counters["skipped_no_table"] += 1
            continue

        clean_measure = Measure(
            name=m.name,
            table=target_table_name,
            expression=format_dax(m.expression),
            source="semantic_model",
            file_path=tmdl_path,
            format_string=m.format_string,
            description=m.description,
        )

        already_exists = measure_exists_in_tmdl(tmdl_path, m.name)

        if execute:
            if already_exists:
                if overwrite:
                    ok = overwrite_measure_in_tmdl(tmdl_path, clean_measure)
                    if ok:
                        print(f"  🔄  Overwritten  [{m.table}].[{m.name}]"
                              f"  →  [{target_table_name}].[{m.name}]")
                        counters["overwritten"] += 1
                    else:
                        counters["failed"] += 1
                else:
                    print(f"  ⏭️   Skipped      [{target_table_name}].[{m.name}]"
                          f"  (already exists — use --overwrite to replace)")
                    counters["skipped_exists"] += 1
            else:
                ok = append_measure_to_tmdl(tmdl_path, clean_measure)
                if ok:
                    print(f"  ✅  Copied       [{m.table}].[{m.name}]"
                          f"  →  [{target_table_name}].[{m.name}]")
                    counters["copied"] += 1
                else:
                    counters["failed"] += 1
        else:
            if already_exists:
                action = "🔄 would overwrite" if overwrite else "⏭️  would skip (exists)"
            else:
                action = "📋 would copy"
            print(f"  {action}  [{m.table}].[{m.name}]  →  [{target_table_name}].[{m.name}]")

    print()
    if execute:
        total_skipped = counters["skipped_exists"] + counters["skipped_no_table"]
        print(f"  ✅ Copied: {counters['copied']}  |  "
              f"🔄 Overwritten: {counters['overwritten']}  |  "
              f"⏭️  Skipped: {total_skipped}  |  "
              f"❌ Failed: {counters['failed']}")
        if counters["copied"] or counters["overwritten"]:
            print("\n  ⚠️   Re-open the report in Power BI Desktop to verify changes.")
            if scenario == SCENARIO_SAME_PROJECT:
                print("  💡  To complete a move, run the cleaner on the source tables"
                      " to remove the originals.")
    else:
        print("  💡  Dry run complete — run with --execute to apply these changes.")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pbi-measure",
        description="Power BI PBIP Measure Tool — Cleaner + Copier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CLEAN MODE (default)
  pbi-measure ./MyWorkspace
  pbi-measure ./MyWorkspace --execute
  pbi-measure ./MyWorkspace --execute --ignore-unapplied-filters

COPY MODE
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace --measures "Revenue" "Cost"
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace --all-measures --execute
  pbi-measure ./MyWorkspace --copy --target ./OtherWorkspace --all-measures --overwrite --execute
        """,
    )

    parser.add_argument("path", help="Source workspace folder or .Report folder")

    clean = parser.add_argument_group("Clean mode")
    clean.add_argument("--execute", action="store_true",
                       help="Apply changes (default: dry run)")
    clean.add_argument("--ignore-unapplied-filters", action="store_true",
                       help="Treat measures only in unapplied filter panes as unused")

    copy = parser.add_argument_group("Copy mode")
    copy.add_argument("--copy", action="store_true", help="Enable copy/move mode")
    copy.add_argument("--target", help="Target workspace or .Report folder")

    sel = copy.add_mutually_exclusive_group()
    sel.add_argument("--measures", nargs="+", metavar="NAME",
                     help="Cherry-pick specific measures by exact name")
    sel.add_argument("--all-measures", action="store_true",
                     help="Copy every measure from the source SemanticModel")

    copy.add_argument("--overwrite", action="store_true",
                      help="Overwrite measures that already exist in the target")

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.copy and not args.target:
        print("❌  --copy requires --target <path>", file=sys.stderr)
        return 1

    try:
        source_report, source_sm = resolve_paths(args.path)

        print(f"\n{'═'*62}")
        print(f"  Power BI Measure Tool  v0.1.0")
        print(f"{'═'*62}")
        print(f"  Source Report : {source_report.name}")
        print(f"  Source SM     : {source_sm.name if source_sm else 'NOT FOUND'}")

        if args.copy:
            target_report, target_sm = resolve_paths(args.target)
            print(f"  Target Report : {target_report.name}")
            print(f"  Target SM     : {target_sm.name if target_sm else 'NOT FOUND'}")
            mode_label = ("⚠️   EXECUTE — measures will be written"
                          if args.execute else "🔍  DRY RUN — no files will be changed")
            print(f"  Mode          : {mode_label}")
            print(f"{'═'*62}")

            source_measures = read_semantic_model_measures(source_sm)
            if not source_measures:
                print("\n⚠️   No measures found in the source SemanticModel.")
                return 0

            print(f"\n📊  {len(source_measures)} measure(s) found in source.")

            if args.all_measures:
                selected = source_measures
                print(f"\n✅  All {len(selected)} measures selected (--all-measures).")
            elif args.measures:
                name_set = set(args.measures)
                selected = [m for m in source_measures if m.name in name_set]
                missing  = name_set - {m.name for m in selected}
                if missing:
                    print(f"  ⚠️   Not found in source: {', '.join(sorted(missing))}")
                if not selected:
                    print("❌  No matching measures found.")
                    return 1
                print(f"\n✅  {len(selected)} measure(s) selected via --measures.")
            else:
                selected = select_measures_interactive(source_measures)

            if not selected:
                print("  No measures selected. Exiting.")
                return 0

            scenario = detect_scenario(source_report, source_sm,
                                       target_report, target_sm)
            copy_measures_workflow(
                measures_to_copy=selected,
                target_sm=target_sm,
                target_report=target_report,
                scenario=scenario,
                execute=args.execute,
                overwrite=args.overwrite,
            )

        else:
            mode_label = ("⚠️   EXECUTE — measures will be deleted"
                          if args.execute else "🔍  DRY RUN — no files will be changed")
            print(f"  Mode          : {mode_label}")
            print(f"{'═'*62}")

            sm_measures  = read_semantic_model_measures(source_sm)
            rpt_measures = read_report_level_measures(source_report)
            all_measures = sm_measures + rpt_measures

            if not all_measures:
                print("\n⚠️   No measures found. Verify your SemanticModel path.")
                return 0

            print(f"\n📊  Measures found:")
            print(f"    • {len(sm_measures)} in SemanticModel (TMDL)")
            print(f"    • {len(rpt_measures)} report-level")
            print(f"    • {len(all_measures)} total")

            print(f"\n📂  Loading report files...")
            report_parts = load_report_parts(source_report)
            print(f"    {len(report_parts)} files loaded")

            print(f"\n🔄  Analysing usage...")
            analyse_usage(all_measures, report_parts, args.ignore_unapplied_filters)

            print_summary(all_measures)

            unused = [m for m in all_measures if not m.is_used]

            if not unused:
                print("\n✅  All measures are in use. Nothing to remove.")
                return 0

            if args.execute:
                print(f"\n🗑️   Removing {len(unused)} unused measure(s)...")
                remove_measures(unused, source_report)
                print(f"\n✅  Done. {len(unused)} measure(s) removed.")
                print("    ⚠️   Re-open the report in Power BI Desktop to verify.")
            else:
                print(f"\n💡  Run with --execute to permanently delete "
                      f"the {len(unused)} unused measure(s).")

    except FileNotFoundError as e:
        print(f"\n❌  {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌  Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
