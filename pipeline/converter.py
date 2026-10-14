"""Step 5 - Convert each syntax A script to syntax B with the LLM, with a repair loop.

    attempt 1 : generate code from the original script
    run it on the test data
    crash?  -> attempt 2 : send back the original, the code and the error
    ...        up to MAX_REPAIR_ATTEMPTS, then flag the script as failed

Early stop: if two consecutive attempts end with the same error, the model
is stuck (at temperature 0 it would repeat itself), so we stop and flag the
script instead of spending the remaining attempts.

What counts as a failure to repair:
  - a crash (and, if WARNINGS_AS_ERRORS, a runtime warning such as pandas
    Copy-on-Write, which otherwise silently does nothing);
  - if STRUCTURAL_FEEDBACK, an output whose structure differs from the
    original output (row count, column names, missing values per column).
The expected VALUES are never sent back: the model could otherwise fit the
numbers instead of fixing the logic. Value differences are reported by the
validator for human review. If the budget runs out, the last version that
runs is kept (status 'runnable') so the validator can still report on it.
"""
import re
import sys
import time

import pandas as pd

from config import (CONVERTED_DIR, MAX_REPAIR_ATTEMPTS, RSCRIPT_PATH, RUNS_DIR,
                    STRUCTURAL_FEEDBACK, USE_CONVERSION_NOTES, WARNINGS_AS_ERRORS)
from pipeline.llm_client import LLMError, chat
from pipeline.parser import ParsedScript
from pipeline.runner import run_script, test_inputs
from pipeline.validator import structure_differences

SYSTEM_PROMPT = """You are an expert data engineer migrating legacy {source} scripts to {target}.
Rewrite the script so that it produces EXACTLY the same output file as the original:
same rows, same row order, same columns, same column names, same values, same missing values.
Reproduce the original behaviour faithfully, even if it looks like a bug. Do not improve it.

Execution contract (mandatory):
- the script is run as: python script.py <input_1.csv> [<input_2.csv> ...] <output.csv>
- read the input files from sys.argv[1:-1] in the same order as the original script
- write the result with to_csv(sys.argv[-1], index=False, na_rep="NA")
- no hard-coded paths, no printing, no plots
Allowed libraries: pandas, numpy, statsmodels, scikit-learn, and the Python standard library.
Return only the complete Python code in a single ```python block.{notes}"""

REPAIR_PROMPT = """The Python conversion of this {source} script crashed.

Original {source} script:
```
{source_code}
```

Your previous Python code:
```python
{python_code}
```

Error:
```
{error}
```

Find the root cause before fixing: the line that crashes is not always the
line that is wrong. Check in particular how the data is read and typed
(column dtypes) and whether earlier steps produce what the original produces.
Fix the error while keeping exactly the behaviour of the original script.
Return only the complete corrected Python code in a single ```python block."""

STRUCTURE_PROMPT = """The Python conversion of this {source} script runs, but its output
does not have the same structure as the output of the original script.

Original {source} script:
```
{source_code}
```

Your previous Python code:
```python
{python_code}
```

Differences found (structure only):
{error}

Find which step of your code diverges from the original logic and fix it.
Do not hard-code values. Keep exactly the behaviour of the original script.
Return only the complete corrected Python code in a single ```python block."""

# Runtime warnings become errors, except library deprecation notices.
PYTHON_FLAGS = ["-W", "error", "-W", "ignore::DeprecationWarning"]
EXCEPTION_LINE = re.compile(r"^[\w.]*(Error|Exception|Warning)\b")

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(answer: str) -> str:
    """Take the code out of the markdown block (or the raw answer if there is none)."""
    match = CODE_BLOCK.search(answer)
    return (match.group(1) if match else answer).strip() + "\n"


def last_line(error: str) -> str:
    """The exception message of a traceback, e.g. 'ValueError: ...'.
    pandas warnings end with a documentation link, so the last line that
    looks like an exception is taken, not simply the last line."""
    lines = error.strip().splitlines()
    exceptions = [line for line in lines if EXCEPTION_LINE.match(line)]
    return exceptions[-1] if exceptions else (lines[-1] if lines else "")


def reference_output(script: ParsedScript, inputs: list) -> pd.DataFrame | None:
    """Run the original script once to know the expected output structure."""
    reference = RUNS_DIR / f"{script.name}_r.csv"
    ok, _ = run_script([RSCRIPT_PATH], script.path, inputs, reference)
    return pd.read_csv(reference) if ok else None


def structure_problems(reference: pd.DataFrame, output) -> list[str]:
    try:
        return structure_differences(reference, pd.read_csv(output))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        return [f"the output file cannot be read as CSV ({exc})"]


def system_prompt(profile: dict) -> str:
    notes = ""
    if USE_CONVERSION_NOTES:
        bullets = "\n".join(f"- {n}" for n in profile["conversion_notes"])
        notes = f"\n\nKnown differences between {profile['name']} and Python to handle carefully:\n{bullets}"
    return SYSTEM_PROMPT.format(source=profile["name"], target=profile["target_name"], notes=notes)


def convert(script: ParsedScript, profile: dict) -> dict:
    CONVERTED_DIR.mkdir(exist_ok=True)
    target = CONVERTED_DIR / f"{script.name}.py"
    output = RUNS_DIR / f"{script.name}_py.csv"
    inputs = test_inputs(script.name)
    system = system_prompt(profile)
    user = f"Convert this {profile['name']} script ({script.path.name}):\n\n```\n{script.source}\n```"
    python = [sys.executable, *PYTHON_FLAGS] if WARNINGS_AS_ERRORS else [sys.executable]
    reference = reference_output(script, inputs) if STRUCTURAL_FEEDBACK else None

    log, code, runnable_code = [], "", None
    kind, problem, signature = "", "", ""  # last problem: "crash" (error) or "structure" (differences)
    ok, stop_reason = False, "max_attempts"
    start = time.perf_counter()
    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        if attempt > 1:
            template = REPAIR_PROMPT if kind == "crash" else STRUCTURE_PROMPT
            user = template.format(source=profile["name"], source_code=script.source,
                                   python_code=code, error=problem)
        try:
            code = extract_code(chat(system, user))
        except LLMError as exc:
            log.append(f"=== attempt {attempt}: LLM error ===\n{exc}\n")
            continue
        target.write_text(code, encoding="utf-8")
        ran, error = run_script(python, target, inputs, output)
        if ran:
            runnable_code = code
            diffs = structure_problems(reference, output) if reference is not None else []
            if not diffs:
                ok, stop_reason = True, "success"
                log.append(f"=== attempt {attempt}: OK ===\n{code}\n")
                break
            kind, problem = "structure", "\n".join(f"- {d}" for d in diffs)
            log.append(f"=== attempt {attempt}: STRUCTURE MISMATCH ===\n{code}\n"
                       f"--- differences ---\n{problem}\n")
        else:
            kind, problem = "crash", error
            log.append(f"=== attempt {attempt}: CRASH ===\n{code}\n--- error ---\n{error}\n")

        # Same problem twice in a row: the model is stuck, stop spending attempts
        previous, signature = signature, problem if kind == "structure" else last_line(problem)
        if signature == previous:
            stop_reason = "stuck_same_error"
            break

    if not ok and runnable_code:
        target.write_text(runnable_code, encoding="utf-8")  # keep the last version that runs
    status = "success" if ok else "runnable" if runnable_code else "failed"
    (RUNS_DIR / f"{script.name}_conversion.log").write_text("\n".join(log), encoding="utf-8")
    return {
        "conversion_status": status,
        "conversion_attempts": attempt,
        "repaired": ok and attempt > 1,
        "stop_reason": stop_reason,
        "last_error": "" if ok else signature,
        "conversion_seconds": round(time.perf_counter() - start, 1),
    }
