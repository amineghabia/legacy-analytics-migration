"""Step 2 - LLM extraction: business, technical, complexity, description.

Two safety layers on the model's answer:
  1. constrained decoding: Ollama only lets the model produce JSON that
     matches SCHEMA (keys present, values inside the taxonomies);
  2. validation in Python: the same rules are re-checked here, so a model
     or engine that ignores the schema cannot corrupt the outputs.
If the answer is still invalid after MAX_JSON_ATTEMPTS, the script is
flagged 'invalid' for human review instead of crashing the pipeline.

The LLM never sees the rule-based results: both methods stay independent,
otherwise the comparison would be meaningless.
"""
import time

from config import (BUSINESS_CATEGORIES, COMPLEXITY_LEVELS, MAX_JSON_ATTEMPTS,
                    TECHNICAL_CATEGORIES)
from pipeline.llm_client import LLMError, chat_json
from pipeline.parser import ParsedScript

MAX_DESCRIPTION_CHARS = 400

SCHEMA = {
    "type": "object",
    "properties": {
        "business_category": {"type": "string", "enum": BUSINESS_CATEGORIES},
        "business_domains": {"type": "array", "items": {"type": "string", "enum": BUSINESS_CATEGORIES}},
        "technical_category": {"type": "string", "enum": TECHNICAL_CATEGORIES},
        "technical_operations": {"type": "array", "items": {"type": "string", "enum": TECHNICAL_CATEGORIES}},
        "complexity": {"type": "string", "enum": COMPLEXITY_LEVELS},
        "description": {"type": "string"},
    },
    "required": ["business_category", "business_domains", "technical_category",
                 "technical_operations", "complexity", "description"],
}

SYSTEM_PROMPT = """You are a senior data engineer auditing legacy {language} analytics scripts before a migration.
Classify the script using ONLY the allowed values.

Business categories (the business process the script serves):
- finance: accounting, provisions, budgets, payouts, financial reporting
- sales: orders, revenue, customers' purchases, sales teams and commissions
- HR: employees, salaries, headcount, payroll, compensation
- risk: credit risk, default, exposure, risk scoring and segmentation
- operations: inventory, warehouses, supply chain, logistics

Technical categories (operations performed on the data):
- ingestion: reading, loading or combining raw sources
- cleaning: fixing types, missing values, duplicates, inconsistent text
- transformation: aggregations, joins, derived columns, ranking, binning
- modeling: statistical or machine learning models
- reporting: charts, formatted outputs, printed summaries

Fields:
- business_category: the main business owner of the script (one value).
- business_domains: every business category the script clearly serves (includes the main one).
- technical_category: the dominant operation (one value).
- technical_operations: every operation the script performs (includes the dominant one).
- complexity: simple, moderate or complex, based on logic (control flow, functions,
  joins, models), length and dependencies (libraries).
- description: 1 or 2 sentences, plain English, describing what the script does.
Answer in JSON only."""


def validate(answer: dict) -> list[str]:
    """Return the list of problems in the answer (empty list = valid)."""
    problems = [f"missing field '{f}'" for f in SCHEMA["required"] if f not in answer]
    if problems:
        return problems
    if answer["business_category"] not in BUSINESS_CATEGORIES:
        problems.append(f"invalid business_category '{answer['business_category']}'")
    if answer["technical_category"] not in TECHNICAL_CATEGORIES:
        problems.append(f"invalid technical_category '{answer['technical_category']}'")
    if answer["complexity"] not in COMPLEXITY_LEVELS:
        problems.append(f"invalid complexity '{answer['complexity']}'")
    if any(d not in BUSINESS_CATEGORIES for d in answer["business_domains"]):
        problems.append(f"invalid business_domains {answer['business_domains']}")
    if any(o not in TECHNICAL_CATEGORIES for o in answer["technical_operations"]):
        problems.append(f"invalid technical_operations {answer['technical_operations']}")
    description = answer["description"].strip()
    if not description or len(description) > MAX_DESCRIPTION_CHARS:
        problems.append("description empty or too long")
    return problems


def normalise(answer: dict) -> dict:
    """Deterministic clean-up: the main category must belong to its list,
    lists are de-duplicated and sorted in taxonomy order."""
    domains = set(answer["business_domains"]) | {answer["business_category"]}
    operations = set(answer["technical_operations"]) | {answer["technical_category"]}
    return {
        **answer,
        "business_domains": [c for c in BUSINESS_CATEGORIES if c in domains],
        "technical_operations": [c for c in TECHNICAL_CATEGORIES if c in operations],
        "description": answer["description"].strip(),
    }


def extract(script: ParsedScript, profile: dict) -> dict:
    system = SYSTEM_PROMPT.replace("{language}", profile["name"])
    user = f"Script name: {script.path.name}\n\n```\n{script.source}\n```"

    problems: list[str] = []
    start = time.perf_counter()
    for attempt in range(1, MAX_JSON_ATTEMPTS + 1):
        try:
            answer = chat_json(system, user, SCHEMA)
            problems = validate(answer)
        except LLMError as exc:
            problems = [str(exc)]
        if not problems:
            return {**normalise(answer), "llm_status": "ok", "llm_attempts": attempt,
                    "llm_seconds": round(time.perf_counter() - start, 1)}

    return {"business_category": "unknown", "business_domains": [],
            "technical_category": "unknown", "technical_operations": [],
            "complexity": "unknown", "description": "",
            "llm_status": "invalid: " + "; ".join(problems),
            "llm_attempts": MAX_JSON_ATTEMPTS,
            "llm_seconds": round(time.perf_counter() - start, 1)}
