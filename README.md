# TaxTracePH: Connecting the Dots Between Citizen Tax Compliance and Regional Infrastructure Development

## The Core Problem

Every single day, ordinary Filipinos comply with their fiscal duties. Taxes are automatically deducted from monthly paychecks and tacked onto everyday purchases like food, gas, and electricity through VAT. Citizens contribute their hard-earned money to the national treasury under the fundamental promise that it will return to their communities in the form of better public roads, functioning hospitals, and reliable public services.

Yet, a massive disconnect persists. While the Bureau of Internal Revenue aggressively enforces collection milestones, average citizens look at their home provinces and still navigate broken infrastructure, persistent flooding, and neglected public utilities. This issue stems directly from institutional malpractice and systemic data fragmentation. Currently, the government records documenting what citizens pay and the data detailing how national agencies distribute funds are intentionally or unintentionally kept in completely isolated, unindexed files.

Because these data sources do not talk to each other, the average Filipino has no way of seeing a definitive receipt. It is impossible to verify if the heavy taxes collected from a specific region are actually returning to improve that local economy, or if the funds are leaking into bureaucratic black holes along the way. This project engineers an automated data pipeline that bridges these disparate datasets, creating a unified platform that tracks the life cycle of tax money to show exactly how much a region contributes versus how much it actually receives.

> The Extensible Challenge

The technical challenge of tracking tax money getting lost in translation extends far beyond the Philippines, serving as a shared roadblock across developing Southeast Asian nations like Indonesia and Malaysia. However, comparing how effectively these neighboring countries utilize citizen contributions is currently blocked by severe data infrastructure limitations.

Building a transnational framework requires solving complex data engineering bottlenecks. The pipeline must harmonize entirely different taxpayer taxonomies, dynamically adjust for multi-currency inflation histories, and clean up conflicting regional granularities, such as aligning Philippine provinces with Malaysian states. Overcoming these technical hurdles is the only way to establish a standardized, data-driven metric for regional fiscal health and governance efficiency across the region.

---

## Target Audience
The primary audience for this platform consists of civil society organizations, independent economic watchdogs, and civic-minded journalists who need hard, data-driven evidence to monitor government spending and advocate for regional equity. Secondary users include local government officials looking to defend their region’s fair share of the national budget, and honest academic researchers analyzing public finance. Ultimately, the system is designed to serve the general Filipino public, transforming complex public finance spreadsheets into accessible, visual insights that allow ordinary citizens to see exactly how their tax contributions match local development.

## Data Source

To construct a reliable fiscal map, the data pipeline consolidates public datasets from the following direct regional repositories:

- PH's Tax Revenue Records: 
    - https://www.bir.gov.ph/collection-statistics
- PH's National Allocations & Spending:
    - https://www.bir.gov.ph/collection-statistics
- For comparative transnational fiscal data:
    - https://data.go.id/
    - https://data.gov.my/

> Fallback Data Sources:
- https://www.dbm.gov.ph/index.php/budget
- https://data.bettergov.ph/datasets/20


