"""Central configuration: paths, model settings, taxonomies and tolerances.

Everything a user may want to tune lives here, so the pipeline modules
contain logic only.
"""
from pathlib import Path

# --- Paths -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
LEGACY_DIR = ROOT / "legacy_scripts"      # syntax A input scripts
TEST_DATA_DIR = ROOT / "test_data"        # one sub-folder of CSVs per script
CONVERTED_DIR = ROOT / "converted"        # generated syntax B scripts
OUTPUT_DIR = ROOT / "outputs"
RUNS_DIR = OUTPUT_DIR / "runs"            # raw outputs and repair logs

# Source language profile (see pipeline/languages.py)
SOURCE_LANGUAGE = "R"

# Explicit path to Rscript so the pipeline does not depend on the PATH.
RSCRIPT_PATH = r"C:\Program Files\R\R-4.6.1\bin\Rscript.exe"

# --- Local LLM (Ollama) ------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5-coder:7b"
TEMPERATURE = 0          # deterministic decoding: reproducible, auditable results
SEED = 42                # removes remaining sampling randomness
NUM_CTX = 4096           # context window (tokens); larger = more VRAM, slower on a 6 GB GPU
LLM_TIMEOUT_S = 300
MAX_JSON_ATTEMPTS = 2    # extraction: retry once if the answer fails validation

MAX_REPAIR_ATTEMPTS = 5  # conversion: generate, run, re-prompt with the error (early stop if stuck)
USE_CONVERSION_NOTES = True  # inject known A->B pitfalls into the conversion prompt
# V2 improvements (set both to False to reproduce V1)
WARNINGS_AS_ERRORS = True    # repair loop: a runtime warning (e.g. pandas Copy-on-Write) is a crash
STRUCTURAL_FEEDBACK = True   # repair loop: compare output structure (rows, columns, NA counts) with
                             # the original and send the differences back, never the values
SCRIPT_TIMEOUT_S = 120

# --- Taxonomies (closed lists, required to compare rules vs LLM) -------------
BUSINESS_CATEGORIES = ["finance", "sales", "HR", "risk", "operations"]
TECHNICAL_CATEGORIES = ["ingestion", "cleaning", "transformation", "modeling", "reporting"]
COMPLEXITY_LEVELS = ["simple", "moderate", "complex"]

# --- Validation ----------------------------------------------------------------
NUMERIC_RTOL = 1e-6      # relative tolerance for float comparison
NUMERIC_ATOL = 1e-8      # absolute tolerance (values close to zero)
