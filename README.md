# Power BI Measure Tool

A command-line tool for managing measures in **Power BI PBIP projects** using the TMDL format.

[![PyPI version](https://img.shields.io/pypi/v/powerbi-measure-tool)](https://pypi.org/project/powerbi-measure-tool/)
[![Python](https://img.shields.io/pypi/pyversions/powerbi-measure-tool?logo=python)](https://pypi.org/project/powerbi-measure-tool/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Features

| Mode | What it does |
|------|-------------|
| **Clean** | Scan for unused measures across your semantic model and optionally delete them |
| **Copy** | Copy or move measures between projects or tables with automatic structure detection |
| **Convert** | Convert between `.pbix` and project folders via the external [pbi-tools](https://pbi.tools) CLI |

### Copy mode scenarios (auto-detected)
- **Same project → different table** — reorganise measures between tables
- **Different project, same table structure** — auto-maps identical table names
- **Different project, different tables** — guided interactive table mapping

### DAX formatting
All measures are cleaned before writing: dedented, trailing whitespace removed, blank lines collapsed. `formatString` and `description` metadata are preserved; ephemeral properties like `lineageTag` are intentionally dropped so the target file gets fresh ones from Power BI.

---

## Requirements

- Python 3.8+
- Power BI project saved in **PBIP format** with **TMDL** enabled
  *(File → Options → Preview features → Store semantic model in TMDL format)*
- **Convert mode only:** the external [pbi-tools](https://pbi.tools) CLI on your
  `PATH` (or pointed at via `--pbi-tools` / the `PBI_TOOLS_PATH` env var).
  Clean and Copy modes have no such dependency.

---

## Installation

```bash
pip install powerbi-measure-tool
```

Or with [pipx](https://pipx.pypa.io) (recommended for CLI tools — keeps it isolated):

```bash
pipx install powerbi-measure-tool
```

---

## Usage

### Clean mode — find and remove unused measures

```bash
# Dry run: show which measures are unused (no files changed)
pbi-measure ./MyWorkspace

# Execute: permanently delete unused measures
pbi-measure ./MyWorkspace --execute

# Treat measures that only appear in unapplied filter panes as unused
pbi-measure ./MyWorkspace --execute --ignore-unapplied-filters
```

**Example output:**
```
══════════════════════════════════════════════════════════════
  Power BI Measure Tool  v0.2.0
══════════════════════════════════════════════════════════════
  Source Report : Sales Dashboard.Report
  Source SM     : Sales Dashboard.SemanticModel
  Mode          : 🔍  DRY RUN — no files will be changed
══════════════════════════════════════════════════════════════

📊  Measures found:
    • 24 in SemanticModel (TMDL)
    • 0 report-level
    • 24 total

🔄  Analysing usage...

────────────────────────────────────────────────────
  Status      Table             Measure             Source
────────────────────────────────────────────────────
  ✅ USED     Sales             Total Revenue       semantic_model
  ✅ USED     Sales             Gross Profit        semantic_model
  ...
  ❌ UNUSED   Sales             Old KPI Draft       semantic_model
────────────────────────────────────────────────────

  Total: 24  |  ✅ Used: 23  |  ❌ Unused: 1

💡  Run with --execute to permanently delete the 1 unused measure(s).
```

---

### Copy mode — copy or move measures between projects / tables

```bash
# Interactive selection (prompts you to pick measures from a numbered list)
pbi-measure ./SourceWorkspace --copy --target ./TargetWorkspace

# Cherry-pick specific measures by name
pbi-measure ./SourceWorkspace --copy --target ./TargetWorkspace \
    --measures "Total Revenue" "Gross Profit" "YTD Sales"

# Copy all measures
pbi-measure ./SourceWorkspace --copy --target ./TargetWorkspace --all-measures

# Copy all and execute (--execute required to write files)
pbi-measure ./SourceWorkspace --copy --target ./TargetWorkspace --all-measures --execute

# Overwrite measures that already exist in the target
pbi-measure ./SourceWorkspace --copy --target ./TargetWorkspace \
    --all-measures --overwrite --execute

# Reorganise: move measures to a different table in the same project
pbi-measure ./MyWorkspace --copy --target ./MyWorkspace \
    --measures "Total Revenue" --execute
```

**Interactive selection example:**
```
┌──────────────────────────────────────────────────────────┐
│           Step 1 — Select Measures to Copy               │
└──────────────────────────────────────────────────────────┘

  📋  Sales
    [  1]  Gross Profit  (#,0.00)
    [  2]  Total Revenue  (#,0.00)
    [  3]  YTD Sales  (#,0.00)

  📋  Targets
    [  4]  Revenue Target
    [  5]  Variance to Target

  Syntax: single (3), range (3-7), list (1,3,5-8), or 'all'
  Enter 'q' to quit.

  Your selection: 1,2,4
```

---

### Convert mode — `.pbix` ↔ project folder

Convert mode wraps the external [pbi-tools](https://pbi.tools) CLI, so it must be
installed and on your `PATH` (or passed via `--pbi-tools` / `PBI_TOOLS_PATH`).
Like the other modes, it is a **dry run by default** — it prints the exact
`pbi-tools` command it would run, and only touches disk with `--execute`.

```bash
# Extract a .pbix into a source-control-friendly project folder (pbix → pbip)
pbi-measure ./Report.pbix --to-pbip --out ./MyProject --execute

# Compile a project folder back into a .pbix / .pbit (pbip → pbix)
pbi-measure ./MyProject --to-pbix --out ./out --execute

# Force a thin (report-only) project to compile to .pbix
pbi-measure ./ThinReport --to-pbix --format pbix --overwrite --execute

# Point at a specific pbi-tools executable
pbi-measure ./Report.pbix --to-pbip --pbi-tools "C:/tools/pbi-tools.exe" --execute
```

**Honest caveats:**
- `--to-pbip` produces pbi-tools' *PbixProj* (TMDL) layout — source-control
  equivalent to Microsoft PBIP, but **not byte-identical** to Power BI Desktop's
  "Save as .pbip" output.
- `--to-pbix` **auto-detects** the format: a project containing a data model
  compiles to a `.pbit` template (opening it in Desktop triggers a refresh),
  while a report-only project compiles to a real `.pbix`. Regenerating a full
  `.pbix` with embedded data requires Power BI Desktop and is out of scope for an
  offline tool. Pass `--format pbix|pbit` to override auto-detection.

---

## Path formats accepted

The `path` and `--target` arguments accept either:
- A **workspace folder** containing both `.Report` and `.SemanticModel` subfolders
- A **`.Report` folder** directly

```
MyWorkspace/                        ← pass this
├── Sales Dashboard.Report/
└── Sales Dashboard.SemanticModel/
```

---

## How unused measure detection works

The tool performs a multi-pass analysis:

1. **Pass 1** — scans all report JSON files (pages, visuals, bookmarks) for structured `Measure` references and DAX string expressions
2. **Pass 2+** — marks any measure referenced in the DAX of an already-used measure as used (handles measure-calls-measure chains)
3. Repeats until no new used measures are found
4. Anything still unmarked → **UNUSED**

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.


## Contributing

Bug reports and pull requests are welcome at [GitHub](https://github.com/Mitz619/powerbi-measure-tool).

1. Fork the repo
2. Create a feature branch: `git checkout -b my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push and open a PR

---

## License

MIT — see [LICENSE](LICENSE).
