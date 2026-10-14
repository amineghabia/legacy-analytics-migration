"""Step 3 - Deterministic (rule-based) extraction, no LLM.

Same input as the LLM extractor, same output fields, so both can be compared.
Every decision is traceable: the result keeps the evidence (matched keywords,
complexity points) that produced it.

  business    : business keywords found in the script name, comments and identifiers
  technical   : function calls mapped to categories by the language profile
  complexity  : additive score over five structural dimensions
"""
import re
from collections import Counter

from config import BUSINESS_CATEGORIES, TECHNICAL_CATEGORIES
from pipeline.parser import ParsedScript

# Business vocabulary is language-agnostic, so it lives here and not in the
# language profile. Keywords are singular; plurals are matched automatically.
BUSINESS_KEYWORDS = {
    "finance": ["finance", "financial", "accrual", "ifrs", "provision", "ledger",
                "budget", "invoice", "expense", "profit", "payout", "loan"],
    "sales": ["sale", "revenue", "order", "deal", "commission", "rep", "quota",
              "product", "region"],
    "HR": ["hr", "employee", "salary", "payroll", "headcount", "bonus",
           "compensation", "hire", "department"],
    "risk": ["risk", "credit", "default", "defaulted", "exposure", "delinquency",
             "segmentation", "pd"],
    "operations": ["operation", "inventory", "warehouse", "stock", "sku",
                   "supply", "logistic", "shipment"],
}

# A secondary business domain needs at least half the evidence of the main one,
# so a single incidental word does not add a domain.
SECONDARY_DOMAIN_RATIO = 0.5

# Modeling calls are rare but decisive: one glm() makes a modeling script,
# while read.csv() appears in every script.
TECHNICAL_WEIGHTS = {"ingestion": 1, "cleaning": 1, "transformation": 1,
                     "modeling": 3, "reporting": 1}
# Tie-break: the most specific operation wins.
TECHNICAL_PRIORITY = ["modeling", "reporting", "cleaning", "transformation", "ingestion"]

# Complexity: each dimension gives 0, 1 or 2 points -> total between 0 and 10.
# (value up to which the dimension gives 0 points, value up to which it gives 1)
COMPLEXITY_THRESHOLDS = {
    "loc": (15, 30),             # lines of code
    "distinct_calls": (10, 20),  # vocabulary of functions used
    "control_flow": (0, 3),      # if / for / while ...
    "user_functions": (0, 2),    # functions defined in the script
    "libraries": (0, 2),         # external dependencies
}
SIMPLE_MAX, MODERATE_MAX = 1, 3  # total points: 0-1 simple, 2-3 moderate, 4+ complex


def tokenize(text: str) -> list[str]:
    """'closed_sales' -> ['closed', 'sales']; lowercase words only."""
    return re.findall(r"[a-z]+", text.lower())


def keyword_hit(token: str, keywords: set[str]) -> bool:
    """Match a token or its singular form ('loans' -> 'loan')."""
    return token in keywords or (token.endswith("s") and token[:-1] in keywords)


def extract_business(script: ParsedScript) -> dict:
    text = " ".join([script.name, *script.comments, *script.code_lines])
    tokens = tokenize(text)
    scores, evidence = Counter(), {}
    for category, keywords in BUSINESS_KEYWORDS.items():
        hits = [t for t in tokens if keyword_hit(t, set(keywords))]
        if hits:
            scores[category] = len(hits)
            evidence[category] = sorted(set(hits))

    if not scores:
        return {"business_category": "unknown", "business_domains": [],
                "business_evidence": {}}
    main, top = scores.most_common(1)[0]
    domains = [c for c in BUSINESS_CATEGORIES if scores[c] >= SECONDARY_DOMAIN_RATIO * top]
    return {"business_category": main, "business_domains": domains,
            "business_evidence": {c: evidence[c] for c in domains}}


def extract_technical(script: ParsedScript, profile: dict) -> dict:
    scores, evidence = Counter(), {}
    for category, functions in profile["technical_keywords"].items():
        found = {f: n for f, n in script.function_calls.items() if f in functions}
        if found:
            scores[category] = sum(found.values()) * TECHNICAL_WEIGHTS[category]
            evidence[category] = sorted(found)

    if not scores:
        return {"technical_category": "unknown", "technical_operations": [],
                "technical_evidence": {}}
    top = max(scores.values())
    main = next(c for c in TECHNICAL_PRIORITY if scores[c] == top)
    operations = [c for c in TECHNICAL_CATEGORIES if scores[c] > 0]
    return {"technical_category": main, "technical_operations": operations,
            "technical_evidence": evidence}


def points(value: int, thresholds: tuple[int, int]) -> int:
    low, high = thresholds
    return 0 if value <= low else 1 if value <= high else 2


def extract_complexity(script: ParsedScript) -> dict:
    metrics = {
        "loc": script.loc,
        "distinct_calls": len(script.function_calls),
        "control_flow": sum(script.control_flow.values()),
        "user_functions": script.user_functions,
        "libraries": len(script.libraries),
    }
    detail = {m: points(v, COMPLEXITY_THRESHOLDS[m]) for m, v in metrics.items()}
    score = sum(detail.values())
    level = "simple" if score <= SIMPLE_MAX else "moderate" if score <= MODERATE_MAX else "complex"
    return {"complexity": level, "complexity_score": score,
            "complexity_metrics": metrics, "complexity_points": detail}


def extract(script: ParsedScript, profile: dict) -> dict:
    """Run the three rule-based extractions on one parsed script."""
    return {**extract_business(script), **extract_technical(script, profile),
            **extract_complexity(script)}
