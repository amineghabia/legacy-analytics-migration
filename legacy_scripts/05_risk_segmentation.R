# Credit risk segmentation of the active portfolio
# Groups active customers into risk bands based on the score produced by the
# scoring engine, then reports exposure and portfolio share per band.
# Bands (risk committee policy): low <= 30 < medium <= 60 < high <= 80 < critical

args <- commandArgs(trailingOnly = TRUE)
customers <- read.csv(args[1], stringsAsFactors = FALSE)

active <- customers[customers$account_status == "active", ]

active$risk_band <- cut(active$risk_score,
                        breaks = c(-Inf, 30, 60, 80, Inf),
                        labels = c("low", "medium", "high", "critical"))

n_customers    <- table(active$risk_band)
total_exposure <- tapply(active$balance, active$risk_band, sum)
avg_score      <- tapply(active$risk_score, active$risk_band, mean)

segments <- data.frame(
  risk_band      = names(n_customers),
  n_customers    = as.integer(n_customers),
  total_exposure = round(as.numeric(total_exposure), 2),
  avg_risk_score = round(as.numeric(avg_score), 2)
)
segments$exposure_share <- round(segments$total_exposure / sum(segments$total_exposure), 4)

write.csv(segments, args[2], row.names = FALSE)
