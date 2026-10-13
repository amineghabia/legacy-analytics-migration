# HR compensation review: salary statistics per department
# Headcount, average salary, salary dispersion and average bonus.
# Requested by HR to prepare the annual pay equity review.

args <- commandArgs(trailingOnly = TRUE)
employees <- read.csv(args[1], stringsAsFactors = FALSE)

headcount  <- tapply(employees$employee_id, employees$department, length)
avg_salary <- tapply(employees$salary, employees$department, mean)
sd_salary  <- tapply(employees$salary, employees$department, sd)
avg_bonus  <- tapply(employees$bonus, employees$department, mean)

result <- data.frame(
  department = names(headcount),
  headcount  = as.integer(headcount),
  avg_salary = round(as.numeric(avg_salary), 2),
  sd_salary  = round(as.numeric(sd_salary), 2),
  avg_bonus  = round(as.numeric(avg_bonus), 2)
)

write.csv(result, args[2], row.names = FALSE)
