# Monthly sales summary by region
# Computes revenue per order, then total revenue and units per month and region.
# Used by the sales team for the monthly performance review.

args <- commandArgs(trailingOnly = TRUE)
sales <- read.csv(args[1], stringsAsFactors = FALSE)

sales$revenue <- sales$units * sales$unit_price
sales$month <- format(as.Date(sales$order_date), "%Y-%m")

summary_df <- aggregate(cbind(units, revenue) ~ month + region, data = sales, FUN = sum)
summary_df$revenue <- round(summary_df$revenue, 2)
summary_df <- summary_df[order(summary_df$month, summary_df$region), ]

write.csv(summary_df, args[2], row.names = FALSE)
