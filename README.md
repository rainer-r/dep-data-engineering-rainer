# TaxTracePH

## The Core Problem

We pay taxes every single day. It gets taken out of our paychecks, and it's added to everything we buy, from food and gas to electricity. We contribute our hard-earned money to the national treasury with the simple promise that it will return to our communities in the form of decent roads, working hospitals, and reliable public services.

But if you look around, that promise feels broken. We see tax collection offices boasting about hitting their targets, yet we still navigate potholes, deal with flooded streets, and struggle with neglected public facilities. 

The real problem is that the public has no way to trace the money. The documents showing what citizens pay and the files showing how the government spends are kept completely separate, whether by design or just out of sheer disorganization. Because these pieces of information never meet, we can't see the receipts. We have no way of knowing if the taxes collected from our hometowns are actually spent to improve them, or if the funds are simply lost in bureaucratic black holes.

This project is an effort to change that. I am bringing these scattered pieces of data together into one clear picture, so we can finally track the life cycle of tax money and compare what a region contributes to what it actually gets back. Specifically, this project aims to answer: **Can a consolidated, open data pipeline reveal whether local taxes collected from Philippine regions are being proportionally spent to develop their local communities?**

> The Extensible Challenge

This frustration isn't unique to the Philippines. People in neighboring countries like Indonesia and Malaysia face the exact same lack of transparency. 

But trying to compare how well different governments use their citizens' money is a massive headache. Every country tracks its finances differently, uses its own currency, and labels its regions and taxpayer categories in ways that don't match. To make a fair comparison, I have to do the messy, behind-the-scenes work of translating, aligning, and cleaning up these incompatible records so everyone can look at them side-by-side.

Initially, this project started by looking for any publicly available government datasets I could actually get my hands on.

---

## Target Audience

This project is built for citizens who want to better understand how local tax contributions connect to public projects in their own neighborhoods. 

It is also designed for local government officials, community organizers, and researchers who want to use clear, data-backed insights to support regional planning and budgeting. Finally, it serves as an open resource for journalists and policy watchdogs looking for objective data to help tell the story of public spending and development.

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


