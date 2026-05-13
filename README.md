# GBR Source Summary

A Python package for generating Great Barrier Reef (GBR) catchment modelling summaries, report card outputs, source–sink analysis, and Sankey visualisations from eWater Source / OpenWater model outputs.

This package consolidates many of the workflows traditionally implemented in large analysis notebooks into reusable, configurable Python scripts and modules.

---

## Features

### Reporting Workflows

* Functional Unit (FU) load summaries
* Process-based summaries
* Basin and regional summaries
* Source–sink analysis
* Sankey diagram generation
* Report card bundle generation
* Land use and rainfall summaries
* Anthropogenic load calculations
* Scenario comparisons:

  * PREDEV
  * BASE
  * CHANGE

---

## Supported Constituents

| Constituent | Description                    |
| ----------- | ------------------------------ |
| FS          | Fine Sediment                  |
| CS          | Coarse Sediment                |
| DIN         | Dissolved Inorganic Nitrogen   |
| DON         | Dissolved Organic Nitrogen     |
| PN          | Particulate Nitrogen           |
| DIP         | Dissolved Inorganic Phosphorus |
| DOP         | Dissolved Organic Phosphorus   |
| PP          | Particulate Phosphorus         |

---

## Main Capabilities

### Functional Unit Summaries

Generate:

* Total loads
* Areal loads
* Regional summaries
* GBR-wide summaries
* Plot-ready tables

---

### Process-Based Reporting

Summarise contributions from:

* Hillslope
* Gully
* Streambank
* Point source
* Surface runoff
* Seepage
* Floodplain deposition
* Reservoir deposition
* Channel remobilisation
* Stream deposition
* Extraction losses

---

### Source–Sink Analysis

Generate source-to-export summaries for:

* Regions
* Basins
* Management Units (MU48)
* Subcatchments

Including:

* Export pathways
* Internal losses
* Retention
* Delivery ratios

---

### Sankey Visualisations

Automatic Sankey generation for:

* All regions
* All basins
* Multiple constituents

Including:

* Source → transport → export pathways
* Automated unit handling
* Consistent report-card formatting

---

### Report Card Bundle

Single-command workflow that generates:

* Regional summaries
* Basin summaries
* FU summaries
* Process summaries
* Source–sink summaries
* Sankey diagrams
* Excel workbooks
* CSV exports
* Metadata tables

---

# Installation

## Clone Repository

```bash
git clone https://github.com/liushuci/gbr-source-summary.git
cd gbr-source-summary
```

---

## Create Environment

```bash
conda create -n gbr python=3.12
conda activate gbr
```

---

## Install Package

```bash
pip install -e .
```

---

## Optional Dependencies

Recommended companion packages:

* openwater
* dsed-py
* veneer-py
* hydrograph-py

---

# Repository Structure

```text
gbr_source_summary/
│
├── scripts/
│   ├── run_report_card_summary.py
│   ├── run_basin_summary.py
│   ├── run_fu_load_summary.py
│   ├── run_process_report.py
│   ├── run_source_sink_summary.py
│   ├── run_source_sink_sankey_for_basin.py
│   └── ...
│
├── src/gbr_source_summary/
│   ├── config.py
│   ├── units.py
│   ├── export.py
│   ├── export_excel.py
│   ├── report_card_summary.py
│   ├── report_fu.py
│   ├── report_process.py
│   ├── workflows_basin.py
│   ├── workflows_fu.py
│   ├── workflows_process.py
│   ├── workflows_source_sink.py
│   └── ...
│
└── README.md
```

---

# Typical Input Structure

The package expects standard GBR Source/OpenWater outputs, typically organised as:

```text
Gold_ResultsSets_PointOfTruth/
    CY/
        Model_Outputs/
            BASE_Gold_93_23/
            PREDEV_Gold_93_23/
            CHANGE_Gold_93_23/
```

---

# Example Usage

## Run Full Report Card Bundle

```bash
python scripts/run_report_card_summary.py ^
    --main-path F:\RC13_RC2023_24_Gold ^
    --output-root F:\RC13_RC2023_24_Gold\report_card_bundle ^
    --regions CY,WT,BU,MW,FI,BM ^
    --units report
```

---

## Run Basin Summary

```bash
python scripts/run_basin_summary.py
```

---

## Run Source–Sink Summary

```bash
python scripts/run_source_sink_summary.py
```

---

## Generate Sankey Diagrams

```bash
python scripts/run_source_sink_sankey_for_basin.py
```

---

# Unit Conventions

## Report Card Units

| Constituent | Unit    |
| ----------- | ------- |
| FS          | kt/year |
| Others      | t/year  |

---

## Raw Units

Internal calculations are generally stored as:

```text
kg
kg/year
kg/ha/year
```

Unit conversions are handled automatically via:

```python
apply_units()
label_for_units()
```

---

# Basin Scales

Supported aggregation scales:

| Alias              | Actual Column |
| ------------------ | ------------- |
| 35                 | Basin_35      |
| Basin_35           | Basin_35      |
| 48                 | Manag_Unit_48 |
| MU_48              | Manag_Unit_48 |
| management_unit_48 | Manag_Unit_48 |

---

# Key Data Sources

Typical required files include:

* `RegContributorDataGrid.csv`
* `fuAreasTable.csv`
* `ParameterTable.csv`
* Climate tables
* Regional lookup tables
* GBR Phase 4 shapefiles

---

# Output Types

Generated outputs include:

* CSV tables
* Excel workbooks
* PNG plots
* Sankey diagrams
* QA summaries
* Metadata tables

---

# Example Outputs

## Functional Unit Summary

* Regional load contributions
* Areal loading rates
* GBR-wide comparisons

---

## Source–Sink Summary

* Generated load
* Delivered load
* Export load
* Internal retention
* Process contribution breakdowns

---

## Sankey Plots

Visualisation of:

```text
Source → Delivery → Retention → Export
```

---

# Development Notes

The package is designed for:

* RC13 / RC2023–25 workflows
* OpenWater + Source interoperability
* Large-scale batch processing
* Reproducible reporting
* QA-ready exports

---

# Future Improvements

Planned enhancements include:

* Parallel processing
* Interactive dashboards
* GeoPackage export support
* Additional QA automation
* Improved plotting themes
* NetCDF direct readers

---

# Acknowledgements

This workflow builds upon modelling and analysis approaches developed across:

* Queensland Government
* eWater
* Flow Matters
* Great Barrier Reef report card workflows
* Paddock-to-Reef program workflows

---

# Related Projects

* [https://github.com/flowmatters/openwater](https://github.com/flowmatters/openwater)
* [https://github.com/flowmatters/dsed-py](https://github.com/flowmatters/dsed-py)
* [https://github.com/flowmatters/veneer-py](https://github.com/flowmatters/veneer-py)
* [https://github.com/flowmatters/hydrograph-py](https://github.com/flowmatters/hydrograph-py)

---

# License

MIT License

---

# Contact

Maintainer: Shuci Liu

GitHub Repository:

[https://github.com/liushuci/gbr-source-summary](https://github.com/liushuci/gbr-source-summary)

---

# Citation

If using this package in reports or publications, please cite the repository and associated GBR modelling workflows.
