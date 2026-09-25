# Data Dictionary — BIR Internal Revenue Collections by Region and Province (PSCG basis)

- **source:** tax
- **source_url:** https://www.bir.gov.ph/collection-statistics
- **format:** xlsx
- **grain:** collections at particular (region/province/city aggregation line) x period column (year | month | quarter | semester | total)

## coverage

- **note_unregistered_workbook:** A 4th workbook (20260716_Monthly_Collection_PSCG_JanJun2026 (D) upload.xlsx) exists on disk and in git but is absent from the manifest, so it has no recorded source URL. It is deliberately excluded from the committed inventory; the two should-tier unregistered-file warnings are expected. Whether its January-June 2026 coverage enters scope is an M3 design decision.
- **registered_workbooks:** 3
- **series:**
  - Annual: CY 2005-CY 2024 and CY 2025 (one workbook, sheets '2005_2024' and '2025')
  - Monthly: CY 2016-CY 2025 (one workbook, one sheet per year)
  - Period: January-May 2026 (workbook 'PSA-PSGC' + 'Notes')

## files

| kind | relative_path | role | sheets |
|---|---|---|---|
| annual | tax/20260430_Annual_Collection_PSCG_2005_2025 (website) cv.xlsx | data | 2005_2024, 2025 |
| monthly | tax/20260430_Monthly_Collection_PSCG_2016_2025 (website) cv.xlsx | data | 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 |
| partial-year | tax/20260616_Monthly_Collection_PSCG_JanMay2026 (D).xlsx | data | Notes, PSA-PSGC |

## layout_contract

- **example_region_row:** National Capital Region
- **header_row_anchor:** PARTICULARS
- **month_tokens:**
  - APRIL
  - AUGUST
  - DECEMBER
  - FEBRUARY
  - JANUARY
  - JULY
  - JUNE
  - MARCH
  - MAY
  - NOVEMBER
  - OCTOBER
  - SEPTEMBER
- **must_have_total_token:** TOTAL
- **notes_sheet_token:** Source: Revenue Accounting Division, BIR
- **period_row_must_contain:** For the Period:
- **title_row_must_contain:** INTERNAL REVENUE COLLECTIONS
- **units_row_must_contain:** Million Pesos

## literal_anchors

- **published_total_literals:** External headline collection totals not yet anchored. Any such literal is marked to-verify rather than fabricated (curation pass required with BIR site access).
