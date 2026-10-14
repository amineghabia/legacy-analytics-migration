"""Step 4 - Compare deterministic and LLM extractions.

Output is in long format (one row per script and field), so disagreements
can be filtered directly. Each comparison gets a verdict:

  agree     : same value
  partial   : not the same, but compatible -> likely ambiguity, low-priority review
              (main categories: each method lists the other's choice in its domains;
               complexity: one level apart; lists: overlap >= 50%)
  disagree  : incompatible answers -> high-priority human review
  llm_invalid : the LLM answer failed validation -> high-priority human review

A disagreement is not automatically an error of the LLM: rules can be wrong
too, and some scripts genuinely belong to several categories.
"""
import pandas as pd

from config import COMPLEXITY_LEVELS

PARTIAL_OVERLAP = 0.5
PRIORITY = {"agree": "none", "partial": "low", "disagree": "high", "llm_invalid": "high"}


def jaccard(a: list, b: list) -> float:
    """Overlap between two sets: |A and B| / |A or B| (1 = identical)."""
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def compare_main(rule_value: str, llm_value: str, rule_list: list, llm_list: list) -> str:
    if rule_value == llm_value:
        return "agree"
    if rule_value in llm_list and llm_value in rule_list:
        return "partial"
    return "disagree"


def compare_complexity(rule_value: str, llm_value: str) -> str:
    gap = abs(COMPLEXITY_LEVELS.index(rule_value) - COMPLEXITY_LEVELS.index(llm_value))
    return "agree" if gap == 0 else "partial" if gap == 1 else "disagree"


def compare_lists(rule_list: list, llm_list: list) -> tuple[str, float]:
    score = jaccard(rule_list, llm_list)
    verdict = "agree" if score == 1 else "partial" if score >= PARTIAL_OVERLAP else "disagree"
    return verdict, round(score, 2)


def compare_script(name: str, rules: dict, llm: dict) -> list[dict]:
    def row(field, verdict, rule_value, llm_value, overlap=None):
        return {"script": name, "field": field, "rule_value": rule_value,
                "llm_value": llm_value, "overlap": overlap, "verdict": verdict,
                "review_priority": PRIORITY[verdict]}

    fields = ["business_category", "business_domains", "technical_category",
              "technical_operations", "complexity"]
    if llm["llm_status"] != "ok":
        return [row(f, "llm_invalid", str(rules[f]), "") for f in fields]

    rows = []
    for main, lst in [("business_category", "business_domains"),
                      ("technical_category", "technical_operations")]:
        verdict = compare_main(rules[main], llm[main], rules[lst], llm[lst])
        rows.append(row(main, verdict, rules[main], llm[main]))
        verdict, score = compare_lists(rules[lst], llm[lst])
        rows.append(row(lst, verdict, ", ".join(rules[lst]), ", ".join(llm[lst]), score))
    rows.append(row("complexity", compare_complexity(rules["complexity"], llm["complexity"]),
                    rules["complexity"], llm["complexity"]))
    return rows


def compare(results: list[tuple[str, dict, dict]]) -> pd.DataFrame:
    """results = [(script_name, rule_extraction, llm_extraction), ...]"""
    rows = [r for name, rules, llm in results for r in compare_script(name, rules, llm)]
    return pd.DataFrame(rows)


def summarise(comparison: pd.DataFrame) -> pd.DataFrame:
    """Agreement rate per field: strict (agree) and lenient (agree or partial)."""
    summary = comparison.groupby("field", sort=False)["verdict"].agg(
        n_scripts="size",
        agree=lambda v: (v == "agree").sum(),
        partial=lambda v: (v == "partial").sum(),
        disagree=lambda v: v.isin(["disagree", "llm_invalid"]).sum(),
    ).reset_index()
    summary["strict_agreement"] = (summary.agree / summary.n_scripts).round(2)
    summary["lenient_agreement"] = ((summary.agree + summary.partial) / summary.n_scripts).round(2)
    return summary
