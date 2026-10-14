"""Single entry point: python run_pipeline.py [--input legacy_scripts]

  1. parse        read and parse every syntax A script of the input directory
  2. LLM extract  business / technical / complexity / description (local LLM)
  3. rule extract same fields with deterministic rules
  4. compare      rules vs LLM, agreement rates, disagreements for review
  5. convert      syntax A -> syntax B with the LLM and a repair loop
  6. validate     run original and converted scripts, compare outputs

Outputs (outputs/):
  metadata.csv               one row per script: rule and LLM extractions
  extraction_comparison.csv  one row per script and field: verdict + review priority
  comparison_summary.csv     agreement rate per field
  validation_report.csv      one row per script: conversion and output comparison
  runs/                      raw outputs of both scripts and conversion logs
"""
import argparse
import time
from pathlib import Path

import pandas as pd

from config import LEGACY_DIR, MODEL_NAME, OUTPUT_DIR, RUNS_DIR, SOURCE_LANGUAGE
from pipeline import comparator, converter, llm_extractor, rule_extractor, validator
from pipeline.languages import get_profile
from pipeline.parser import load_scripts


def as_text(value):
    """Lists are written as 'a; b' in CSV files."""
    return "; ".join(value) if isinstance(value, list) else value


def metadata_row(script, rules: dict, llm: dict) -> dict:
    row = {"script": script.name, "file": script.path.name, "loc": script.loc,
           "libraries": sorted(script.libraries)}
    for field in ["business_category", "business_domains", "technical_category",
                  "technical_operations", "complexity"]:
        row[f"rule_{field}"] = rules[field]
        row[f"llm_{field}"] = llm[field]
    row.update({
        "rule_complexity_score": rules["complexity_score"],
        "rule_business_evidence": str(rules["business_evidence"]),
        "llm_description": llm["description"],
        "llm_status": llm["llm_status"],
        "llm_seconds": llm["llm_seconds"],
    })
    return {k: as_text(v) for k, v in row.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Legacy script analysis and migration pipeline")
    parser.add_argument("--input", type=Path, default=LEGACY_DIR, help="directory of syntax A scripts")
    args = parser.parse_args()

    start = time.perf_counter()
    profile = get_profile(SOURCE_LANGUAGE)
    OUTPUT_DIR.mkdir(exist_ok=True)
    RUNS_DIR.mkdir(exist_ok=True)

    scripts = load_scripts(args.input, profile)
    print(f"[1] Parsed {len(scripts)} {profile['name']} scripts from {args.input}  (model: {MODEL_NAME})")

    metadata, extractions, validations = [], [], []
    for i, script in enumerate(scripts, 1):
        print(f"\n--- [{i}/{len(scripts)}] {script.name}")
        llm = llm_extractor.extract(script, profile)
        print(f"[2] LLM extraction   : {llm['business_category']} / {llm['technical_category']} / "
              f"{llm['complexity']}  ({llm['llm_status']}, {llm['llm_seconds']}s)")
        rules = rule_extractor.extract(script, profile)
        print(f"[3] Rule extraction  : {rules['business_category']} / {rules['technical_category']} / "
              f"{rules['complexity']}")
        metadata.append(metadata_row(script, rules, llm))
        extractions.append((script.name, rules, llm))

        conversion = converter.convert(script, profile)
        print(f"[5] Conversion       : {conversion['conversion_status']} after "
              f"{conversion['conversion_attempts']} attempt(s) ({conversion['stop_reason']})")
        validation = validator.validate(script, conversion)
        print(f"[6] Validation       : {validation['verdict']}")
        validations.append({**validation, **{k: v for k, v in conversion.items()
                                             if k != "conversion_status"}})

    comparison = comparator.compare(extractions)
    summary = comparator.summarise(comparison)
    report = pd.DataFrame(validations)

    pd.DataFrame(metadata).to_csv(OUTPUT_DIR / "metadata.csv", index=False)
    comparison.to_csv(OUTPUT_DIR / "extraction_comparison.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "comparison_summary.csv", index=False)
    report.to_csv(OUTPUT_DIR / "validation_report.csv", index=False)

    print("\n[4] Rules vs LLM agreement")
    print(summary[["field", "strict_agreement", "lenient_agreement"]].to_string(index=False))
    flagged = comparison[comparison.review_priority == "high"]
    print(f"    {len(flagged)} high-priority disagreement(s) flagged for human review")
    print("\n[6] Validation verdicts")
    print(report.verdict.value_counts().to_string())
    print(f"\nDone in {time.perf_counter() - start:.0f}s. Outputs written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
