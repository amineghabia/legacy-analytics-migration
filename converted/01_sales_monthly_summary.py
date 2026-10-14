import pandas as pd
import sys

# Monthly sales summary by region
# Computes revenue per order, then total revenue and units per month and region.
# Used by the sales team for the monthly performance review.

input_files = sys.argv[1:-1]
output_file = sys.argv[-1]

# Read input files
sales = pd.concat([pd.read_csv(file, parse_dates=['order_date'], dtype={'region': str}) for file in input_files])

# Compute revenue per order
sales['revenue'] = sales['units'] * sales['unit_price']

# Extract month from order_date
sales['month'] = sales['order_date'].dt.strftime('%Y-%m')

# Aggregate data by month and region
summary_df = sales.groupby(['month', 'region']).agg({'units': 'sum', 'revenue': 'sum'}).reset_index()

# Round revenue to 2 decimal places
summary_df['revenue'] = summary_df['revenue'].round(2)

# Sort by month and region
summary_df = summary_df.sort_values(by=['month', 'region'])

# Write the result to the output file
summary_df.to_csv(output_file, index=False, na_rep="NA")
