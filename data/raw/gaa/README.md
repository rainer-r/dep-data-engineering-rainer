---
license: cc0-1.0
language:
- en
tags:
- government
- philippines
- budget
- appropriations
- public-finance
size_categories:
- 1M<n<10M
configs:
- config_name: default
  data_files: "gaa.parquet"
---

# General Appropriations Act (GAA) Dataset

### Dataset Summary

This dataset contains detailed Philippine government budget appropriations data from the General Appropriations Act (GAA). It includes 3.7+ million records of government expenditures across departments, agencies, and programs, using the Unified Accounts Code Structure (UACS) classification system. The dataset covers fiscal years 2020-2025 (six years) and provides comprehensive breakdowns of government spending by department, agency, program, expense category, and specific object codes.

The data is primarily in English with some Filipino terms used in agency names and descriptions.

### Languages

The dataset contains text in English and Filipino. Government agency names, department descriptions, and budget classifications.

## Dataset Structure

### Data Instances

```json
{
  "id": 2,
  "department": "01",
  "uacs_dpt_dsc": "Congress of the Philippines (CONGRESS)",
  "agency": "001",
  "uacs_agy_dsc": "Senate",
  "prexc_fpap_id": "100000100001000",
  "dsc": "General management and supervision",
  "operunit": "0000000",
  "uacs_oper_dsc": null,
  "uacs_reg_id": "13",
  "fundcd": "101101",
  "uacs_fundsubcat_dsc": "Specific Budgets of National Government Agencies",
  "uacs_exp_cd": "1",
  "uacs_exp_dsc": "Personnel Services",
  "uacs_sobj_cd": "5010101001",
  "uacs_sobj_dsc": "Basic Salary - Civilian",
  "amt": 543636.0,
  "year": 2020,
  "prexc_level": null,
  "sorder": null,
  "uacs_operdiv_id": null,
  "uacs_div_dsc": null
}
```

### Data Fields

- `id` (int64): Unique identifier for each record
- `department` (string): Department code following UACS classification
- `uacs_dpt_dsc` (string): Department description/name
- `agency` (string): Agency code within the department
- `uacs_agy_dsc` (string): Agency description/name
- `prexc_fpap_id` (string): Program/Project/Activity identifier code
- `dsc` (string): Program/Project/Activity description
- `operunit` (string): Operating unit code
- `uacs_oper_dsc` (string): Operating unit description (often null)
- `uacs_reg_id` (string): Region identifier code
- `fundcd` (string): Fund source code
- `uacs_fundsubcat_dsc` (string): Fund subcategory description
- `uacs_exp_cd` (string): Expense category code (1=Personnel Services, etc.)
- `uacs_exp_dsc` (string): Expense category description
- `uacs_sobj_cd` (string): Specific object of expenditure code (detailed spending classification)
- `uacs_sobj_dsc` (string): Specific object of expenditure description
- `amt` (double): Amount in Philippine Pesos (PHP)
- `year` (int64): Fiscal year (2020-2025)
- `prexc_level` (string): Program execution level (often null)
- `sorder` (string): Sort order (often null)
- `uacs_operdiv_id` (string): Operating division identifier (often null)
- `uacs_div_dsc` (string): Division description (often null)

Note: Many records contain null values for certain fields, particularly at higher aggregation levels where detailed breakdowns are not applicable.

### Data Splits

This dataset does not have predefined train/validation/test splits. It represents aggregated GAA budget data across six fiscal years.

|                | Records   |
|----------------|-----------|
| Total          | 3,776,789 |
| Years covered  | 6 (2020-2025) |

## Dataset Creation

### Source Data

The data was sourced from the Department of Budget and Management (DBM) and normalized into the Unified Accounts Code Structure (UACS) format. The UACS is the official Philippine government chart of accounts that provides a standardized classification system for government financial transactions.

Data was extracted from official budget documents and structured into a relational format with hierarchical classifications (department → agency → program → expense category → specific object).

### Annotations

### Personal and Sensitive Information

This dataset does not contain personal information. All data represents institutional budget allocations at the program and object code level.

## Additional Information

### Licensing Information

This dataset is licensed under the CC0 1.0 Universal license. This means you can copy, modify, distribute and perform the work, even for commercial purposes, all without asking permission.
