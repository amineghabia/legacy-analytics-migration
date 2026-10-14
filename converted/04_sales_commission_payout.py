import pandas as pd
import sys

# Read input files
reps = pd.read_csv(sys.argv[1], dtype=str)
transactions = pd.read_csv(sys.argv[2], dtype=str)

# Only closed deals are commissionable
closed = transactions[transactions['status'] == 'closed']
sales_by_rep = closed.groupby('rep_id')['amount'].sum().reset_index()
sales_by_rep.rename(columns={'amount': 'closed_sales'}, inplace=True)

# Merge with reps data and calculate commission
payout = pd.merge(reps, sales_by_rep, on='rep_id')
payout['commission'] = round(payout['closed_sales'].astype(float) * payout['commission_rate'].astype(float), 2)

# Rank reps by closed sales; the top 3 earn a 2% accelerator
payout = payout.sort_values(by='closed_sales', ascending=False).reset_index(drop=True)
payout['rank'] = range(1, len(payout) + 1)
top_n = 3
payout['accelerator'] = 0
payout.loc[:top_n-1, 'accelerator'] = round(payout.loc[:top_n-1, 'closed_sales'].astype(float) * 0.02, 2)

payout['total_payout'] = payout['commission'] + payout['accelerator']
payout['closed_sales'] = round(payout['closed_sales'].astype(float), 2)

# Write output file
payout.to_csv(sys.argv[3], index=False, na_rep="NA")
