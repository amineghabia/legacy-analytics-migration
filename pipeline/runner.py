"""Execute a script under the common execution contract:

    <command> <script> <input_1.csv> [<input_2.csv> ...] <output.csv>

Used by the converter (does the generated code run?) and by the validator
(original vs converted outputs). Inputs of a script are the CSV files of
test_data/<script_name>/, in alphabetical order.
"""
import subprocess
from pathlib import Path

from config import SCRIPT_TIMEOUT_S, TEST_DATA_DIR


def test_inputs(script_name: str) -> list[Path]:
    inputs = sorted((TEST_DATA_DIR / script_name).glob("*.csv"))
    if not inputs:
        raise FileNotFoundError(f"No test data in {TEST_DATA_DIR / script_name}")
    return inputs


def run_script(command: list[str], script: Path, inputs: list[Path], output: Path) -> tuple[bool, str]:
    """Run the script; return (success, error message)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)  # never compare with a stale output
    try:
        proc = subprocess.run([*command, str(script), *map(str, inputs), str(output)],
                              capture_output=True, text=True, timeout=SCRIPT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {SCRIPT_TIMEOUT_S}s"
    if proc.returncode != 0:
        return False, proc.stderr.strip()[-2000:]  # the end of a traceback is the useful part
    if not output.exists():
        return False, f"Script ended without writing the output file {output.name}"
    return True, ""
