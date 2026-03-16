"""
Configuration module for gbr_source_summary.

This module defines the GBRConfig dataclass, which stores:
- base project path
- region/model/constituent settings
- unit conversion constants
- standard file/path builders used across the package

The main_path should normally be provided by the user when running the package,
so the code can be reused for different model builds and machines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GBRConfig:
    """
    Central configuration object for GBR Source summary workflows.

    Attributes
    ----------
    main_path : Path
        Root folder for a model build, e.g. F:\\RC13_RC2023_24_Gold
    rc : str
        Run/build suffix used in model output folders.
    regions : list[str]
        List of NRM region codes.
    models : list[str]
        Model scenarios, e.g. PREDEV / BASE / CHANGE.
    constituents : list[str]
        Standard constituent names used within the package.
    """

    # Root directory for the model build.
    main_path: Path

    # Run identifier used in Source output folder names.
    rc: str = "Gold_93_23"

    # Standard region sets.
    regions: list[str] = field(default_factory=lambda: ["CY", "WT", "BU", "MW", "FI", "BM"])
    regions_all_gbr: list[str] = field(default_factory=lambda: ["CY", "WT", "BU", "MW", "FI", "BM", "GBR"])

    # Standard model scenarios.
    models: list[str] = field(default_factory=lambda: ["PREDEV", "BASE", "CHANGE"])

    # Standard constituent names used inside the package.
    constituents: list[str] = field(default_factory=lambda: ["FS", "PN", "PP", "DIN", "DON", "DIP", "DOP", "Flow"])
    core_constituents: list[str] = field(default_factory=lambda: ["FS", "PN", "PP", "DIN"])

    # Functional units used in reporting.
    fus_of_interest: list[str] = field(default_factory=lambda: [
        "Bananas",
        "Conservation",
        "Cropping",
        "Dairy",
        "Forestry",
        "Grazing",
        "Horticulture",
        "Stream",
        "Sugarcane",
        "Urban + Other",
    ])

    fu_areas_of_interest: list[str] = field(default_factory=lambda: [
        "Bananas",
        "Conservation",
        "Cropping",
        "Dairy",
        "Forestry",
        "Grazing",
        "Horticulture",
        "Sugarcane",
        "Urban + Other",
    ])

    fu_colors: list[str] = field(default_factory=lambda: [
        "yellow",
        "darkgreen",
        "plum",
        "purple",
        "lime",
        "gray",
        "orangered",
        "navy",
        "greenyellow",
        "red",
    ])

    # Standard file suffixes.
    region_lut_end_filename: str = "_Subcat_Regions_LUT.csv"
    region_lut_node_subcat_filename: str = "_Reg_cat_node_link.csv"
    gbrclmp_filename: str = "flowsLoadsGBRCLMP_GBR_allSites_MASTER.csv"

    # Unit conversions used repeatedly in GBR workflows.
    kg_to_t: float = 1e-3
    kg_to_kt: float = 1e-6
    t_to_kt: float = 1e-3
    cumecs_to_mld: float = 86400 * 1e-3
    m3_to_ml: float = 1e-3
    ml_to_gl: float = 1e-3
    m2_to_ha: float = 1e-4
    m_to_km: float = 1e-3
    kt_to_t: float = 1000
    t_to_kg: float = 1000

    # Number of model years used for average annual calculations.
    model_years: int = 30

    @property
    def per_year(self) -> float:
        """Return the multiplier used to convert totals to average annual values."""
        return 1 / self.model_years

    @property
    def model_results_prefix(self) -> Path:
        """Return the root folder containing Source result sets."""
        return self.main_path / "Gold_ResultsSets_PointOfTruth"

    @property
    def monitoring_data_path(self) -> Path:
        """Return the folder containing monitoring datasets."""
        return self.main_path / "Monitoring_data"

    @property
    def gbrclmp_file(self) -> Path:
        """Return the full path to the GBRCLMP monitoring file."""
        return self.monitoring_data_path / self.gbrclmp_filename

    @property
    def regions_path(self) -> Path:
        """Return the folder containing region lookup tables."""
        return self.main_path / "Regions"

    def get_region_lut_path(self, region: str) -> Path:
        """Return the standard region lookup CSV path for a region."""
        return self.regions_path / f"{region}{self.region_lut_end_filename}"

    def get_region_cat_node_link_path(self, region: str) -> Path:
        """Return the region node-subcatchment link CSV path for a region."""
        return self.regions_path / f"{region}{self.region_lut_node_subcat_filename}"

    def get_model_output_dir(self, region: str, model: str) -> Path:
        """Return the model output folder for a given region and scenario."""
        return self.model_results_prefix / region / "Model_Outputs" / f"{model}_{self.rc}"

    def get_timeseries_dir(self, region: str, model: str = "BASE") -> Path:
        """Return the TimeSeries folder for a given region/model."""
        return self.get_model_output_dir(region, model) / "TimeSeries"