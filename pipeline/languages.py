"""Language profiles: everything that depends on the source language.

The rest of the pipeline only reads a profile, so migrating another legacy
language (e.g. SAS) means adding a profile here, not changing the engine.

A profile contains three kinds of information:
  1. operational   - how to recognise, parse and execute a script
  2. rules         - function -> technical category mapping (rule-based extractor)
  3. knowledge     - known semantic pitfalls, injected in the conversion prompt
"""

R_PROFILE = {
    "name": "R",
    "target_name": "Python (pandas)",

    # 1. Operational ---------------------------------------------------------
    "extension": ".R",
    "comment_prefix": "#",
    "run_command": ["Rscript"],  # replaced by config.RSCRIPT_PATH at runtime
    # library(dplyr) / require("ggplot2")
    "library_pattern": r"\b(?:library|require)\(\s*['\"]?([\w.]+)",
    # stats::glm -> explicit namespace usage also counts as a dependency
    "namespace_pattern": r"\b([A-Za-z][\w.]*)::",
    # any identifier directly followed by "(" is a call
    "function_call_pattern": r"([A-Za-z_.][\w.]*)\s*\(",
    "control_flow_keywords": ["if", "else", "for", "while", "repeat", "switch", "tryCatch"],
    "function_definition_pattern": r"<-\s*function\s*\(",

    # 2. Rules for the deterministic extractor ------------------------------
    # Business keywords are language-agnostic and live in rule_extractor.py.
    "technical_keywords": {
        "ingestion": [
            "read.csv", "read.table", "read.delim", "read_csv", "read_excel",
            "readRDS", "fread", "scan", "dbConnect", "dbGetQuery", "download.file",
        ],
        "cleaning": [
            "na.omit", "is.na", "complete.cases", "drop_na", "replace_na",
            "trimws", "tolower", "toupper", "gsub", "sub", "duplicated",
            "unique", "distinct", "as.Date",
            # as.numeric / as.integer are left out on purpose: they are mostly
            # used as plumbing to build output tables, not to clean data.
        ],
        "transformation": [
            "aggregate", "tapply", "sapply", "lapply", "apply", "merge",
            "mutate", "group_by", "summarise", "summarize", "arrange", "order",
            "transform", "cut", "factor", "ifelse", "cumsum", "rbind", "cbind",
            "reshape", "pivot_longer", "pivot_wider", "left_join", "inner_join",
        ],
        "modeling": [
            "lm", "glm", "predict", "nls", "kmeans", "randomForest",
            "anova", "t.test", "coef", "confint",
        ],
        "reporting": [
            "ggplot", "plot", "hist", "barplot", "pdf", "png", "dev.off",
            "kable", "print", "cat", "sprintf",
        ],
    },

    # 3. Knowledge for the converter ----------------------------------------
    "conversion_notes": [
        "read.csv(..., stringsAsFactors = FALSE) only keeps text columns as plain "
        "strings instead of factors; numeric columns stay numeric. It translates "
        "to a plain pd.read_csv(path): never use dtype=str.",
        "R vectors and data frames are 1-based and R slices include both ends "
        "(df[2:4, ] = rows 2, 3 and 4); pandas iloc is 0-based and end-exclusive.",
        "R sd() and var() use the sample formula (n-1). numpy std()/var() default "
        "to ddof=0; use ddof=1 or pandas .std()/.var().",
        "R mean(), sum(), max() return NA if any value is NA unless na.rm=TRUE; "
        "pandas skips NaN by default. Use skipna=False to reproduce R behaviour.",
        "R factor levels define the order of groups and outputs; pandas groupby "
        "sorts alphabetically. Use pd.Categorical(..., categories=[...], ordered=True).",
        "R cut() intervals are right-closed by default; check pd.cut right= and "
        "include_lowest= arguments.",
        "R glm(family = binomial) is an unpenalised logistic regression; "
        "sklearn LogisticRegression is L2-penalised by default. Use statsmodels.",
        "R write.csv(..., row.names = FALSE) corresponds to to_csv(index=False). "
        "Write NA values as the string 'NA' (na_rep='NA') to match R output.",
    ],
}

PROFILES = {"R": R_PROFILE}


def get_profile(name: str) -> dict:
    """Return the profile of a source language, e.g. get_profile('R')."""
    if name not in PROFILES:
        raise ValueError(f"Unknown language '{name}'. Available: {list(PROFILES)}")
    return PROFILES[name]
