# Legacy Analytics Migration Pipeline

A local pipeline that analyses legacy analytics scripts written in **syntax A**,
categorises them, converts them to **syntax B**, and validates each conversion by
running both versions on the same test data.

For this prototype, **syntax A = R** and **syntax B = Python (pandas)**. Everything
that depends on the source language is isolated in one language profile, so the
same engine can be pointed at SAS or another legacy language.

All processing is local. The LLM runs through [Ollama](https://ollama.com) on the
workstation, so no source code is sent to an external service.

---

## 1. What the pipeline does

| Step | Module | Description |
|------|--------|-------------|
| 1. Parse | `pipeline/parser.py` | Reads every script in the input directory and extracts code lines, comments, function calls, libraries and control flow. |
| 2. LLM extraction | `pipeline/llm_extractor.py` | Business category, technical category, complexity and a short description, returned as schema-constrained JSON and validated. |
| 3. Rule-based extraction | `pipeline/rule_extractor.py` | The same fields from deterministic rules (keywords, function mapping, structural complexity score), with no LLM involved. |
| 4. Comparison | `pipeline/comparator.py` | Per-field agreement between rules and LLM. Disagreements are flagged for human review. |
| 5. Conversion | `pipeline/converter.py` | LLM translation from A to B, with a repair loop: run, capture the error or the structural differences, re-prompt. |
| 6. Validation | `pipeline/validator.py` | Runs the original and the converted script on the same input and compares rows, columns and values (numeric tolerance). |

```
legacy_scripts/*.R
      │
      ▼
 [1] parser ──────────────► ParsedScript (code, comments, calls, libraries, control flow)
      │
      ├──► [2] LLM extractor ─┐
      │                       ├──► [4] comparator ──► extraction_comparison.csv
      ├──► [3] rule extractor ┘                       comparison_summary.csv
      │                                               metadata.csv
      ▼
 [5] converter ──► converted/*.py  ◄─── repair loop (run → error → re-prompt, early stop)
      │
      ▼
 [6] validator ──► Rscript original.R  vs  python converted.py  ──► validation_report.csv
```

## 2. Repository structure

```
├── run_pipeline.py          # single entry point
├── config.py                # paths, model settings, taxonomies, tolerances
├── requirements.txt
├── pipeline/
│   ├── languages.py         # language profiles (R today; SAS = a new profile)
│   ├── parser.py            # step 1
│   ├── llm_client.py        # minimal HTTP client for the local Ollama server
│   ├── llm_extractor.py     # step 2
│   ├── rule_extractor.py    # step 3
│   ├── comparator.py        # step 4
│   ├── converter.py         # step 5
│   ├── runner.py            # executes scripts under the common execution contract
│   └── validator.py         # step 6
├── legacy_scripts/          # 6 sample R scripts (input, syntax A)
├── test_data/               # synthetic CSV inputs, one folder per script, plus generator
├── converted/               # generated Python scripts (syntax B)
├── outputs/                 # deliverables (see section 5)
├── README.md
└── REPORT.md                # challenges, results and lessons learned
```

## 3. Assumptions

- **Languages**: syntax A is R and syntax B is Python 3 with pandas. The case leaves
  both abstract (".a files"). R → Python is a realistic, common migration path.
- **Confidentiality**: the client does not allow code to be sent to external cloud
  APIs. Only a local model is used, `qwen2.5-coder:7b` through Ollama: an
  open-weights, code-specialised model (Apache 2.0) that fits on a 6 GB laptop GPU.
- **Determinism**: temperature 0 and a fixed seed, so results are reproducible and
  auditable.
- **Closed taxonomies**: a fixed list of values is required to compare the two methods.
  - Business: `finance`, `sales`, `HR`, `risk`, `operations`
  - Technical: `ingestion`, `cleaning`, `transformation`, `modeling`, `reporting`
  - Complexity: `simple`, `moderate`, `complex`

  Each script gets a **main** category (compared exactly) and the **list** of all
  categories it touches (compared by overlap), because real scripts often span
  several domains and operations.
- **Common execution contract**: every script, original or converted, is run as
  `<command> <script> <input_1.csv> [<input_2.csv> ...] <output.csv>`.
  The validator therefore compares two files and does not need to understand the
  script. Converted scripts must respect the same contract.
- **Test data**: synthetic CSV files generated with a fixed seed per script
  (`test_data/generate_test_data.py`). No client data is used.
- **Fidelity over correction**: the reference is the legacy behaviour, even when it
  looks like a bug (e.g. `mean()` returning `NA`). A migration must not change
  results silently. Suspected bugs are reported to the business, not fixed during
  the migration.

## 4. How to run

### Prerequisites

- Python 3.10+
- R 4.x (`Rscript`). Its path is set in `config.py` (`RSCRIPT_PATH`).
- Ollama, with the model pulled:

```bash
ollama pull qwen2.5-coder:7b
```

### Install and run

```bash
pip install -r requirements.txt
python test_data/generate_test_data.py   # optional: test data is already committed
python run_pipeline.py                   # or: python run_pipeline.py --input <directory>
```

A full run on the 6 sample scripts takes about 6 minutes on a laptop
(RTX 4050, 6 GB VRAM).

### Main settings (`config.py`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `MODEL_NAME` | `qwen2.5-coder:7b` | local model used for extraction and conversion |
| `TEMPERATURE`, `SEED` | `0`, `42` | deterministic decoding |
| `MAX_REPAIR_ATTEMPTS` | `5` | conversion budget (stops early if the same error repeats) |
| `USE_CONVERSION_NOTES` | `True` | injects the known R → Python pitfalls into the conversion prompt |
| `WARNINGS_AS_ERRORS` | `True` | V2: a runtime warning during the repair loop counts as a crash |
| `STRUCTURAL_FEEDBACK` | `True` | V2: output structure (rows, columns, missing values per column) is compared with the original and differences are sent back to the model, never the values |

Set both V2 settings to `False` to reproduce V1 (also available as git tag `v1`).
| `NUMERIC_RTOL`, `NUMERIC_ATOL` | `1e-6`, `1e-8` | tolerance for numeric comparison |

## 5. Outputs

| File | Granularity | Content |
|------|-------------|---------|
| `outputs/metadata.csv` | one row per script | rule-based and LLM extractions, LLM description, rule evidence |
| `outputs/extraction_comparison.csv` | one row per script and field | rule value, LLM value, overlap, verdict (`agree` / `partial` / `disagree`), review priority |
| `outputs/comparison_summary.csv` | one row per field | strict and lenient agreement rates |
| `outputs/validation_report.csv` | one row per script | conversion status, attempts, stop reason, row and column checks, `content_match`, `order_match`, mismatching cells, verdict and details |
| `outputs/runs/` | per script | raw R and Python outputs, full log of every conversion attempt |

Validation verdicts:

- `identical`: same rows, columns and values, in the same order
- `same_content_different_order`: same values, different row order
- `different`: different row count, columns or values (details are given)
- `not_converted`: no runnable conversion after the repair loop

## 6. Sample scripts

The six scripts cover every category and include deliberate migration traps.

| Script | Business | Technical | Purpose in the test set |
|--------|----------|-----------|-------------------------|
| `01_sales_monthly_summary` | sales | transformation | control case, no trap |
| `02_hr_salary_stats` | HR | transformation | `sd()` uses n−1 (numpy uses n); `mean()` returns `NA` with missing values |
| `03_ops_inventory_cleaning` | operations | cleaning | non-numeric quantities make a naive `astype(float)` crash, which exercises the repair loop |
| `04_sales_commission_payout` | sales / HR / finance (ambiguous) | transformation | 1-based indexing (`1:nrow()`, `[1:3]`), inner join, two input files |
| `05_risk_segmentation` | risk | transformation | `cut()` right-closed bins with values on the boundaries; factor order vs alphabetical order |
| `06_credit_default_model` | finance / risk (ambiguous) | modeling | `glm()` is unpenalised while sklearn's default is L2-penalised; standardisation with `sd()` |

## 7. Results (current run)

**Extraction, rules vs LLM**

| Field | Strict agreement | Lenient agreement (incl. partial) |
|-------|------------------|-----------------------------------|
| business_category | 83% | 83% |
| technical_category | 83% | 83% |
| complexity | 50% | 100% |
| business_domains | 33% | 100% |
| technical_operations | 0% | 83% |

Three high-priority disagreements are flagged for review. The main one is script 06,
finance vs risk, a genuinely ambiguous case.

**Conversion and validation (V2, with V1 for comparison)**

| Script | Conversion (V2) | Attempts | Validation V1 | Validation V2 |
|--------|-----------------|----------|---------------|---------------|
| 01 | success | 1 | identical | identical |
| 02 | runnable (structure still differs) | 5 | different (30 rows instead of 5) | different (one extra column; all values correct) |
| 03 | success | 3 | different (missing costs not imputed) | **identical** |
| 04 | failed (stuck on the same error) | 3 | not converted | not converted |
| 05 | success | 2 | identical | identical |
| 06 | runnable (structure still differs) | 5 | different (one predictor dropped) | different (one predictor dropped) |

V1 gave 2 identical conversions out of 6, V2 gives 3. In both versions, every wrong
conversion is detected: no incorrect conversion was reported as valid.
See `REPORT.md` for the analysis.

## 8. Limitations

- **Small local model**: a 7B model follows instructions imperfectly. It can ignore
  an explicit conversion note, and it drops details in longer scripts.
- **Validation is only as good as the test data**: it proves equivalence on the
  given inputs, not in general. Script 05 is identical on the test data, but its
  code relies on an ordering that holds only by coincidence.
- **The repair loop does not see values**: it fixes crashes and, in V2, structural
  differences. Code with the right structure but wrong values is reported by the
  validator, not repaired automatically.
- **Lexical parser**: regex-based, with no syntax tree. Dynamic calls (`do.call`,
  `eval`) and multi-line constructs are not fully understood.
- **Rule calibration**: keyword lists and complexity thresholds were set on the six
  sample scripts. On a real estate, they should be calibrated on a labelled sample
  and evaluated on held-out scripts.
- **Execution contract**: legacy scripts with hard-coded paths would first need an
  automated rewrite to read their inputs from arguments.
- **Randomness in scripts**: R and Python random generators differ, so scripts with
  random sampling (`set.seed` + `sample`) cannot be compared output to output unless
  the split is fixed in the data.
- **Residual non-determinism**: temperature 0 keeps categories stable, but the wording
  of descriptions and the number of repair attempts can vary slightly between runs
  (floating-point effects on a mixed CPU/GPU execution).
- **Generated code is executed locally**: acceptable on synthetic data. In production
  it should run in a sandbox (container, no network, resource limits).
