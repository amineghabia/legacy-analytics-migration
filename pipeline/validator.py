"""Step 6 - Run the original and the converted script on the same test data
and compare their output files.

Checks, from coarse to fine:
  row count      same number of rows
  columns        same column names (and same order)
  content_match  same values whatever the row order
  order_match    same values in the same row order
Numbers are compared with a tolerance (config.NUMERIC_RTOL / NUMERIC_ATOL):
R and Python may differ in the last decimals for purely technical reasons,
which is not a business difference. Missing values must be missing on both sides.

Both CSVs are parsed before comparison, never compared as raw text:
R quotes strings ("East") and pandas does not, which is cosmetic.
"""
import sys

import numpy as np
import pandas as pd

from config import CONVERTED_DIR, NUMERIC_ATOL, NUMERIC_RTOL, RSCRIPT_PATH, RUNS_DIR
from pipeline.parser import ParsedScript
from pipeline.runner import run_script, test_inputs

MAX_DETAILS = 5  # mismatching cells listed in the report


def equal_cells(a: pd.Series, b: pd.Series) -> np.ndarray:
    """Element-wise equality: tolerance for numbers, exact for text, NA == NA."""
    both_na = a.isna().to_numpy() & b.isna().to_numpy()
    a_num, b_num = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    if a_num.notna().sum() == a.notna().sum() and b_num.notna().sum() == b.notna().sum():
        close = np.isclose(a_num.to_numpy(float), b_num.to_numpy(float),
                           rtol=NUMERIC_RTOL, atol=NUMERIC_ATOL)
    else:
        close = (a.astype(str) == b.astype(str)).to_numpy()
    return both_na | (close & ~a.isna().to_numpy() & ~b.isna().to_numpy())


def compare_frames(r: pd.DataFrame, py: pd.DataFrame) -> tuple[int, float, list[str]]:
    """Compare two frames of the same shape, row by row.
    Return (number of mismatching cells, max numeric difference, details)."""
    mismatches, max_diff, details = 0, 0.0, []
    for col in r.columns:
        equal = equal_cells(r[col], py[col])
        mismatches += int((~equal).sum())
        a_num, b_num = pd.to_numeric(r[col], errors="coerce"), pd.to_numeric(py[col], errors="coerce")
        diff = (a_num - b_num).abs().max()
        if pd.notna(diff):
            max_diff = max(max_diff, float(diff))
        for i in np.flatnonzero(~equal)[:MAX_DETAILS - len(details)]:
            details.append(f"row {i + 1} '{col}': R={r[col].iloc[i]} Py={py[col].iloc[i]}")
    return mismatches, max_diff, details


def structure_differences(r: pd.DataFrame, py: pd.DataFrame) -> list[str]:
    """Differences in output structure only: row count, columns, missing values
    per column. No data values, so this can be shown to the LLM safely."""
    diffs = []
    if len(r) != len(py):
        diffs.append(f"the output has {len(py)} rows, the original output has {len(r)} rows")
    if list(r.columns) != list(py.columns):
        diffs.append(f"the output columns are {list(py.columns)}, "
                     f"the original output columns are {list(r.columns)} (same names, same order)")
    for col in [c for c in r.columns if c in py.columns]:
        r_na, py_na = int(r[col].isna().sum()), int(py[col].isna().sum())
        if r_na != py_na:
            diffs.append(f"column '{col}' has {py_na} missing values, the original has {r_na}")
    return diffs


def sort_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Canonical row order (values rounded so that tiny float noise does not reorder)."""
    key = df.round(6).astype(str)
    return df.loc[key.sort_values(list(df.columns)).index].reset_index(drop=True)


def validate(script: ParsedScript, conversion: dict) -> dict:
    result = {"script": script.name, "conversion_status": conversion["conversion_status"]}
    if conversion["conversion_status"] not in ("success", "runnable"):
        return {**result, "verdict": "not_converted", "details": conversion["last_error"]}

    inputs = test_inputs(script.name)
    r_out, py_out = RUNS_DIR / f"{script.name}_r.csv", RUNS_DIR / f"{script.name}_py.csv"
    ok, error = run_script([RSCRIPT_PATH], script.path, inputs, r_out)
    if not ok:
        return {**result, "verdict": "original_failed", "details": error[-300:]}
    ok, error = run_script([sys.executable], CONVERTED_DIR / f"{script.name}.py", inputs, py_out)
    if not ok:
        return {**result, "verdict": "converted_failed", "details": error[-300:]}

    r, py = pd.read_csv(r_out), pd.read_csv(py_out)
    result.update({
        "r_rows": len(r), "py_rows": len(py),
        "row_count_match": len(r) == len(py),
        "columns_match": set(r.columns) == set(py.columns),
        "column_order_match": list(r.columns) == list(py.columns),
    })
    if not (result["row_count_match"] and result["columns_match"]):
        missing = sorted(set(r.columns) - set(py.columns))
        extra = sorted(set(py.columns) - set(r.columns))
        return {**result, "content_match": False, "order_match": False, "verdict": "different",
                "details": f"rows R={len(r)} Py={len(py)}; missing columns {missing}; extra columns {extra}"}

    py = py[r.columns]  # align column order, already reported above
    ordered_mismatches, max_diff, details = compare_frames(r, py)
    sorted_mismatches, _, sorted_details = compare_frames(sort_rows(r), sort_rows(py))
    result.update({
        "order_match": ordered_mismatches == 0,
        "content_match": sorted_mismatches == 0,
        "mismatched_cells": sorted_mismatches,
        "max_abs_diff": round(max_diff, 6),
    })
    if result["order_match"]:
        verdict, details = "identical", []
    elif result["content_match"]:
        verdict, details = "same_content_different_order", details
    else:
        verdict, details = "different", sorted_details
    return {**result, "verdict": verdict, "details": " | ".join(details)}
