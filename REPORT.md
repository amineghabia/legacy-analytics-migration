# Report: Challenges, Results and Lessons Learned

This report covers what was built, what the results are, the challenges met
during development and how each was addressed. All figures come from the run
committed in `outputs/` unless stated otherwise.

---

## 1. Summary

- A local pipeline (R → Python, Ollama `qwen2.5-coder:7b`, plain Python) runs the
  six steps of the case end to end with one command, in about 4 minutes for six
  scripts on a laptop GPU.
- **Classification**: rules and LLM agree on the main business and technical
  category for 5 of 6 scripts (83%). Three disagreements are flagged as high
  priority. The most significant one (script 06, finance vs risk) is a genuine
  ambiguity, not a mistake.
- **Conversion**: 5 of 6 scripts produce runnable Python. 4 of these needed the
  repair loop. Script 04 stays blocked on the same error and is flagged.
- **Validation**: 2 conversions are identical to the original outputs. **3 run
  without any error but produce wrong results**, and only the output comparison
  reveals it.
- **No incorrect conversion is reported as valid.** The pipeline is a reliable
  triage tool: it accelerates the safe cases and directs human effort to the
  risky ones.

---

## 2. Results in detail

### 2.1 Extraction: rules vs LLM

| Field | Agree | Partial | Disagree | Strict agreement | Lenient agreement |
|-------|-------|---------|----------|------------------|-------------------|
| business_category | 5 | 0 | 1 | 0.83 | 0.83 |
| business_domains | 2 | 4 | 0 | 0.33 | 1.00 |
| technical_category | 5 | 0 | 1 | 0.83 | 0.83 |
| technical_operations | 0 | 5 | 1 | 0.00 | 0.83 |
| complexity | 3 | 3 | 0 | 0.50 | 1.00 |

Verdict rules:
- **Main category**: `agree` if equal. `partial` if each method lists the other's
  choice among its domains. Otherwise `disagree`.
- **Complexity**: `partial` if one level apart, because complexity is ordinal.
- **Lists**: Jaccard overlap (|A ∩ B| / |A ∪ B|). `partial` if ≥ 0.5.

High-priority disagreements:

| Script | Field | Rules | LLM | Analysis |
|--------|-------|-------|-----|----------|
| 06 | business_category | finance | risk | Genuinely ambiguous: a probability of default model owned by credit risk and used by finance for IFRS 9 provisions. The rules count more finance words (IFRS, provision, loan). The LLM recognises a risk model. This needs a business owner decision. |
| 05 | technical_category | transformation | reporting | The rules are arguably right: the script only aggregates. The LLM is influenced by the word "reports" in the comments. |
| 05 | technical_operations | ingestion, transformation | cleaning, transformation, reporting | Same cause. |

Observed patterns:
- The LLM **compresses complexity towards the middle**: scripts 03 and 04 are
  rated moderate (rules: simple), script 06 moderate (rules: complex).
- The LLM **sees semantics the rules miss**: it adds HR to script 04 (commissions
  are compensation). The rules found only one HR keyword, "payroll", below the
  secondary-domain threshold.
- The LLM tends to **omit "ingestion"**, probably considering a single `read.csv`
  not worth listing. It also adds "finance" to scripts 01 and 02 as a secondary
  domain (revenue, salaries).

### 2.2 Conversion and validation

| Script | Attempts | Errors met during the repair loop | Validation | Cause of the difference |
|--------|----------|-----------------------------------|------------|-------------------------|
| 01 | 1 | none | **identical** | |
| 02 | 2 | `TypeError: dtype 'str' does not support operation 'mean'` | **different**: 30 rows instead of 5, extra column `employee_id` | `groupby().transform()` keeps one row per employee instead of aggregating per department |
| 03 | 2 | `TypeError: Cannot perform reduction 'median' with string dtype` | **different**: 4 cells (`unit_cost` and `stock_value` NA instead of values) | `df['unit_cost'].fillna(median, inplace=True)` has no effect in pandas 3 (Copy-on-Write) |
| 04 | 3, stopped | `NameError: sys`, then the same `ValueError` twice | **not converted** | `pd.read_csv(..., dtype=str)`: amounts are concatenated as strings instead of summed |
| 05 | 2 | `NameError: sys` | **identical** | correct on the test data, but relies on a coincidence (see 3.8) |
| 06 | 3 | `NameError: sys`, `ValueError: Length mismatch` | **different**: 4 coefficients instead of 5 | predictor `prior_default` dropped from the model |

### 2.3 Planned traps vs actual errors

| Planned trap | Script | Did the LLM fall into it? |
|--------------|--------|---------------------------|
| `sd()` n−1 vs `np.std()` n | 02 | No: `transform('std', ddof=1)` |
| `mean()` with NA (R returns NA) | 02 | Not observable: masked by the structural error |
| non-numeric values → crash | 03 | Yes, then repaired with `pd.to_numeric(errors="coerce")` |
| 1-based indexing | 04 | Not observable: conversion failed earlier |
| `cut()` right-closed bins | 05 | No: `pd.cut` defaults match R |
| factor order vs alphabetical | 05 | No: categorical labels keep the order |
| `glm` vs sklearn L2 penalty | 06 | No: `statsmodels` GLM used |
| `sd()` in standardisation | 06 | No: pandas `.std()` (n−1) used |

**Key finding: the real errors are not the ones anticipated.** The model avoided
most of the classic semantic traps (probably helped by the conversion notes), but
made more basic mistakes: wrong output structure, a forgotten variable, outdated
library behaviour, misreading an R option. A migration cannot rely on a checklist
of known pitfalls. Comparing outputs is the only safeguard that catches unknown
errors.

---

## 3. Challenges and how they were addressed

### 3.1 Confidentiality and hardware: choosing a local model

- **Constraint**: no code sent to external APIs.
- **Choice**: `qwen2.5-coder:7b` through Ollama. It is code-specialised, open
  weights (Apache 2.0) and supports JSON-constrained outputs. At 4.7 GB it fits a
  6 GB laptop GPU. A 14B model would spill heavily onto the CPU and be 5 to 10
  times slower.
- **Observed**: even the 7B runs 82% GPU / 18% CPU (display memory takes part of
  the VRAM). The context window is kept at 4096 tokens: enough for the scripts,
  and a larger one would increase the CPU offload.
- **Performance**: about 6 s per extraction and 12 to 60 s per conversion,
  depending on the number of repair attempts.

### 3.2 Making two different methods comparable

- **Problem**: the case asks for an open "business process or domain", which
  cannot be compared automatically, and real scripts span several categories.
- **Solution**: closed taxonomies, shared by the rules, the LLM schema and the
  validation. Each script gets a **main** category (who owns it) and a **list** of
  all categories involved. Comparison uses three verdict levels (`agree`,
  `partial`, `disagree`) with Jaccard overlap for lists. This separates genuine
  ambiguity from real disagreement.
- **Test set design**: 4 unambiguous scripts as references and 2 deliberately
  ambiguous ones (04, 06). Without clear cases, model errors could not be told
  apart from questions that have no single answer.

### 3.3 Designing and calibrating the rules

- **Business**: keyword counting over the file name, comments and identifiers
  (`closed_sales` → `closed`, `sales`), with plural matching. A secondary domain
  needs at least 50% of the main domain's evidence.
- **Technical**: function calls mapped to categories by the language profile.
  Modeling calls weigh 3: one `glm()` makes a modeling script, while `read.csv()`
  appears everywhere.
- **Complexity**: five dimensions (lines of code, distinct functions, control
  flow, user-defined functions, libraries), 0 to 2 points each, total 0 to 10:
  0-1 simple, 2-3 moderate, 4+ complex. This maps the case's criteria (logic,
  length, dependencies). Round thresholds (15/30 lines, 10/20 functions) avoid
  fitting the six samples.
- **Calibration issue**: the first run classified scripts 02 and 05 as "cleaning",
  because `as.numeric()` / `as.integer()` were used 4 to 5 times only to build the
  output table. They were removed from the cleaning list, for the same reason
  `write.csv` is not counted as reporting: plumbing present in every script carries
  no information.
- **Caveat**: adjusting rules after looking at results risks overfitting to the
  test set. On a real estate, calibrate on a labelled sample and evaluate on
  held-out scripts.
- **Benefit**: every rule-based decision keeps its evidence (e.g. `finance: ifrs,
  provision, loan`), so it is fully explainable, unlike the LLM.

### 3.4 Getting reliable structured outputs from the LLM

- **Two layers**:
  1. Constrained decoding: the JSON schema (with enums from the taxonomies) is sent
     to Ollama, which only allows tokens producing valid JSON.
  2. Python validation of the same rules, one retry, then the script is flagged
     `invalid` instead of crashing the pipeline.
- **Normalisation**: the main category is added to its list if missing, and lists
  are de-duplicated and ordered.
- **Independence**: the LLM never sees the rule-based results, otherwise it could
  anchor on them and the comparison would be meaningless.
- **Result**: 6/6 valid answers on the first attempt.

### 3.5 Determinism

- Temperature 0 (always the most likely token) plus a fixed seed.
- Two consecutive calls in the same process gave strictly identical answers.
- **Residual variation across runs**: category fields were stable over all runs,
  but the wording of one description changed slightly, and script 06 needed 4
  repair attempts in one run and 3 in another. Explanation: floating-point
  differences on a mixed CPU/GPU execution can flip near-tied tokens.
- **Consequence**: only closed fields are used for automated decisions. Free text
  (the description) is informative only.

### 3.6 Conversion: iterating on the repair loop

The conversion step went through three iterations. The figures below are from
development runs.

| Iteration | Change | Runnable conversions |
|-----------|--------|----------------------|
| v0 | basic prompt, max 3 attempts | 4/6 (04 and 05 failed) |
| v1 | + conversion note on `stringsAsFactors`, + "find the root cause" repair prompt | 4/6 (05 fixed; 06 ran out of attempts while still progressing) |
| v2 (current) | + budget of 5 attempts with early stop when the same error repeats | 5/6 (04 flagged as stuck) |

**Root cause found in v0**: the model translated
`read.csv(file, stringsAsFactors = FALSE)` into `pd.read_csv(file, dtype=str)`.
The R option only keeps text columns as plain strings instead of factors; numeric
columns stay numeric. Read as strings, the amounts were **concatenated instead of
summed** (`'9448.16' + '10561.45'` → `'9448.1610561.45'`), and the script crashed
later on a conversion to float.

**Why the repair loop failed**: the traceback points to the line that crashes
(the sum), not the line that is wrong (the file read). At temperature 0 the model
kept patching the symptom with `astype(float)` calls.

**Fixes**:
1. A conversion note added to the R profile, as general R knowledge (the option
   appears in most pre-4.0 R code), not a fix tailored to one script.
2. A repair prompt asking for the root cause and pointing at data types. This
   fixed the same `dtype=str` issue in scripts 02 and 03 in the final run.
3. An adaptive budget: up to 5 attempts while each attempt produces a new error
   (the model is progressing, as for 06: missing import, then a shape error, then
   success), and an early stop when the same error repeats (the model is stuck and
   would repeat itself).

**Remaining failure (04)**: the 7B model keeps writing `dtype=str` despite the
explicit note. A small model follows instructions poorly when they contradict a
strong learned association. The script is flagged with a precise diagnosis.
Possible fix, not applied to avoid tailoring the pipeline to the samples: a
deterministic "modernisation" pre-processing that removes options that are no-ops
in current R (`stringsAsFactors = FALSE` is the default since R 4.0) before
conversion.

**Most frequent repaired error**: missing `import sys` (3 scripts). It is trivial,
but would have broken those conversions without the loop.

### 3.7 Silent errors: code that runs but is wrong

Three conversions were declared successful by the repair loop (they run) but are
wrong:

- **02, wrong structure**: `transform('mean')` instead of an aggregation, giving 30
  rows instead of 5. Ironically, the model handled `ddof=1` correctly.
- **03, library version drift**: `df['col'].fillna(value, inplace=True)` worked in
  pandas 1.x/2.x. In pandas 3 (Copy-on-Write) it modifies a temporary copy and
  silently does nothing. The model learned from older pandas code. pandas emits a
  `ChainedAssignmentError` warning but no error.
- **06, dropped variable**: `prior_default` is missing from the model, so every
  coefficient changes. The longest script is where the model loses details.

**How it was addressed**: by design, the repair loop does not send the expected
output back to the model. It could otherwise fit the numbers (even hard-code them)
instead of fixing the logic. These errors are caught by the validator and reported
with cell-level details (e.g. `row 2 'unit_cost': R=48.0 Py=nan`) to guide the
human fix.

### 3.8 Validation coverage: identical is not the same as correct

Script 05 is `identical`, but its code builds the result from `value_counts()`,
which orders bands by **frequency**. On the test data, the frequency order
(18, 10, 10, 5) happens to match the business order (low, medium, high,
critical). With other data, the same code would misalign the bands.

**Lesson**: output comparison proves equivalence on the test inputs only. Its
strength depends on test data coverage. Mitigation: several test datasets per
script, including edge cases, and code review for business-critical scripts.

### 3.9 Comparing outputs across two languages

- **Cosmetic differences**: R quotes strings in CSV and pandas does not. Both files
  are parsed before comparison, never compared as raw text.
- **Missing values**: NA vs NA is equal, NA vs a value is a difference. This is what
  caught script 03.
- **Floating point**: relative tolerance 1e-6 and absolute tolerance 1e-8. This
  absorbs technical noise (operation order) but stays tight enough to catch a
  method difference (n vs n−1 shifts values by ~0.1% on 388 rows, well above the
  tolerance).
- **Row order**: two separate verdicts, `content_match` (order-insensitive) and
  `order_match`, because whether order matters is a business question.
- **Fair comparison**: the validator reruns both scripts itself and deletes stale
  outputs before each run.

### 3.10 Designing test data

- **Synthetic** (no client data) and **reproducible**: one random generator with
  its own seed per script, so changing one dataset never changes another. The
  first version shared one generator across scripts, which made datasets depend
  on generation order. This was fixed.
- **Designed to expose traps**: small HR departments (5-7 people) so that n vs n−1
  is visible (~11% at n = 5); risk scores forced onto band limits (30, 60, 80),
  because boundary values are where off-by-one errors hide; a sales rep with no
  transaction to test the join type; messy text and duplicates for cleaning.
- **No random sampling in scripts**: R and Python random generators produce
  different draws for the same seed, so a random train/test split would make the
  outputs incomparable. In production, the split should be fixed in the data.

### 3.11 Robustness of the pipeline itself

- A failing script (LLM error, conversion failure, crash of the original) never
  stops the pipeline. It is recorded with a status and the run continues.
- Every conversion attempt (code + error) is logged in `outputs/runs/` for audit.
- Generated code runs locally on synthetic data. In production it should run in
  a sandbox (container, no network, CPU/memory limits).

---

## 4. Lessons learned

1. **"It runs" is not "it is correct."** Half of the runnable conversions were
   wrong. Output-based validation is not optional.
2. **The useful metric is false positives, not conversion rate.** A pipeline that
   converts 50% reliably and flags the rest is more valuable than one that claims
   100%.
3. **LLM errors cannot be fully anticipated.** Known-pitfall notes help, but the
   errors observed were mostly unexpected. Safeguards must be generic.
4. **Rules and LLM are complementary.** Rules are transparent and stable but blind
   to meaning. The LLM understands context but is opaque and sometimes swayed by
   wording. Their disagreements point to the cases worth a human look.
5. **The target environment matters.** A model trained on older library versions
   produces code that silently misbehaves on newer ones.
6. **Repair loops need a stopping rule.** Progress-based early stopping saves
   compute on hopeless cases without cutting off cases that are converging.

---

## 5. Next steps

Ranked by expected impact relative to effort:

| # | Improvement | Expected effect |
|---|-------------|-----------------|
| 1 | Larger code model (e.g. 32B class) on an internal GPU server | Better instruction following, fewer omissions. Largest single lever. |
| 2 | Structural feedback from the validator to the converter: row count, column names, NA counts per column, without values | Likely fixes 02, 03 and 06, with no risk of the model copying expected numbers |
| 3 | Treat runtime warnings as errors when running converted code | Script 03 would crash on `ChainedAssignmentError` and enter the repair loop |
| 4 | State target library versions in the prompt (pandas 3, Copy-on-Write) | Fewer version-drift errors |
| 5 | Several test datasets per script, including edge cases | Catches code that is correct only by coincidence (05) |
| 6 | Few-shot examples of validated conversions in the prompt (migration playbook) | Fewer recurring errors |
| 7 | Deterministic pre-processing of legacy idioms (e.g. no-op options) | Unblocks cases like 04 |
| 8 | A second language profile (SAS) | Demonstrates the language-agnostic design |

### Scaling to a real estate (e.g. 2,000 scripts)

- **Throughput**: about 40 s per script on this laptop, roughly 22 hours
  sequentially. On a GPU server with parallel requests, a few hours.
- **Triage output**: scripts `identical` → fast-track review. `different` →
  developer fix, starting from the cell-level details. `not_converted` → manual
  conversion. Classification disagreements → business owner decision.
- **Prioritisation**: complexity and business domain from step 2-3 can order the
  migration waves (simple, low-risk scripts first; regulated models such as PD
  models with full review).
