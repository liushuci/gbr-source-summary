# GBR Source Summary

A Python package for generating Great Barrier Reef (GBR) catchment modelling summaries, report card outputs, source–sink analysis, model performance assessment, RSDR exports, and Sankey visualisations from eWater Source / OpenWater model outputs.

This package consolidates many workflows traditionally implemented in large analysis notebooks into reusable, configurable Python scripts and modules suitable for operational Reef Report Card production.

---

# Features

## Reporting Workflows

The package supports automated generation of:

* Report card summaries
* Region summaries
* Basin summaries
* Subcatchment summaries
* Land-use summaries
* Source–sink summaries
* Source–sink Sankey diagrams
* Functional Unit (FU) load summaries
* Process contribution summaries
* Change summary plots
* Modelled vs measured assessments
* Moriasi performance statistics
* RSDR shapefile and CSV exports
* Excel workbooks
* Metadata tables

---

# Supported Constituents

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

# Main Capabilities

## Functional Unit Summaries

Generate:

* Total loads
* Areal loads
* Regional summaries
* GBR-wide summaries
* Plot-ready tables
* Scenario comparisons

---

## Process-Based Reporting

Summarise contributions from:

### Sediment and Particulate Pathways

* Hillslope
* Gully
* Streambank

### Dissolved Pathways

* Surface runoff
* Seepage
* Point source

### Internal Processes

* Floodplain deposition
* Reservoir deposition
* Stream deposition
* Extraction losses
* Channel remobilisation

---

## Source–Sink Analysis

Generate source-to-export summaries for:

* Regions
* Basins
* Management Units (MU48)
* Subcatchments

Including:

* Generated load
* Delivered load
* Export load
* Internal retention
* Delivery ratios
* Source contributions
* Process contributions

---

## Sankey Visualisations

Automatic Sankey generation for:

* GBR
* Regions
* Basins
* Multiple constituents

Including:

```text
Source → Delivery → Retention → Export
```

Features:

* Consistent report-card formatting
* Automatic unit conversion
* Automated scaling
* Batch generation

---

## Change Summary Plots

Generate:

* Percent reduction plots
* Process-change plots
* Region-level plots
* GBR-wide plots

Supporting:

```text
BASE
PREDEV
CHANGE
```

scenario comparisons.

---

## Modelled vs Measured Assessment

Generate:

* Daily comparisons
* Annual comparisons
* Moriasi statistics
* Site-level summaries
* Performance rating tables
* Diagnostic plots

Supporting:

* Flow
* Fine Sediment
* DIN
* TN
* TP

Implemented in:

```text
modelled_vs_measured.py
metrics.py
moriasi_ratings.py
```

---

## Moriasi Performance Metrics

Supported statistics:

| Metric | Description                                |
| ------ | ------------------------------------------ |
| R²     | Coefficient of Determination               |
| NSE    | Nash-Sutcliffe Efficiency                  |
| PBIAS  | Percent Bias                               |
| RSR    | RMSE-observations standard deviation ratio |

Automatic performance ratings are generated using published Moriasi criteria.

---

## RSDR Export Workflow

Generate:

* CSV outputs
* ESRI Shapefiles
* GeoPackages

Outputs include:

* Region-level RSDR
* GBR-level RSDR
* Spatial RSDR products

Implemented in:

```text
rsdr_shapefile.py
```

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
│   ├── io.py
│   ├── package_data.py
│   ├── metrics.py
│   ├── moriasi_ratings.py
│   ├── modelled_vs_measured.py
│   ├── rsdr_shapefile.py
│   ├── report_card_summary.py
│   ├── workflows_basin.py
│   ├── workflows_process.py
│   ├── workflows_source_sink.py
│   ├── workflows_change_summary_plots.py
│   └── ...
│
├── data/
│
└── README.md
```

---

# Packaged Reference Data

The package includes commonly used GBR reporting datasets.

## Monitoring Data

```text
src/gbr_source_summary/data/monitoring_data/
└── flowsLoadsGBRCLMP_GBR_allSites_MASTER.csv
```

Used for:

* Modelled vs measured workflows
* Moriasi assessments

---

## Region Lookup Tables

```text
src/gbr_source_summary/data/region_lookup/
```

Includes:

```text
BM_Subcat_Regions_LUT.csv
BU_Subcat_Regions_LUT.csv
CY_Subcat_Regions_LUT.csv
FI_Subcat_Regions_LUT.csv
MW_Subcat_Regions_LUT.csv
WT_Subcat_Regions_LUT.csv
```

and:

```text
BM_Reg_cat_node_link.csv
BU_Reg_cat_node_link.csv
CY_Reg_cat_node_link.csv
FI_Reg_cat_node_link.csv
MW_Reg_cat_node_link.csv
WT_Reg_cat_node_link.csv
```

---

## Regional Spatial Layers

Subcatchment spatial layers are packaged by region:

```text
src/gbr_source_summary/data/spatial/regions_shp/
├── BM/
├── BU/
├── CY/
├── FI/
├── MW/
└── WT/
```

This avoids GitHub file-size limitations associated with a single GBR-wide shapefile.

---

# Typical Input Structure

The package expects standard GBR Source/OpenWater outputs:

```text
RC13_RC2023_24_Gold/
└── Gold_ResultsSets_PointOfTruth/
    ├── CY/
    ├── WT/
    ├── BU/
    ├── MW/
    ├── FI/
    └── BM/
        └── Model_Outputs/
            ├── BASE_Gold_93_23/
            ├── PREDEV_Gold_93_23/
            └── CHANGE_Gold_93_23/
```

---

# Supported Reporting Scales

| Scale              | Column        |
| ------------------ | ------------- |
| 35                 | Basin_35      |
| Basin_35           | Basin_35      |
| 48                 | Manag_Unit_48 |
| MU_48              | Manag_Unit_48 |
| management_unit_48 | Manag_Unit_48 |
| WQI                | WQI_Cal       |

---

# Example Usage

## Full Report Card Bundle

Generate all report card products:

```bash
python scripts/run_report_card_summary.py ^
  --main-path F:\RC13_RC2023_24_Gold ^
  --model-results-prefix Gold_ResultsSets_PointOfTruth ^
  --output-root F:\RC13_RC2023_24_Gold\report_card_bundle ^
  --regions CY,WT,BU,MW,FI,BM ^
  --constituents FS,PN,PP,DIN,DON,DIP,DOP ^
  --units report ^
  --process-model BASE
```

### Arguments

| Argument                 | Description                                                      |
| ------------------------ | ---------------------------------------------------------------- |
| `--main-path`            | Root report card directory (e.g. RC13_RC2023_24_Gold)            |
| `--model-results-prefix` | Folder containing Source/OpenWater model outputs                 |
| `--output-root`          | Output report bundle directory                                   |
| `--regions`              | Regions to process                                               |
| `--constituents`         | Constituents to include                                          |
| `--units`                | `report` or `raw`                                                |
| `--process-model`        | Scenario used for process summaries (`BASE`, `PREDEV`, `CHANGE`) |

---

### Skip Options

Individual workflow components can be disabled to reduce runtime.

| Option                              | Skips                                      |
| ----------------------------------- | ------------------------------------------ |
| `--skip-region`                     | Region summaries                           |
| `--skip-basin`                      | Basin summaries                            |
| `--skip-subcatchment`               | Subcatchment summaries                     |
| `--skip-landuse`                    | Land-use summaries                         |
| `--skip-source-sink`                | Source–sink summaries                      |
| `--skip-sankey`                     | Sankey diagram generation                  |
| `--skip-fu-load`                    | Functional Unit load summaries             |
| `--skip-process-plots`              | Process contribution plots                 |
| `--skip-change-plots`               | Change summary plots                       |
| `--skip-modelled-vs-measured`       | Modelled-vs-measured statistics and tables |
| `--skip-modelled-vs-measured-plots` | Modelled-vs-measured PNG plots             |
| `--skip-rsdr`                       | RSDR shapefile and CSV exports             |
| `--no-excel`                        | Disable Excel workbook generation          |
| `--fail-fast`                       | Stop immediately if any workflow fails     |

---

### Example: Change Summary Plots Only

```bash
python scripts/run_report_card_summary.py ^
  --main-path F:\RC13_RC2023_24_Gold ^
  --model-results-prefix Gold_ResultsSets_PointOfTruth ^
  --output-root F:\RC13_RC2023_24_Gold\change_plots ^
  --regions CY,WT,BU,MW,FI,BM ^
  --constituents FS,PN,PP,DIN,DON,DIP,DOP ^
  --units report ^
  --process-model BASE ^
  --skip-region ^
  --skip-basin ^
  --skip-subcatchment ^
  --skip-landuse ^
  --skip-source-sink ^
  --skip-sankey ^
  --skip-fu-load ^
  --skip-process-plots ^
  --skip-modelled-vs-measured ^
  --skip-modelled-vs-measured-plots ^
  --skip-rsdr ^
  --no-excel
```

---

### Example: RSDR Export Only

```bash
python scripts/run_report_card_summary.py ^
  --main-path F:\RC13_RC2023_24_Gold ^
  --model-results-prefix Gold_ResultsSets_PointOfTruth ^
  --output-root F:\RC13_RC2023_24_Gold\rsdr_exports ^
  --regions CY,WT,BU,MW,FI,BM ^
  --constituents FS,PN,PP,DIN,DON,DIP,DOP ^
  --units report ^
  --process-model BASE ^
  --skip-region ^
  --skip-basin ^
  --skip-subcatchment ^
  --skip-landuse ^
  --skip-source-sink ^
  --skip-sankey ^
  --skip-fu-load ^
  --skip-process-plots ^
  --skip-change-plots ^
  --skip-modelled-vs-measured ^
  --skip-modelled-vs-measured-plots
```

---

### Example: Fast Summary Run

Generate only the core report card tables:

```bash
python scripts/run_report_card_summary.py ^
  --main-path F:\RC13_RC2023_24_Gold ^
  --model-results-prefix Gold_ResultsSets_PointOfTruth ^
  --output-root F:\RC13_RC2023_24_Gold\report_card_summary ^
  --regions CY,WT,BU,MW,FI,BM ^
  --constituents FS,PN,PP,DIN,DON,DIP,DOP ^
  --units report ^
  --process-model BASE ^
  --skip-sankey ^
  --skip-process-plots ^
  --skip-change-plots ^
  --skip-modelled-vs-measured ^
  --skip-modelled-vs-measured-plots ^
  --skip-rsdr
```

---

## Basin Summary

```bash
python scripts/run_basin_summary.py
```

---

## Source–Sink Summary

```bash
python scripts/run_source_sink_summary.py
```

---

## Sankey Generation

```bash
python scripts/run_source_sink_sankey_for_basin.py
```

---

# Report Card Bundle Outputs

A full report-card bundle may generate:

```text
01_report_card_summary
02_region_summary
03_basin_summary
04_subcatchment_summary
05_landuse_summary
06_source_sink_summary
07_source_sink_sankey
08_fu_load_summary
09_process_contribution_summary
10_change_summary_plots
11_modelled_vs_measured
12_rsdr_shapefiles
```

---

# Unit Conventions

## Report Card Units

| Constituent | Unit    |
| ----------- | ------- |
| FS          | kt/year |
| CS          | kt/year |
| Others      | t/year  |

---

## Internal Units

Internal calculations generally use:

```text
kg
kg/year
kg/ha/year
```

Unit conversion is handled automatically.

---

# Key Input Files

Typical required files include:

```text
RegContributorDataGrid.csv
RawResults.csv
RegionalSourceSinkSummaryTable.csv
fuAreasTable.csv
ParameterTable.csv
```

---

# Output Types

Generated outputs include:

* CSV tables
* Excel workbooks
* PNG plots
* Sankey diagrams
* Shapefiles
* GeoPackages
* QA summaries
* Metadata tables

---

# Development Notes

The package is designed for:

* RC13 / RC2023–25 workflows
* Source and OpenWater interoperability
* Large-scale batch processing
* Reproducible reporting
* Automated QA workflows
* Operational Reef Report Card production

---

# Future Improvements

Potential future enhancements:

* Parallel processing
* Interactive dashboards
* Direct NetCDF readers
* Additional QA automation
* Improved plotting themes
* Cloud-ready workflows

---


---

# License

MIT License

---

# Contact

Maintainer: Shuci Liu

Repository:

https://github.com/liushuci/gbr-source-summary

---

# Citation

If using this package in reports, publications, or operational reporting workflows, please cite the repository and associated GBR modelling workflows.
