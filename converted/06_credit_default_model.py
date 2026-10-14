import pandas as pd
import statsmodels.api as sm
import numpy as np
import sys

args = sys.argv[1:-1]
loans = pd.read_csv(args[0], dtype=str)

model_vars = ["defaulted", "income", "loan_amount", "credit_score",
              "employment_years", "prior_default"]
loans = loans[model_vars].dropna()
if len(loans) < 50:
    raise ValueError("Not enough complete observations to fit the model")

loans["debt_to_income"] = loans["loan_amount"].astype(float) / loans["income"].astype(float)

# Standardise continuous predictors so coefficients are comparable
predictors = ["debt_to_income", "credit_score", "employment_years"]
for v in predictors:
    loans[v] = (loans[v].astype(float) - loans[v].astype(float).mean()) / loans[v].astype(float).std()

X = loans[predictors]
y = loans["defaulted"].astype(int)
X = sm.add_constant(X)

model = sm.GLM(y, X, family=sm.families.Binomial()).fit()

# Coefficient table for model governance review
coefs = model.summary2().tables[1]
coefs.columns = ["estimate", "std_error", "z_value", "p_value", "conf_lower", "conf_upper"]
coefs["term"] = coefs.index
coefs["term"][coefs["term"] == "const"] = "intercept"
coefs["odds_ratio"] = np.exp(coefs["estimate"])
coefs = coefs[["term", "estimate", "std_error", "z_value", "p_value", "odds_ratio"]]
coefs[["estimate", "std_error", "z_value", "p_value"]] = coefs[["estimate", "std_error", "z_value", "p_value"]].round(4)

coefs.to_csv(sys.argv[-1], index=False, na_rep="NA")
