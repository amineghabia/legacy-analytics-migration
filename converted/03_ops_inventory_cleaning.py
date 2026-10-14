import pandas as pd
import sys

# Read input files
input_files = sys.argv[1:-1]
output_file = sys.argv[-1]

inventory = pd.read_csv(input_files[0])

# Normalise text fields
inventory['warehouse'] = inventory['warehouse'].str.upper().str.strip()
inventory['item_name'] = inventory['item_name'].str.strip()

# Remove exact duplicate lines (same count sent twice)
inventory = inventory.drop_duplicates()

# Quantities: non-numeric values become NA, then invalid rows are dropped
inventory['quantity'] = pd.to_numeric(inventory['quantity'], errors='coerce')
inventory = inventory[~inventory['quantity'].isna() & (inventory['quantity'] >= 0)]

# Missing unit cost: impute with the median cost
median_cost = inventory['unit_cost'].median(skipna=True)
inventory['unit_cost'].fillna(median_cost, inplace=True)

inventory['stock_value'] = round(inventory['quantity'] * inventory['unit_cost'], 2)

# Stock age relative to the fixed quarter-end reporting date
inventory['last_count_date'] = pd.to_datetime(inventory['last_count_date'])
inventory['days_since_count'] = (pd.to_datetime("2024-06-30") - inventory['last_count_date']).dt.days

inventory = inventory.sort_values(by=['warehouse', 'sku'])
inventory.to_csv(output_file, index=False, na_rep="NA")
