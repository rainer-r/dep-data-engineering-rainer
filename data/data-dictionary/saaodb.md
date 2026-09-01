# Data Dictionary — DBM Statement of Appropriations, Allotments, Obligations, Disbursements and Balances (SAAODB)

- **source:** saaodb
- **source_url:** https://www.dbm.gov.ph/index.php/statement-of-appropriations-allotments-obligations-disbursements-and-balances
- **format:** mixed
- **format_note:** .htm (2011Q1-2014Q2, HTML tables) then .pdf (2014Q3-2026Q1, tabular PDFs). Extractor planned .xlsx but DBM serves these; this is the canonical format record.
- **grain:** department/agency x quarterly period for allotments, obligations (and balances) in thousand pesos

## coverage

- **expected_htm_count:** 14
- **expected_pdf_count:** 47
- **expected_quarters:** 61
- **expected_total_files:** 61
- **grid:**
  - **end_quarter:** 1
  - **end_year:** 2026
  - **start_quarter:** 1
  - **start_year:** 2011

## coverage_anchor

The SAAODB series is published quarterly. From 2011Q1 through 2026Q1 inclusive the grid has (2026-2011)*4+1 = 61 successive quarters, matching the 61 committed files (14 .htm, 47 .pdf). The DBM page lists many more links (96 PDF + 18 htm candidates) that are superseded revisions of the canonical quarters; the quarterly grid is the stable, independently enumerable completeness gate.

## filename_pattern

^\\s*(20\\d{2})\\s*[-_]?[Qq]([1-4])

## htm_structure

- **expense_groups:**
  - CO
  - MOOE
  - PS
- **group_header_row:**
  - CO
  - MOOE
  - PS
  - Total
- **header_tokens:**
  - ALLOTMENT
  - OBLIGATIONS
  - STATEMENT OF ALLOTMENT
  - UNOBLIGATED
- **single_table:** true

## pdf_structure

- **expense_groups_2014_2025:**
  - CO
  - FINEX
  - MOOE
  - PS
- **header_tokens_all:**
  - OBLIGATION
- **header_tokens_any:**
  - ALLOTMENT
  - APPROPRIATIONS
- **min_pages:** 2
- **note_2026_format:** The FY2026 Q1 first page names the full fiscal lifecycle (APPROPRIATIONS...DISBURSEMENTS), i.e. the report gained columns over the PDF era. Deep per-column checks are deferred to M3's parser decision (pdfplumber candidate); this layer checks page count, openability, and presence of the header vocabulary.
