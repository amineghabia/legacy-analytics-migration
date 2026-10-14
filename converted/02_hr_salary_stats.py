import pandas as pd
import sys

# Read input files
input_files = sys.argv[1:-1]
output_file = sys.argv[-1]

# Initialize an empty list to store results
results = []

# Process each input file
for file in input_files:
    employees = pd.read_csv(file)
    
    headcount = employees.groupby('department')['employee_id'].transform('count')
    avg_salary = employees.groupby('department')['salary'].transform('mean')
    sd_salary = employees.groupby('department')['salary'].transform('std', ddof=1)
    avg_bonus = employees.groupby('department')['bonus'].transform('mean')
    
    result = employees[['department', 'employee_id']].drop_duplicates().reset_index(drop=True)
    result['headcount'] = headcount
    result['avg_salary'] = avg_salary.round(2)
    result['sd_salary'] = sd_salary.round(2)
    result['avg_bonus'] = avg_bonus.round(2)
    
    results.append(result)

# Concatenate all results
final_result = pd.concat(results, ignore_index=True)

# Write the result to the output file
final_result.to_csv(output_file, index=False, na_rep="NA")
