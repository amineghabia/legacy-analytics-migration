"""Step 5 - Convert each syntax A script to syntax B with the LLM, with a repair loop.

    attempt 1 : generate code from the original script
    run it on the test data
    crash?  -> attempt 2 : send back the original, the code and the error
    ...        up to MAX_REPAIR_ATTEMPTS, then flag the script as failed

Early stop: if two consecutive attempts end with the same error, the model
is stuck (at temperature 0 it would repeat itself), so we stop and flag the
script instead of spending the remaining attempts.

The loop only repairs crashes. A script that runs but gives a different
result is NOT sent back with the expected output: the model could otherwise
fit the numbers instead of fixing the logic. Those differences are reported
by the validator for human review.
"""
import re
import sys
import time

from config import CONVERTED_DIR, MAX_REPAIR_ATTEMPTS, RUNS_DIR, USE_CONVERSION_NOTES
from pipeline.llm_client import LLMError, chat
from pipeline.parser import ParsedScript
from pipeline.runner import run_script, test_inputs

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

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(answer: str) -> str:
    """Take the code out of the markdown block (or the raw answer if there is none)."""
    match = CODE_BLOCK.search(answer)
    return (match.group(1) if match else answer).strip() + "\n"


def last_line(error: str) -> str:
    """The exception message, i.e. the last line of a traceback."""
    return error.strip().splitlines()[-1] if error.strip() else ""


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

    log, error, code, ok, stop_reason = [], "", "", False, "max_attempts"
    start = time.perf_counter()
    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        if attempt > 1:
            user = REPAIR_PROMPT.format(source=profile["name"], source_code=script.source,
                                        python_code=code, error=error)
        try:
            code = extract_code(chat(system, user))
        except LLMError as exc:
            error = str(exc)
            log.append(f"=== attempt {attempt}: LLM error ===\n{error}\n")
            continue
        target.write_text(code, encoding="utf-8")
        previous_error = last_line(error)
        ok, error = run_script([sys.executable], target, inputs, output)
        log.append(f"=== attempt {attempt}: {'OK' if ok else 'CRASH'} ===\n{code}\n"
                   + (f"--- error ---\n{error}\n" if error else ""))
        if ok:
            stop_reason = "success"
            break
        if last_line(error) == previous_error:
            stop_reason = "stuck_same_error"
            break

    (RUNS_DIR / f"{script.name}_conversion.log").write_text("\n".join(log), encoding="utf-8")
    return {
        "conversion_status": "success" if ok else "failed",
        "conversion_attempts": attempt,
        "repaired": ok and attempt > 1,
        "stop_reason": stop_reason,
        "last_error": "" if ok else last_line(error),
        "conversion_seconds": round(time.perf_counter() - start, 1),
    }
