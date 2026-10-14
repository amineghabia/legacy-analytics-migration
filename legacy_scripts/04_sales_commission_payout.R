# Quarterly sales commission payout
# Joins the sales reps master file with Q1 transactions, computes each rep's
# commission on closed deals and an accelerator bonus for the top 3 performers.
# Output is sent to payroll and to finance for the commission accrual.

args <- commandArgs(trailingOnly = TRUE)
reps <- read.csv(args[1], stringsAsFactors = FALSE)
transactions <- read.csv(args[2], stringsAsFactors = FALSE)

# Only closed deals are commissionable
closed <- transactions[transactions$status == "closed", ]
sales_by_rep <- aggregate(amount ~ rep_id, data = closed, FUN = sum)
names(sales_by_rep)[2] <- "closed_sales"

payout <- merge(reps, sales_by_rep, by = "rep_id")
payout$commission <- round(payout$closed_sales * payout$commission_rate, 2)

# Rank reps by closed sales; the top 3 earn a 2% accelerator
payout <- payout[order(-payout$closed_sales), ]
payout$rank <- 1:nrow(payout)
top_n <- 3
payout$accelerator <- 0
payout$accelerator[1:top_n] <- round(payout$closed_sales[1:top_n] * 0.02, 2)

payout$total_payout <- payout$commission + payout$accelerator
payout$closed_sales <- round(payout$closed_sales, 2)

write.csv(payout, args[3], row.names = FALSE)
