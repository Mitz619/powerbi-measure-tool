"""Unit tests for the pbix ↔ pbip conversion wrapper.

These tests do NOT require pbi-tools to be installed — they exercise the
pure command-builder / detection logic and the not-found error path.
"""

from pathlib import Path

import pytest

from powerbi_measure_tool import convert


# ── pbi-tools discovery ────────────────────────────────────────

class TestFindPbiTools:
    def test_explicit_existing_file_used_as_is(self, tmp_path):
        fake = tmp_path / "pbi-tools.exe"
        fake.write_text("")
        assert convert.find_pbi_tools(str(fake)) == str(fake)

    def test_env_var_existing_file(self, tmp_path, monkeypatch):
        fake = tmp_path / "pbi-tools.core.exe"
        fake.write_text("")
        monkeypatch.setenv("PBI_TOOLS_PATH", str(fake))
        assert convert.find_pbi_tools() == str(fake)

    def test_not_found_raises(self, monkeypatch):
        monkeypatch.delenv("PBI_TOOLS_PATH", raising=False)
        monkeypatch.setattr(convert.shutil, "which", lambda _: None)
        with pytest.raises(convert.PbiToolsNotFoundError):
            convert.find_pbi_tools()


# ── command builders ───────────────────────────────────────────

class TestBuildExtractCommand:
    def test_minimal(self):
        cmd = convert.build_extract_command("pbi-tools", Path("r.pbix"))
        assert cmd[:3] == ["pbi-tools", "extract", "r.pbix"]
        assert "-modelSerialization" in cmd
        assert "Tmdl" in cmd
        assert "-mode" in cmd and "Auto" in cmd

    def test_with_out_folder(self):
        cmd = convert.build_extract_command(
            "pbi-tools", Path("r.pbix"), Path("out"), "Tmdl", "V3"
        )
        assert "-extractFolder" in cmd
        i = cmd.index("-extractFolder")
        assert cmd[i + 1] == "out"
        assert "V3" in cmd


class TestBuildCompileCommand:
    def test_minimal(self):
        cmd = convert.build_compile_command("pbi-tools", Path("proj"))
        assert cmd[:3] == ["pbi-tools", "compile", "proj"]
        assert "-format" in cmd and "PBIX" in cmd
        assert "-overwrite" not in cmd

    def test_pbit_with_overwrite_and_out(self):
        cmd = convert.build_compile_command(
            "pbi-tools", Path("proj"), Path("out.pbit"), "PBIT", overwrite=True
        )
        assert "-overwrite" in cmd
        assert "PBIT" in cmd
        i = cmd.index("-outPath")
        assert cmd[i + 1] == "out.pbit"


# ── project model detection ────────────────────────────────────

class TestProjectHasModel:
    def test_pbip_semantic_model_folder(self, tmp_path):
        (tmp_path / "Sales.SemanticModel" / "definition" / "tables").mkdir(parents=True)
        assert convert.project_has_model(tmp_path) is True

    def test_pbixproj_model_folder(self, tmp_path):
        (tmp_path / "Model").mkdir()
        (tmp_path / "Model" / "database.tmdl").write_text("database x")
        assert convert.project_has_model(tmp_path) is True

    def test_report_only_has_no_model(self, tmp_path):
        (tmp_path / "Report").mkdir()
        (tmp_path / "Report" / "report.json").write_text("{}")
        assert convert.project_has_model(tmp_path) is False

    def test_missing_folder(self, tmp_path):
        assert convert.project_has_model(tmp_path / "nope") is False


class TestResolveCompileFormat:
    def test_explicit_pbit(self, tmp_path):
        assert convert.resolve_compile_format(tmp_path, "pbit") == "PBIT"

    def test_explicit_pbix(self, tmp_path):
        assert convert.resolve_compile_format(tmp_path, "PBIX") == "PBIX"

    def test_auto_with_model(self, tmp_path):
        (tmp_path / "Sales.SemanticModel").mkdir()
        assert convert.resolve_compile_format(tmp_path, "auto") == "PBIT"

    def test_auto_report_only(self, tmp_path):
        assert convert.resolve_compile_format(tmp_path, None) == "PBIX"


# ── high-level dry runs (no pbi-tools invocation) ──────────────

class TestDryRuns:
    def test_pbix_to_pbip_dry_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(convert, "find_pbi_tools", lambda explicit=None: "pbi-tools")
        pbix = tmp_path / "r.pbix"
        pbix.write_text("")
        result = convert.convert_pbix_to_pbip(pbix, tmp_path / "out", execute=False)
        assert result is None  # dry run returns None

    def test_pbix_to_pbip_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(convert, "find_pbi_tools", lambda explicit=None: "pbi-tools")
        with pytest.raises(FileNotFoundError):
            convert.convert_pbix_to_pbip(tmp_path / "missing.pbix", execute=False)

    def test_pbip_to_pbix_dry_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(convert, "find_pbi_tools", lambda explicit=None: "pbi-tools")
        (tmp_path / "Report").mkdir()
        result = convert.convert_pbip_to_pbix(tmp_path, execute=False)
        assert result is None
