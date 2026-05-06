from __future__ import annotations

from pathlib import Path
import re

import matplotlib.pyplot as plt
from matplotlib.sankey import Sankey
import pandas as pd

from gbr_source_summary.naming import standardise_constituent_names

# =========================================================
# CONFIG
# =========================================================

BASE_PATH = Path(r"F:/RC13_RC2023_24_Gold")
MODEL = "BASE"

REGION = "BM"
BASIN_SCALE = "MU48"   # "MU48" or "BASIN35"
BASIN_NAME = "Mary"

# None = run all supported constituents
CONSTITUENTS = None
# Example:
# CONSTITUENTS = ["FS", "PN", "PP", "DIN"]

SOURCE_SINK_DIR = BASE_PATH / "report_card_summary" / "source_sink"
OUTPUT_DIR = SOURCE_SINK_DIR / "sankey_diagrams"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_CONSTITUENTS = ["FS", "CS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

VALUE_COLUMN = "Total_Load_in_Kg"

LOSS_GROUPS = {
    "Extraction + Other Minor Losses",
    "FloodPlainDeposition",
    "ReservoirDeposition",
    "StreamDeposition",
}

# =========================================================
# HELPERS
# =========================================================

def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text)).strip("_")


def source_sink_csv_path() -> Path:
    if BASIN_SCALE.upper() == "MU48":
        return SOURCE_SINK_DIR / "mu48_source_sink.csv"
    if BASIN_SCALE.upper() == "BASIN35":
        return SOURCE_SINK_DIR / "basin35_source_sink.csv"
    raise ValueError("BASIN_SCALE must be 'MU48' or 'BASIN35'")


def constituent_unit_label(constituent: str) -> str:
    return "kt/yr" if constituent in {"FS", "CS"} else "t/yr"


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
    }
    return replacements.get(text, text.replace(" ", "").replace("_", "").replace("+", ""))


# =========================================================
# LOAD SOURCE-SINK SUMMARY CSV
# =========================================================

def load_source_sink_for_basin(constituent: str) -> pd.DataFrame:
    """
    Load source-sink summary from the exported basin summary CSV
    created earlier by run_source_sink_summary.py.

    Assumes values are already in report units:
    - FS, CS -> kt/yr
    - all others -> t/yr
    """
    csv_path = source_sink_csv_path()
    if not csv_path.exists():
        raise FileNotFoundError(f"Source-sink summary not found: {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]
    df["Constituent"] = standardise_constituent_names(df["Constituent"])

    required = ["Scenario", "Region", "Basin", "Constituent", "BudgetGroup", VALUE_COLUMN]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns in source-sink summary: {missing}")

    work = df.copy()
    work = work.loc[work["Scenario"] == MODEL].copy()
    work = work.loc[work["Region"] == REGION].copy()
    work = work.loc[work["Basin"] == BASIN_NAME].copy()
    work = work.loc[work["Constituent"] == constituent].copy()

    if work.empty:
        raise ValueError(
            f"No source-sink summary found for region={REGION}, basin={BASIN_NAME}, constituent={constituent}"
        )

    work[VALUE_COLUMN] = pd.to_numeric(work[VALUE_COLUMN], errors="coerce").fillna(0.0)
    work["_BudgetGroup_norm"] = work["BudgetGroup"].map(normalise_group_name)

    return work


# =========================================================
# VALUE HELPERS
# =========================================================

def get_ss_value(df: pd.DataFrame, key: str) -> float:
    """
    Get value from source-sink summary.
    Values are already in report units.
    """
    target = normalise_group_name(key)
    hit = df.loc[df["_BudgetGroup_norm"] == target, VALUE_COLUMN]

    if hit.empty:
        return 0.0

    return float(hit.sum())


# =========================================================
# BUILD SANKEY SUMMARY
# =========================================================

def build_summary_tables(
    source_sink: pd.DataFrame,
    constituent: str,
) -> tuple[pd.DataFrame, float, float, float]:
    """
    Build Sankey input using only source-sink summary.

    Convention:
    - supplies are positive
    - losses are negative
    - export is calculated as residual:
        total_export = total_supply - total_loss
    and shown as negative in the Sankey flows.
    """
    summary_parts: list[tuple[str, float]] = []

    # -----------------------------------------------------
    # SUPPLY (positive)
    # -----------------------------------------------------
    if constituent in {"FS", "CS", "PN", "PP"}:
        streambank_supply = get_ss_value(source_sink, "Streambank")
        hillslope_supply = get_ss_value(source_sink, "Hillslope")
        gully_supply = get_ss_value(source_sink, "Gully")
        channel_supply = get_ss_value(source_sink, "ChannelRemobilisation")

        for name, val in [
            ("Streambank_supply", streambank_supply),
            ("Hillslope_supply", hillslope_supply),
            ("Gully_supply", gully_supply),
            ("ChannelRemobilisation_supply", channel_supply),
        ]:
            if val != 0:
                summary_parts.append((name, abs(val)))

        total_supply = (
            abs(streambank_supply)
            + abs(hillslope_supply)
            + abs(gully_supply)
            + abs(channel_supply)
        )

    else:
        surface_supply = get_ss_value(source_sink, "SurfaceRunoff")
        seepage_supply = get_ss_value(source_sink, "Seepage")
        point_supply = get_ss_value(source_sink, "PointSource")

        for name, val in [
            ("SurfaceRunoff_supply", surface_supply),
            ("Seepage_supply", seepage_supply),
            ("PointSource_supply", point_supply),
        ]:
            if val != 0:
                summary_parts.append((name, abs(val)))

        total_supply = (
            abs(surface_supply)
            + abs(seepage_supply)
            + abs(point_supply)
        )

    # -----------------------------------------------------
    # LOSSES (negative)
    # -----------------------------------------------------
    extraction = get_ss_value(source_sink, "Extraction + Other Minor Losses")
    floodplain = get_ss_value(source_sink, "FloodPlainDeposition")
    reservoir = get_ss_value(source_sink, "ReservoirDeposition")
    stream_dep = get_ss_value(source_sink, "StreamDeposition")

    losses = {
        "Extraction_Other_loss": extraction,
        "FloodPlainDeposition_loss": floodplain,
        "ReservoirDeposition_loss": reservoir,
        "StreamDeposition_loss": stream_dep,
    }

    total_loss = 0.0
    for name, val in losses.items():
        if val != 0:
            summary_parts.append((name, -abs(val)))
            total_loss += abs(val)

    # -----------------------------------------------------
    # EXPORT (negative residual)
    # -----------------------------------------------------
    total_export = total_supply - total_loss

    if total_export < -1e-9:
        raise ValueError(
            f"Computed export is negative for {REGION} | {BASIN_NAME} | {constituent}: "
            f"supply={total_supply:.6f}, loss={total_loss:.6f}, export={total_export:.6f}. "
            f"Check the source-sink summary inputs."
        )

    if total_export > 0:
        summary_parts.append(("Export", -abs(total_export)))

    # -----------------------------------------------------
    # FINAL TABLE
    # -----------------------------------------------------
    summary = pd.DataFrame(summary_parts, columns=["Name", "DisplayValue"])
    summary = summary.set_index("Name")
    summary = summary[summary["DisplayValue"] != 0]

    return summary, total_supply, total_loss, total_export


# =========================================================
# PLOT
# =========================================================

def build_labels_and_orientations(names: list[str]) -> tuple[list[str], list[int]]:
    label_map = {
        "Streambank_supply": "Streambank\nSupply",
        "Hillslope_supply": "Hillslope\nSupply",
        "Gully_supply": "Gully\nSupply",
        "ChannelRemobilisation_supply": "Channel\nRemobilisation\nSupply",
        "SurfaceRunoff_supply": "SurfaceRunoff\nSupply",
        "Seepage_supply": "Seepage\nSupply",
        "PointSource_supply": "PointSource\nSupply",
        "Extraction_Other_loss": "Extraction and\nOther\nMinor Losses",
        "FloodPlainDeposition_loss": "Floodplain\ndeposition",
        "ReservoirDeposition_loss": "Reservoir\nDeposition",
        "StreamDeposition_loss": "Stream\nDeposition",
        "Export": "Export",
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
        "Export": 1,
    }

    labels = [label_map.get(name, name.replace("_", "\n")) for name in names]
    orientations = [orient_map.get(name, 0) for name in names]
    return labels, orientations


def scale_for_constituent(region: str, constituent: str) -> float:
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


def text_positions(region: str) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
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
        supply_pos = (-1.40, 0.20)
        export_pos = (1.30, 0.30)
        loss_pos = (0.70, -1.30)

    return supply_pos, export_pos, loss_pos


def make_plot(
    summary: pd.DataFrame,
    total_supply: float,
    total_loss: float,
    total_export: float,
    constituent: str,
) -> Path:
    numbers = summary["DisplayValue"].tolist()
    names = summary.index.tolist()
    labels, orientations = build_labels_and_orientations(names)
    units = constituent_unit_label(constituent)

    fig = plt.figure(figsize=(16, 10))
    fig.subplots_adjust(bottom=0.1, left=0.06, top=0.92, right=0.94)
    ax = fig.add_subplot(1, 1, 1, xticks=[], yticks=[])
    plt.rc("font", size=12)
    ax.axis("off")

    Sankey(
        flows=numbers,
        labels=labels,
        orientations=orientations,
        ax=ax,
        format="%.2f",
        unit=f" {units.replace('/yr', '/y')}",
        scale=scale_for_constituent(REGION, constituent),
        offset=0.2,
        head_angle=100,
        alpha=0.75,
        lw=1,
        facecolor="brown",
    ).finish()

    plt.title(f"{BASIN_NAME} | {constituent} | {BASIN_SCALE} | {MODEL}", fontsize=24)

    supply_pos, export_pos, loss_pos = text_positions(REGION)

    plt.text(
        supply_pos[0],
        supply_pos[1],
        f"TOTAL SUPPLY\n~ {round(total_supply, 0):.0f} {units}",
        fontsize=20,
        rotation=90,
    )
    plt.text(
        export_pos[0],
        export_pos[1],
        f"TOTAL EXPORT\n~ {round(total_export, 0):.0f} {units}",
        fontsize=20,
    )
    plt.text(
        loss_pos[0],
        loss_pos[1],
        f"TOTAL LOSS\n~ {round(total_loss, 0):.0f} {units}",
        fontsize=20,
    )

    out_path = OUTPUT_DIR / f"{safe_name(BASIN_NAME)}_{constituent}_{BASIN_SCALE}_budget.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    return out_path


# =========================================================
# RUN
# =========================================================

def run_one(constituent: str) -> None:
    source_sink = load_source_sink_for_basin(constituent)

    print("\nSource-sink summary rows:")
    print(source_sink[["BudgetGroup", VALUE_COLUMN]])

    summary, total_supply, total_loss, total_export = build_summary_tables(
        source_sink=source_sink,
        constituent=constituent,
    )

    print(f"\n=== {constituent} ===")
    print(summary)
    print(f"Summary net = {summary['DisplayValue'].sum():.6f}")

    out_path = make_plot(
        summary=summary,
        total_supply=total_supply,
        total_loss=total_loss,
        total_export=total_export,
        constituent=constituent,
    )
    print(f"Saved: {out_path}")


def main() -> None:
    constituents = SUPPORTED_CONSTITUENTS if CONSTITUENTS is None else CONSTITUENTS

    for constituent in constituents:
        try:
            run_one(constituent)
        except Exception as e:
            print(f"Skipped {constituent}: {e}")


if __name__ == "__main__":
    main()