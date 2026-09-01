# Data Dictionary — General Appropriations Act (GAA) — bettergovph/gaa on Hugging Face

- **source:** gaa
- **source_url:** https://huggingface.co/datasets/bettergovph/gaa
- **format:** parquet
- **grain:** appropriation line at department x agency x program x operating unit x region x fund x expense class x object code x fiscal year

## columns

| name | type | nullable | description |
|---|---|---|---|
| agency | string | false | Agency code within the department |
| amt | double | false | Amount in Philippine Pesos (PHP); 11 negative rows observed |
| department | string | false | Department code following UACS classification |
| dsc | string | false | Program/Project/Activity description |
| fundcd | string | false | Fund source code |
| id | int64 | false | Unique identifier for each record |
| operunit | string | false | Operating unit code |
| prexc_fpap_id | string | false | Program/Project/Activity identifier code |
| prexc_level | string | true | Program execution level (often null) |
| sorder | string | true | Sort order (often null) |
| uacs_agy_dsc | string | false | Agency description/name |
| uacs_div_dsc | string | true | Division description (often null) |
| uacs_dpt_dsc | string | false | Department description/name |
| uacs_exp_cd | string | false | Expense category code (1=PS, 2=MOOE, 3=CO, 6=FINEX) |
| uacs_exp_dsc | string | false | Expense category description |
| uacs_fundsubcat_dsc | string | false | Fund subcategory description |
| uacs_oper_dsc | string | false | Operating unit description (README says often null; observed 0 nulls on disk) |
| uacs_operdiv_id | string | true | Operating division identifier (often null) |
| uacs_reg_id | string | false | Region identifier code (PSA 01-19; also '00' central-office and 'nan' unassigned) |
| uacs_sobj_cd | string | false | Specific object of expenditure code |
| uacs_sobj_dsc | string | false | Specific object of expenditure description |
| year | int64 | false | Fiscal year (2020-2026) |

## coverage

- **column_count:** 22
- **fiscal_years:**
  - 2020
  - 2021
  - 2022
  - 2023
  - 2024
  - 2025
  - 2026
- **row_count:** 4538396
- **size_bytes:** 79707700

## coverage_anchors

- **fiscal_years:** Same live HF query. FY2026 present, matching CONTEXT.md note that GAA publishes BARMM/NIR rows beginning FY2026.
- **note_readme_stale:** The in-repo dataset README.md (data/raw/gaa/README.md) claims 3,776,789 records over FY2020-2025. The live HF card and the on-disk data agree on 4,538,396 records over FY2020-2026, so the README is treated as stale upstream metadata.
- **row_count:** Hugging Face datasets-server /size?dataset=bettergovph/gaa (fetched 2026-08-30): num_rows=4538396, num_columns=22, num_bytes_parquet_files=79707700. On-disk parquet byte size agrees with the live card.
- **size_bytes:** Transposition fixed 2026-09-01: this literal was previously recorded as 79770700 (digits transposed). The on-disk file, the data/raw/manifest.json entry, and the fetched live HF card all agree on 79707700. The same correction applies to files[0].size_bytes.

## files

| relative_path | role | size_bytes |
|---|---|---|
| gaa/README.md | metadata |  |
| gaa/gaa.parquet | data | 79707700 |

## reference_values

- **known_anomalies:**
  - **negative_amt_count:** 11
  - **uacs_reg_id_special_values_ok:** Values '00' (central office), 'nan' (unassigned), '15' (ARMM, folds to '19'), '18' (NIR) are expected per CONTEXT.md domain rules.
- **uacs_exp_cd_allowed:**
  - 1
  - 2
  - 3
  - 6
  - nan
- **uacs_reg_id_allowed:**
  - 00
  - 01
  - 02
  - 03
  - 04
  - 05
  - 06
  - 07
  - 08
  - 09
  - 10
  - 11
  - 12
  - 13
  - 14
  - 15
  - 16
  - 17
  - 18
  - 19
  - nan
