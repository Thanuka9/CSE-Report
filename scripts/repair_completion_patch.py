from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

pipeline = ROOT / "src/cse_financial_etl/orchestration/pipeline.py"
text = pipeline.read_text(encoding="utf-8")
text = text.replace(
    "from cse_financial_etl.domain.periods import shift_quarter, supporting_periods",
    "from cse_financial_etl.domain.periods import supporting_periods",
)
pipeline.write_text(text, encoding="utf-8")

document_ir = ROOT / "src/cse_financial_etl/documents/document_ir.py"
text = document_ir.read_text(encoding="utf-8")
text = text.replace("import json\nimport math\nimport os\n", "import json\nimport os\n")
document_ir.write_text(text, encoding="utf-8")

tests = ROOT / "tests/regression/test_structure_benchmark.py"
text = tests.read_text(encoding="utf-8")
marker = "\ndef test_cumulative_only_flow_is_never_published_as_quarter"
if marker in text:
    text = text[: text.index(marker)]
text += r'''


def test_cumulative_only_flow_is_never_published_as_quarter(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "cumulative_only.pdf",
        "Statement of profit or loss - Company\n"
        "For the six months ended 30 June 2025\n"
        "Rs.'000\n"
        "Profit for the period 12,500 10,000",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    pat = facts_by_code(facts)["PAT"]
    assert pat.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}


def test_total_liabilities_is_never_assets_minus_equity_fallback(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "no_liabilities.pdf",
        "Statement of financial position - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 300 250\n"
        "Total equity 100 90",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    liabilities = facts_by_code(facts)["TOTAL_LIABILITIES"]
    assert liabilities.status != "EXTRACTED_DERIVED"
    assert liabilities.normalized_value is None
'''
tests.write_text(text, encoding="utf-8")
print("Completion patch repairs applied.")
