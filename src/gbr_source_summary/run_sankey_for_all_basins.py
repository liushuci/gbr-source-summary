from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.sankey import Sankey
import pandas as pd

from gbr_source_summary.naming import standardise_constituent_names


# =========================================================
# DEFAULTS
# =========================================================

DEFAULT_MODEL = "BASE"
DEFAULT_REGIONS = ["CY", "WT", "BU", "MW", "FI", "BM"]
DEFAULT_BASIN_SCALE = "MU48"  # "MU48" or "BASIN35"

SUPPORTED_CONSTITUENTS = ["FS", "CS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]
VALUE_COLUMN = "Total_Load_in_Kg"


# =========================================================
# CLI
# =========================================================

def _maybe_list(value: str | None) -> list[str] | None:
    if value is None:
        return None

    items = [
        x.strip().upper()
        for x in value.split(",")
        if x.strip()
    ]

    return items or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate source-sink Sankey diagrams for all basins."
    )

    parser.add_argument(
        "--base-path",
        type=str,
        default=None,
        help=(
            "Main RC model/data folder. "
            "If omitted, uses GBR_BASE_PATH environment variable."
        ),
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        choices=["PREDEV", "BASE", "CHANGE"],
        help="Scenario/model to plot.",
    )

    parser.add_argument(
        "--regions",
        type=str,
        default=",".join(DEFAULT_REGIONS),
        help="Comma-separated regions, e.g. CY,WT,BU,MW,FI,BM.",
    )

    parser.add_argument(
        "--basin-scale",
        type=str,
        default=DEFAULT_BASIN_SCALE,
        choices=["MU48", "BASIN35"],
        help="Basin scale to plot.",
    )

    parser.add_argument(
        "--constituents",
        type=str,
        default=None,
        help=(
            "Comma-separated constituents. "
            "If omitted, all supported constituents are used. "
            "Example: FS,PN,PP,DIN"
        ),
    )

    parser.add_argument(
        "--source-sink-dir",
        type=str,
        default=None,
        help=(
            "Optional source-sink summary folder. "
            "If omitted, uses <base-path>/report_card_summary/source_sink."
        ),
    )

    parser.add_argument(
        "--output-root",
        type=str,
        default=None,
        help=(
            "Optional Sankey output root. "
            "If omitted, uses GBR_SANKEY_OUTPUT_ROOT or "
            "<source-sink-dir>/sankey_diagrams."
        ),
    )

    return parser


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    base_path_text = args.base_path or os.environ.get("GBR_BASE_PATH")

    if not base_path_text:
        raise ValueError(
            "Base path was not provided. Use either:\n"
            "  --base-path F:/RC13_RC2023_24_Gold\n"
            "or set environment variable:\n"
            "  $env:GBR_BASE_PATH='F:/RC13_RC2023_24_Gold'"
        )

    base_path = Path(base_path_text).resolve()

    source_sink_dir = (
        Path(args.source_sink_dir).resolve()
        if args.source_sink_dir
        else base_path / "report_card_summary" / "source_sink"
    )

    output_root = Path(
        args.output_root
        or os.environ.get(
            "GBR_SANKEY_OUTPUT_ROOT",
            str(source_sink_dir / "sankey_diagrams"),
        )
    ).resolve()

    return base_path, source_sink_dir, output_root


# =========================================================
# HELPERS
# =========================================================

def constituent_unit_label(constituent: str) -> str:
    return "kt/yr" if constituent in {"FS", "CS"} else "t/yr"


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text)).strip("_")


def source_sink_csv_path(
    source_sink_dir: Path,
    basin_scale: str,
) -> Path:
    candidates = [
        source_sink_dir / "source_sink_basin_summary.xlsx",
        source_sink_dir / "source_sink_basin_summary.csv",
        source_sink_dir / "source_sink_summary.xlsx",
        source_sink_dir / "source_sink_summary.csv",
    ]

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Source-sink summary not found. Tried:\n"
        + "\n".join(str(p) for p in candidates)
    )

def output_dir_for_region(
    region: str,
    basin_scale: str,
    constituent: str,
    output_root: Path,
) -> Path:
    out = output_root / region / basin_scale / constituent
    out.mkdir(parents=True, exist_ok=True)
    return out


def normalise_group_name(text: str) -> str:
    text = str(text).strip().lower()

    replacements = {
        "flood plain deposition": "floodplaindeposition",
        "floodplain deposition": "floodplaindeposition",
        "reservoir deposition": "reservoirdeposition",
        "reservoirdeposition": "reservoirdeposition",
        "stream deposition": "streamdeposition",
        "streamdeposition": "streamdeposition",
        "channel remobilisation": "channelremobilisation",
        "channelremobilisation": "channelremobilisation",
        "extraction + other minor losses": "extractionotherminorlosses",
        "extraction and other minor losses": "extractionotherminorlosses",
        "extraction_other_loss": "extractionotherminorlosses",
        "surface runoff": "surfacerunoff",
        "surfacerunoff": "surfacerunoff",
        "point source": "pointsource",
        "pointsource": "pointsource",
        "streambank": "streambank",
        "hillslope": "hillslope",
        "gully": "gully",
        "seepage": "seepage",
        "hillslopeexport": "hillslopeexport",
        "streambankexport": "streambankexport",
        "gullyexport": "gullyexport",
        "channelremobilisationexport": "channelremobilisationexport",
        "surfacerunoffexport": "surfacerunoffexport",
        "seepageexport": "seepageexport",
        "pointsourceexport": "pointsourceexport",
    }

    return replacements.get(
        text,
        text.replace(" ", "").replace("_", "").replace("+", ""),
    )


def figure_size_for_summary(summary: pd.DataFrame) -> tuple[float, float]:
    n = len(summary)

    max_flow = (
        float(summary["DisplayValue"].abs().max())
        if not summary.empty
        else 0.0
    )
    total_flow = (
        float(summary["DisplayValue"].abs().sum())
        if not summary.empty
        else 0.0
    )

    width = 16.0
    height = 10.0

    if n >= 7:
        width = 18.0
        height = 11.5

    if n >= 9:
        width = 20.0
        height = 12.5

    if max_flow > 300:
        width += 1.5
        height += 0.5

    if total_flow > 1500:
        width += 1.5
        height += 0.5

    return width, height


def font_sizes_for_summary(summary: pd.DataFrame) -> tuple[int, int, int]:
    n = len(summary)

    title_fs = 22
    label_fs = 12
    total_fs = 18

    if n >= 7:
        title_fs = 20
        label_fs = 11
        total_fs = 16

    if n >= 9:
        title_fs = 18
        label_fs = 10
        total_fs = 15

    return title_fs, label_fs, total_fs


# =========================================================
# LOAD SUMMARY
# =========================================================

def load_source_sink_all(
    source_sink_dir: Path,
    basin_scale: str,
) -> pd.DataFrame:
    """
    Load full exported source-sink summary CSV.

    IMPORTANT:
    These values are already in reporting / plotting units,
    so do not convert them again.
    """
    csv_path = source_sink_csv_path(
        source_sink_dir=source_sink_dir,
        basin_scale=basin_scale,
    )

    if not csv_path.exists():
        raise FileNotFoundError(f"Source-sink summary not found: {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    required = [
        "Region",
        "Scenario",
        "Basin",
        "Constituent",
        "BudgetGroup",
        VALUE_COLUMN,
    ]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise KeyError(
            f"Missing required columns in source-sink summary: {missing}"
        )

    df["Constituent"] = standardise_constituent_names(df["Constituent"])
    df[VALUE_COLUMN] = pd.to_numeric(
        df[VALUE_COLUMN],
        errors="coerce",
    ).fillna(0.0)

    df["_BudgetGroup_norm"] = df["BudgetGroup"].map(normalise_group_name)

    return df


def get_basin_list(
    source_sink_all: pd.DataFrame,
    region: str,
    model: str,
) -> list[str]:
    work = source_sink_all.copy()
    work = work.loc[work["Scenario"] == model].copy()
    work = work.loc[work["Region"] == region].copy()

    basins = (
        work["Basin"]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .sort_values()
        .unique()
        .tolist()
    )

    return basins


def load_source_sink_for_basin(
    source_sink_all: pd.DataFrame,
    region: str,
    basin_name: str,
    constituent: str,
    model: str,
) -> pd.DataFrame:
    work = source_sink_all.copy()
    work = work.loc[work["Scenario"] == model].copy()
    work = work.loc[work["Region"] == region].copy()
    work = work.loc[work["Basin"] == basin_name].copy()
    work = work.loc[work["Constituent"] == constituent].copy()

    if work.empty:
        raise ValueError(
            "No source-sink summary found for "
            f"region={region}, basin={basin_name}, "
            f"constituent={constituent}, model={model}"
        )

    work["DisplayValue"] = pd.to_numeric(
        work[VALUE_COLUMN],
        errors="coerce",
    ).fillna(0.0)

    return work


# =========================================================
# VALUE HELPERS
# =========================================================

def get_ss_value(df: pd.DataFrame, key: str) -> float:
    target = normalise_group_name(key)
    hit = df.loc[df["_BudgetGroup_norm"] == target, "DisplayValue"]

    return float(hit.sum()) if not hit.empty else 0.0


# =========================================================
# BUILD SANKEY SUMMARY
# =========================================================

def build_summary_tables(
    source_sink: pd.DataFrame,
    constituent: str,
) -> tuple[pd.DataFrame, float, float, float]:
    """
    Build Sankey input using summary CSV only.

    Convention:
    - supplies are positive
    - losses are negative
    - exports are negative
    """
    summary_parts: list[tuple[str, float]] = []

    if constituent in {"FS", "CS", "PN", "PP"}:
        supplies = {
            "Streambank_supply": get_ss_value(source_sink, "Streambank"),
            "Hillslope_supply": get_ss_value(source_sink, "Hillslope"),
            "Gully_supply": get_ss_value(source_sink, "Gully"),
            "ChannelRemobilisation_supply": get_ss_value(
                source_sink,
                "ChannelRemobilisation",
            ),
        }

        exports = {
            "Streambank_export": get_ss_value(
                source_sink,
                "StreambankExport",
            ),
            "Hillslope_export": get_ss_value(
                source_sink,
                "HillslopeExport",
            ),
            "Gully_export": get_ss_value(
                source_sink,
                "GullyExport",
            ),
            "ChannelRemobilisation_export": get_ss_value(
                source_sink,
                "ChannelRemobilisationExport",
            ),
        }

    else:
        supplies = {
            "SurfaceRunoff_supply": get_ss_value(
                source_sink,
                "SurfaceRunoff",
            ),
            "Seepage_supply": get_ss_value(
                source_sink,
                "Seepage",
            ),
            "PointSource_supply": get_ss_value(
                source_sink,
                "PointSource",
            ),
        }

        exports = {
            "SurfaceRunoff_export": get_ss_value(
                source_sink,
                "SurfaceRunoffExport",
            ),
            "Seepage_export": get_ss_value(
                source_sink,
                "SeepageExport",
            ),
            "PointSource_export": get_ss_value(
                source_sink,
                "PointSourceExport",
            ),
        }

    losses = {
        "Extraction_Other_loss": get_ss_value(
            source_sink,
            "Extraction + Other Minor Losses",
        ),
        "FloodPlainDeposition_loss": get_ss_value(
            source_sink,
            "FloodPlainDeposition",
        ),
        "ReservoirDeposition_loss": get_ss_value(
            source_sink,
            "ReservoirDeposition",
        ),
        "StreamDeposition_loss": get_ss_value(
            source_sink,
            "StreamDeposition",
        ),
    }

    total_supply = 0.0
    for name, val in supplies.items():
        if abs(val) > 0:
            summary_parts.append((name, abs(val)))
            total_supply += abs(val)

    total_export = 0.0
    for name, val in exports.items():
        if abs(val) > 0:
            summary_parts.append((name, -abs(val)))
            total_export += abs(val)

    total_loss = 0.0
    for name, val in losses.items():
        if abs(val) > 0:
            summary_parts.append((name, -abs(val)))
            total_loss += abs(val)

    summary = pd.DataFrame(
        summary_parts,
        columns=["Name", "DisplayValue"],
    ).set_index("Name")

    summary = summary[summary["DisplayValue"] != 0]

    return summary, total_supply, total_loss, total_export


# =========================================================
# PLOT
# =========================================================

def build_labels_and_orientations(
    names: list[str],
) -> tuple[list[str], list[int]]:
    label_map = {
        "Streambank_supply": "Streambank\nSupply",
        "Hillslope_supply": "Hillslope\nSupply",
        "Gully_supply": "Gully\nSupply",
        "ChannelRemobilisation_supply": "Channel\nRemobilisation\nSupply",
        "SurfaceRunoff_supply": "Surface runoff\nSupply",
        "Seepage_supply": "Seepage\nSupply",
        "PointSource_supply": "Point source\nSupply",
        "Extraction_Other_loss": "Extraction and\nother minor\nlosses",
        "FloodPlainDeposition_loss": "Floodplain\ndeposition",
        "ReservoirDeposition_loss": "Reservoir\ndeposition",
        "StreamDeposition_loss": "Stream\ndeposition",
        "ChannelRemobilisation_export": "Channel\nRemobilisation\nExport",
        "Gully_export": "Gully\nExport",
        "Hillslope_export": "Hillslope\nExport",
        "Streambank_export": "Streambank\nExport",
        "SurfaceRunoff_export": "Surface runoff\nExport",
        "Seepage_export": "Seepage\nExport",
        "PointSource_export": "Point source\nExport",
    }

    orient_map = {
        "Streambank_supply": 0,
        "Hillslope_supply": -1,
        "Gully_supply": 1,
        "ChannelRemobilisation_supply": 1,
        "SurfaceRunoff_supply": -1,
        "Seepage_supply": 1,
        "PointSource_supply": 0,
        "Extraction_Other_loss": -1,
        "FloodPlainDeposition_loss": -1,
        "ReservoirDeposition_loss": -1,
        "StreamDeposition_loss": -1,
        "ChannelRemobilisation_export": 1,
        "Gully_export": 1,
        "Hillslope_export": 1,
        "Streambank_export": 0,
        "SurfaceRunoff_export": 1,
        "Seepage_export": 1,
        "PointSource_export": 0,
    }

    labels = [
        label_map.get(name, name.replace("_", "\n"))
        for name in names
    ]

    orientations = [
        orient_map.get(name, 0)
        for name in names
    ]

    return labels, orientations


def scale_for_constituent(
    region: str,
    constituent: str,
) -> float:
    if constituent in {"FS", "CS"}:
        region_scale = {
            "CY": 0.001,
            "WT": 0.001,
            "BU": 0.00007,
            "MW": 0.003,
            "FI": 0.0001,
            "BM": 0.001,
        }

        return region_scale.get(region, 0.001)

    return 0.001


def text_positions(
    region: str,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    supply_pos = (-1.35, 0.05)
    export_pos = (1.20, 0.35)
    loss_pos = (0.55, -1.15)

    if region == "WT":
        supply_pos = (-1.50, 0.00)
        export_pos = (1.30, 0.40)
        loss_pos = (0.45, -1.20)

    elif region == "BU":
        supply_pos = (-1.50, 0.00)
        export_pos = (1.20, 0.30)
        loss_pos = (0.70, -1.10)

    elif region == "MW":
        supply_pos = (-1.20, 0.20)
        export_pos = (1.20, 0.30)
        loss_pos = (0.70, -1.10)

    elif region == "FI":
        supply_pos = (-1.25, 0.00)
        export_pos = (1.10, 0.45)
        loss_pos = (0.70, -1.20)

    elif region == "BM":
        supply_pos = (-1.55, 0.25)
        export_pos = (1.45, 0.40)
        loss_pos = (0.85, -1.45)

    return supply_pos, export_pos, loss_pos


def make_plot(
    summary: pd.DataFrame,
    total_supply: float,
    total_loss: float,
    total_export: float,
    region: str,
    basin_name: str,
    constituent: str,
    basin_scale: str,
    model: str,
    output_root: Path,
) -> Path:
    if summary.empty:
        raise ValueError("Cannot plot empty Sankey summary.")

    numbers = summary["DisplayValue"].tolist()
    names = summary.index.tolist()
    labels, orientations = build_labels_and_orientations(names)

    units = constituent_unit_label(constituent)

    output_dir = output_dir_for_region(
        region=region,
        basin_scale=basin_scale,
        constituent=constituent,
        output_root=output_root,
    )

    fig_w, fig_h = figure_size_for_summary(summary)
    title_fs, label_fs, total_fs = font_sizes_for_summary(summary)

    fig = plt.figure(figsize=(fig_w, fig_h))
    fig.subplots_adjust(
        bottom=0.08,
        left=0.05,
        top=0.90,
        right=0.95,
    )

    ax = fig.add_subplot(
        1,
        1,
        1,
        xticks=[],
        yticks=[],
    )

    plt.rc("font", size=label_fs)
    ax.axis("off")

    Sankey(
        flows=numbers,
        labels=labels,
        orientations=orientations,
        ax=ax,
        format="%.2f",
        unit=f" {units.replace('/yr', '/y')}",
        scale=scale_for_constituent(region, constituent),
        offset=0.25,
        head_angle=100,
        alpha=0.75,
        lw=1,
        facecolor="brown",
    ).finish()

    plt.title(
        f"{region} | {basin_name} | {constituent} | "
        f"{basin_scale} | {model} | Unit: {units}",
        fontsize=title_fs,
    )

    supply_pos, export_pos, loss_pos = text_positions(region)

    if len(summary) >= 7:
        supply_pos = (
            supply_pos[0] - 0.10,
            supply_pos[1],
        )
        export_pos = (
            export_pos[0] + 0.10,
            export_pos[1] + 0.05,
        )
        loss_pos = (
            loss_pos[0],
            loss_pos[1] - 0.10,
        )

    plt.text(
        supply_pos[0],
        supply_pos[1],
        f"TOTAL SUPPLY\n~ {total_supply:.2f} {units}",
        fontsize=total_fs,
        rotation=90,
    )

    plt.text(
        export_pos[0],
        export_pos[1],
        f"TOTAL EXPORT\n~ {total_export:.2f} {units}",
        fontsize=total_fs,
    )

    plt.text(
        loss_pos[0],
        loss_pos[1],
        f"TOTAL LOSS\n~ {total_loss:.2f} {units}",
        fontsize=total_fs,
    )

    out_path = (
        output_dir
        / f"{safe_name(basin_name)}_{constituent}_{basin_scale}_budget.png"
    )

    plt.savefig(
        out_path,
        dpi=220,
        bbox_inches="tight",
        pad_inches=0.3,
    )

    plt.close()

    return out_path


# =========================================================
# RUN
# =========================================================

def run_one(
    source_sink_all: pd.DataFrame,
    region: str,
    basin_name: str,
    constituent: str,
    basin_scale: str,
    model: str,
    output_root: Path,
) -> Path:
    source_sink = load_source_sink_for_basin(
        source_sink_all=source_sink_all,
        region=region,
        basin_name=basin_name,
        constituent=constituent,
        model=model,
    )

    print(
        "\nSource-sink summary rows: "
        f"region={region}, basin={basin_name}, constituent={constituent}"
    )
    print(source_sink[["BudgetGroup", "DisplayValue"]])

    summary, total_supply, total_loss, total_export = build_summary_tables(
        source_sink=source_sink,
        constituent=constituent,
    )

    balance_check = total_supply - total_loss - total_export

    print(f"\n=== {region} | {basin_name} | {constituent} ===")
    print(summary)
    print(
        f"Total supply = {total_supply:.6f} "
        f"{constituent_unit_label(constituent)}"
    )
    print(
        f"Total loss   = {total_loss:.6f} "
        f"{constituent_unit_label(constituent)}"
    )
    print(
        f"Total export = {total_export:.6f} "
        f"{constituent_unit_label(constituent)}"
    )
    print(
        "Balance check "
        f"(supply - loss - export) = {balance_check:.6f} "
        f"{constituent_unit_label(constituent)}"
    )
    print(
        f"Summary net = {summary['DisplayValue'].sum():.6f} "
        f"{constituent_unit_label(constituent)}"
    )

    out_path = make_plot(
        summary=summary,
        total_supply=total_supply,
        total_loss=total_loss,
        total_export=total_export,
        region=region,
        basin_name=basin_name,
        constituent=constituent,
        basin_scale=basin_scale,
        model=model,
        output_root=output_root,
    )

    print(f"Saved: {out_path}")
    return out_path


def _validate_constituents(constituents: list[str] | None) -> list[str]:
    constituents = SUPPORTED_CONSTITUENTS if constituents is None else constituents

    if not constituents:
        raise ValueError("No constituents supplied.")

    invalid = [con for con in constituents if con not in SUPPORTED_CONSTITUENTS]

    if invalid:
        raise ValueError(
            f"Unsupported constituents: {invalid}. "
            f"Supported: {SUPPORTED_CONSTITUENTS}"
        )

    return constituents


def run_source_sink_sankey_for_all_basins(
    *,
    cfg: object | None = None,
    base_path: str | Path | None = None,
    main_path: str | Path | None = None,
    source_sink_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
    regions: list[str] | str | None = None,
    constituents: list[str] | str | None = None,
    basin_scale: str = DEFAULT_BASIN_SCALE,
    model: str | None = None,
    process_model: str | None = None,
    scenario: str | None = None,
    bundle_dirs: dict[str, Path] | None = None,
    **_: object,
) -> dict[str, object]:
    """
    Generate source-sink Sankey diagrams for all basins.

    This function is designed to be called directly from
    run_report_card_bundle() or workflows_source_sink.py, without launching
    this script as a subprocess.
    """
    resolved_model = (model or process_model or scenario or DEFAULT_MODEL).upper()
    resolved_basin_scale = basin_scale.upper()

    if isinstance(regions, str):
        resolved_regions = _maybe_list(regions) or DEFAULT_REGIONS
    else:
        resolved_regions = regions or getattr(cfg, "regions", None) or DEFAULT_REGIONS

    if isinstance(constituents, str):
        resolved_constituents = _maybe_list(constituents)
    else:
        resolved_constituents = constituents

    resolved_constituents = _validate_constituents(resolved_constituents)

    resolved_base_path = Path(
        base_path
        or main_path
        or getattr(cfg, "main_path", None)
        or os.environ.get("GBR_BASE_PATH", ".")
    ).resolve()

    if source_sink_dir is None and bundle_dirs is not None:
        source_sink_dir = bundle_dirs.get("source_sink_summary")

    resolved_source_sink_dir = Path(
        source_sink_dir
        or resolved_base_path / "report_card_summary" / "source_sink"
    ).resolve()

    resolved_output_root = Path(
        output_root
        or output_dir
        or os.environ.get(
            "GBR_SANKEY_OUTPUT_ROOT",
            str(resolved_source_sink_dir / "sankey_diagrams"),
        )
    ).resolve()

    source_sink_all = load_source_sink_all(
        source_sink_dir=resolved_source_sink_dir,
        basin_scale=resolved_basin_scale,
    )

    print("\n============================================================")
    print("Running Sankey generation")
    print(f"Base path       : {resolved_base_path}")
    print(f"Source-sink dir : {resolved_source_sink_dir}")
    print(f"Basin scale     : {resolved_basin_scale}")
    print(f"Model           : {resolved_model}")
    print(f"Regions         : {', '.join(resolved_regions)}")
    print(f"Constituents    : {', '.join(resolved_constituents)}")
    print(f"Output root     : {resolved_output_root}")
    print("============================================================")

    files: dict[str, Path] = {}
    skipped: list[str] = []

    for region in resolved_regions:
        basin_list = get_basin_list(
            source_sink_all=source_sink_all,
            region=region,
            model=resolved_model,
        )

        print("\n" + "=" * 60)
        print(f"Region      : {region}")
        print(f"Basins found: {len(basin_list)}")

        for constituent in resolved_constituents:
            print(
                f"Output dir ({constituent}) : "
                f"{output_dir_for_region(region, resolved_basin_scale, constituent, resolved_output_root)}"
            )

        for basin_name in basin_list:
            for constituent in resolved_constituents:
                try:
                    out_path = run_one(
                        source_sink_all=source_sink_all,
                        region=region,
                        basin_name=basin_name,
                        constituent=constituent,
                        basin_scale=resolved_basin_scale,
                        model=resolved_model,
                        output_root=resolved_output_root,
                    )
                    key = f"{region}_{safe_name(basin_name)}_{constituent}_{resolved_basin_scale}"
                    files[key] = out_path
                except Exception as e:
                    msg = (
                        f"Skipped region={region}, basin={basin_name}, "
                        f"constituent={constituent}: {e}"
                    )
                    skipped.append(msg)
                    print(msg)

    return {
        "output_root": resolved_output_root,
        "source_sink_dir": resolved_source_sink_dir,
        "files": files,
        "skipped": skipped,
    }


def run_source_sink_sankey_all_basins(**kwargs: object) -> dict[str, object]:
    """Backward-compatible alias used by report-card bundle runners."""
    return run_source_sink_sankey_for_all_basins(**kwargs)


def export_source_sink_sankey_all_basins(**kwargs: object) -> dict[str, object]:
    """Backward-compatible alias used by reflective runners."""
    return run_source_sink_sankey_for_all_basins(**kwargs)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    base_path, source_sink_dir, output_root = resolve_paths(args)

    run_source_sink_sankey_for_all_basins(
        base_path=base_path,
        source_sink_dir=source_sink_dir,
        output_root=output_root,
        regions=args.regions,
        constituents=args.constituents,
        basin_scale=args.basin_scale,
        model=args.model,
    )


if __name__ == "__main__":
    main()