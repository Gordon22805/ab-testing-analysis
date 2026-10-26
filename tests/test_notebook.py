"""Execute the EDA notebook and assert it runs clean."""
from __future__ import annotations

import nbformat
import pytest
from nbclient import NotebookClient

from abtest.config import ROOT

NOTEBOOK = ROOT / "notebooks" / "01_eda.ipynb"


@pytest.fixture(scope="module")
def executed(tmp_path_factory):
    nb = nbformat.read(NOTEBOOK, as_version=4)
    nbformat.validate(nb)
    client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(NOTEBOOK.parent)}})
    client.execute()
    return nb


def test_notebook_executes_without_errors(executed):
    for index, cell in enumerate(executed.cells):
        for output in cell.get("outputs", []):
            assert output.get("output_type") != "error", f"cell {index}: {output.get('evalue')}"


def test_notebook_has_expected_sections(executed):
    markdown = " ".join(
        cell["source"] for cell in executed.cells if cell["cell_type"] == "markdown"
    )
    for heading in ("Данные и очистка", "Размер групп", "Воронка", "Сегменты", "Динамика по дням", "Выручка"):
        assert heading in markdown


def test_notebook_prints_dataframe_with_rows(executed):
    text_outputs = [
        "".join(output.get("text", ""))
        for cell in executed.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "stream"
    ]
    assert any("строк после очистки" in text for text in text_outputs)
