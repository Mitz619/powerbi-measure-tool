"""Basic unit tests for powerbi-measure-tool."""

import pytest
from powerbi_measure_tool.measure_tool import format_dax, build_tmdl_measure_block, Measure


class TestFormatDax:
    def test_strips_trailing_whitespace(self):
        expr = "CALCULATE(SUM(Sales[Amount]))   "
        assert format_dax(expr) == "CALCULATE(SUM(Sales[Amount]))"

    def test_dedents_common_indent(self):
        expr = "    VAR x = 1\n    RETURN x"
        result = format_dax(expr)
        assert result == "VAR x = 1\nRETURN x"

    def test_collapses_multiple_blank_lines(self):
        expr = "VAR x = 1\n\n\n\nRETURN x"
        result = format_dax(expr)
        assert result == "VAR x = 1\n\nRETURN x"

    def test_trims_leading_trailing_blanks(self):
        expr = "\n\nVAR x = 1\nRETURN x\n\n"
        result = format_dax(expr)
        assert result == "VAR x = 1\nRETURN x"

    def test_empty_string(self):
        assert format_dax("") == ""

    def test_single_line_unchanged(self):
        expr = "SUM(Sales[Amount])"
        assert format_dax(expr) == expr


class TestBuildTmdlMeasureBlock:
    def _make_measure(self, name="My Measure", expr="SUM(Sales[Amount])",
                      fmt=None, desc=None):
        return Measure(
            name=name, table="Sales", expression=expr,
            source="semantic_model",
            format_string=fmt, description=desc,
        )

    def test_single_line_inline(self):
        m = self._make_measure()
        block = build_tmdl_measure_block(m)
        assert block.startswith("\tmeasure 'My Measure' = SUM(Sales[Amount])")

    def test_multiline_indented(self):
        m = self._make_measure(expr="VAR x = 1\nRETURN x")
        block = build_tmdl_measure_block(m)
        assert "\t\tVAR x = 1" in block
        assert "\t\tRETURN x" in block

    def test_format_string_appended(self):
        m = self._make_measure(fmt="#,0.00")
        block = build_tmdl_measure_block(m)
        assert "\t\tformatString: #,0.00" in block

    def test_no_format_string_by_default(self):
        m = self._make_measure()
        block = build_tmdl_measure_block(m)
        assert "formatString" not in block

    def test_description_appended(self):
        m = self._make_measure(desc="Total sales amount")
        block = build_tmdl_measure_block(m)
        assert "description:" in block
        assert "Total sales amount" in block
