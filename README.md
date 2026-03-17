# GBR Source Summary

Python tools for summarising **eWater Source** and **OpenWater** model outputs for  
**Great Barrier Reef (GBR) catchment water quality modelling**.

This package provides workflows to aggregate, compare, and report model outputs
used in **Paddock-to-Reef (P2R)** modelling and **Reef Report Card** reporting.

---

## Overview

`gbr_source_summary` automates the extraction and summarisation of loads from
GBR catchment models across multiple reporting scales, including:

- Functional Unit (FU)
- Basin / reporting region
- Constituent
- Model scenario

Typical outputs include:

- **Total loads**
- **Anthropogenic loads**
- **Load reductions**
- **Percent reductions**

These summaries support reporting workflows used in the  
**Reef Report Card and related GBR modelling programs**.

---

## Units

All load summaries produced by this package are expressed as:

kilograms (kg) over the full model simulation period

Typical **RC13 builds** cover approximately:


1993–2023 (~30 years)


### Conversion to reporting units

Sediment:


kt/yr = kg / 1e6 / model_years


Nutrients (DIN, PN, etc.):


t/yr = kg / 1000 / model_years


---

## Features

- Functional Unit (FU) summaries
- Basin / region aggregation
- Scenario comparisons
  - PREDEV
  - BASE
  - CHANGE
- Anthropogenic load calculation
- Load reduction reporting
- Percent reduction calculation

---

## Basin summary workflow

Generate basin-scale summaries and scenario comparisons:

python scripts/run_basin_summary.py \
--base-path F:/RC13_RC2023_24_Gold \
--basin-scale 48 \
--reporting-units report_card \
--value-column "LoadToStream (kg)"

Run QA checks:

python scripts/check_basin_outputs.py \
--folder check_outputs/basin_summary/Manag_Unit_48/report_card \
--run-label Gold_93_23 \
--reporting-units report_card


## Repository Structure


gbr-source-summary
│
├── src/gbr_source_summary
│ ├── init.py
│ ├── config.py
│ ├── workflows_fu.py
│ ├── workflows_compare.py
│ ├── workflows_process.py
│ ├── report_card_summary.py
│ └── utils.py
│
├── scripts
│ └── run_summary.py
│
├── tests
│
├── README.md
├── requirements.txt
└── pyproject.toml

