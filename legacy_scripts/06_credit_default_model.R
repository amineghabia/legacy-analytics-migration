# Probability of default (PD) model for the retail loan book
# Logistic regression of loan default on borrower characteristics.
# Coefficients are reviewed by the credit risk team and used by finance to
# estimate expected credit losses for the IFRS 9 loan loss provision.

library(stats)

args <- commandArgs(trailingOnly = TRUE)
loans <- read.csv(args[1], stringsAsFactors = FALSE)

model_vars <- c("defaulted", "income", "loan_amount", "credit_score",
                "employment_years", "prior_default")
loans <- na.omit(loans[, model_vars])
if (nrow(loans) < 50) {
  stop("Not enough complete observations to fit the model")
}

loans$debt_to_income <- loans$loan_amount / loans$income

# Standardise continuous predictors so coefficients are comparable
standardize <- function(x) {
  (x - mean(x)) / sd(x)
}
predictors <- c("debt_to_income", "credit_score", "employment_years")
for (v in predictors) {
  loans[[v]] <- standardize(loans[[v]])
}

model <- glm(defaulted ~ debt_to_income + credit_score + employment_years + prior_default,
             data = loans, family = binomial(link = "logit"))

# Coefficient table for model governance review
coefs <- as.data.frame(summary(model)$coefficients)
names(coefs) <- c("estimate", "std_error", "z_value", "p_value")
coefs$term <- rownames(coefs)
coefs$term[coefs$term == "(Intercept)"] <- "intercept"
coefs$odds_ratio <- exp(coefs$estimate)
coefs <- coefs[, c("term", "estimate", "std_error", "z_value", "p_value", "odds_ratio")]
coefs[, -1] <- round(coefs[, -1], 4)

write.csv(coefs, args[2], row.names = FALSE)
