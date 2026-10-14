# Warehouse inventory cleaning
# Standardises the raw stock extract sent by the warehouses before it is
# loaded into the operations dashboard: text normalisation, duplicate removal,
# invalid quantities, missing costs and stock age.

args <- commandArgs(trailingOnly = TRUE)
inventory <- read.csv(args[1], stringsAsFactors = FALSE)

# Normalise text fields
inventory$warehouse <- toupper(trimws(inventory$warehouse))
inventory$item_name <- trimws(inventory$item_name)

# Remove exact duplicate lines (same count sent twice)
inventory <- inventory[!duplicated(inventory), ]

# Quantities: non-numeric values become NA, then invalid rows are dropped
inventory$quantity <- suppressWarnings(as.numeric(inventory$quantity))
inventory <- inventory[!is.na(inventory$quantity) & inventory$quantity >= 0, ]

# Missing unit cost: impute with the median cost
median_cost <- median(inventory$unit_cost, na.rm = TRUE)
inventory$unit_cost[is.na(inventory$unit_cost)] <- median_cost

inventory$stock_value <- round(inventory$quantity * inventory$unit_cost, 2)

# Stock age relative to the fixed quarter-end reporting date
inventory$last_count_date <- as.Date(inventory$last_count_date)
inventory$days_since_count <- as.numeric(as.Date("2024-06-30") - inventory$last_count_date)

inventory <- inventory[order(inventory$warehouse, inventory$sku), ]
write.csv(inventory, args[2], row.names = FALSE)
