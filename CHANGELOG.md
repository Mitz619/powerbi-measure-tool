# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-13

### Added
- **Convert mode** — convert between `.pbix` and project folders via the
  external [pbi-tools](https://pbi.tools) CLI
  - `--to-pbip` — extract a `.pbix` into a source-control-friendly PbixProj/TMDL
    project folder (`pbi-tools extract`)
  - `--to-pbix` — compile a project folder back into a `.pbix`/`.pbit`
    (`pbi-tools compile`)
  - Auto-detects the compile format: projects containing a data model produce a
    `.pbit` template, report-only ("thin") projects produce a `.pbix`, with an
    honest warning when `.pbix` is forced on a model project
  - `--model-serialization`, `--extract-mode`, `--format`, `--out`, and
    `--pbi-tools` flags; resolves the executable from `--pbi-tools`, the
    `PBI_TOOLS_PATH` env var, or `PATH`
  - Dry run by default (as with clean/copy modes); `--execute` performs the work

## [0.1.4] - 2026-04-09

### Fixed
- Corrupted shebang line in `measure_tool.py` causing import error on Python 3.12

## [0.1.2] - 2026-04-09

### Fixed
- Added author metadata (name, email) to `pyproject.toml`
- Fixed badge URLs in `README.md` (PyPI and Python version badges)

---

## [0.1.0] - 2026-04-09

### Added
- **Clean mode** — multi-pass unused measure detection across all report JSON files
  (pages, visuals, bookmarks), including measures-calling-measures chains
- **Copy mode** — copy or move measures between PBIP projects or tables
  - Interactive numbered selection with single, range, and list syntax
  - `--measures` flag for cherry-picking by exact name
  - `--all-measures` flag to copy everything
  - `--overwrite` flag to replace existing measures in the target
- **Auto-detect target structure** — three scenarios handled automatically:
  - Same project, different table (reorganising)
  - Different project, identical table names (auto-mapped)
  - Different project, different table names (interactive mapping)
- **DAX formatter** — dedents, strips trailing whitespace, collapses blank lines
- Preserves `formatString` and `description` metadata on copy
- Drops ephemeral TMDL properties (`lineageTag`, etc.) from copied blocks
- `--ignore-unapplied-filters` flag for clean mode
- `--execute` flag (default is always a safe dry run)
- Support for both SemanticModel (TMDL) and report-level measures
