# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-04-08

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
