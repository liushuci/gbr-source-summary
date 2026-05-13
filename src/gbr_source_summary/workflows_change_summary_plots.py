from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .export import ensure_output_dir
from .workflows_compare import build_fu_basin_scenario_comparison
from .workflows_process import build_process_export_summaries


REGION_ORDER = ["CY", "WT", "BU", "MW", "FI", "BM"]

PROCESS_ORDER = ["Hillslope", "Streambank", "Gully"]

PROCESS_COLOURS = {
    "Hillslope": "green",
    "Streambank": "blue",
    "Gully": "pink",
}


def _normalise_constituents(constituents: list[str] | None) -> list[str]:
    if constituents is None:
        return ["FS", "CS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

    out = [str(c).strip().upper() for c in constituents if str(c).strip()]

    if "TSS" in out:
        raise ValueError("Use FS, not TSS.")

    return out


def _report_unit(con: str) -> str:
    con = str(con).upper().strip()

    if con in {"FS", "CS"}:
        return "kt/yr"

    return "t/yr"


def _kg_to_report(value: pd.Series, con: str, years: float) -> pd.Series:
    value = pd.to_numeric(value, errors="coerce").fillna(0.0)

    con = str(con).upper().strip()

    if con in {"FS", "CS"}:
        return value / 1e6 / years

    return value / 1e3 / years


def _normalise_process_name(name: str) -> str | None:
    s = str(name).lower()

    if "hillslope" in s:
        return "Hillslope"

    if "streambank" in s:
        return "Streambank"

    if "gully" in s:
        return "Gully"

    return None


def _first_numeric_column(df: pd.DataFrame) -> str:
    numeric_cols = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c])
    ]

    if numeric_cols:
        return numeric_cols[0]

    return df.columns[0]


def _lookup_35_order_from_cfg(cfg, region: str) -> list[str]:
    """
    Best-effort Basin_35 order from cfg lookup files, if available.

    If unavailable, plotting falls back to alphabetical order.
    """
    possible_attrs = [
        "basin_lookup",
        "region_lookup",
        "reg_link",
        "regional_link",
    ]

    for attr in possible_attrs:
        obj = getattr(cfg, attr, None)

        if isinstance(obj, pd.DataFrame):
            df = obj.copy()

            if "Region" in df.columns:
                df = df.loc[df["Region"].astype(str).str.upper() == region.upper()]

            if "Basin_35" in df.columns:
                return (
                    df["Basin_35"]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .tolist()
                )

    return []


def _sort_35_basins(
    df: pd.DataFrame,
    *,
    cfg,
    region: str,
) -> list[str]:
    lookup_order = _lookup_35_order_from_cfg(cfg, region)
    basins_found = df["Basin"].dropna().astype(str).drop_duplicates().tolist()

    ordered = [b for b in lookup_order if b in basins_found]
    remaining = sorted([b for b in basins_found if b not in ordered])

    return ordered + remaining


def _plot_process_change_by_region_35(
    df: pd.DataFrame,
    *,
    cfg,
    region: str,
    con: str,
    out_dir: Path,
) -> Path:
    """
    Plot BASE - CHANGE process reduction grouped at Basin_35 scale.

    One plot per region and constituent.
    """
    unit = _report_unit(con)

    basins = _sort_35_basins(df, cfg=cfg, region=region)
    y = np.arange(len(basins))

    fig_h = max(3.2, 0.55 * len(basins) + 1.8)
    fig, ax = plt.subplots(figsize=(10.5, fig_h))

    left_pos = np.zeros(len(basins))
    left_neg = np.zeros(len(basins))

    for process in PROCESS_ORDER:
        vals = (
            df.loc[df["Process"] == process]
            .set_index("Basin")
            .reindex(basins)["Value"]
            .fillna(0.0)
            .to_numpy()
        )

        pos = np.where(vals > 0, vals, 0.0)
        neg = np.where(vals < 0, vals, 0.0)

        ax.barh(
            y,
            pos,
            left=left_pos,
            label=process,
            color=PROCESS_COLOURS[process],
            edgecolor="black",
            linewidth=0.8,
        )

        ax.barh(
            y,
            neg,
            left=left_neg,
            color=PROCESS_COLOURS[process],
            edgecolor="black",
            linewidth=0.8,
        )

        left_pos += pos
        left_neg += neg

    ax.axvline(0, color="black", linewidth=1.0)

    ax.set_yticks(y)
    ax.set_yticklabels(basins, fontsize=10)
    ax.invert_yaxis()

    ax.set_xlabel(
        f"{region} — {con} total change by process "
        f"(BASE − CHANGE) [{unit}]",
        fontsize=11,
    )

    ax.set_title(
        f"{region} — {con} total change by process (35 basins)",
        fontsize=12,
        pad=18,
    )

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        ncol=3,
        frameon=False,
        fontsize=10,
    )

    fig.tight_layout()

    out_path = out_dir / f"{region}_{con}_process_change_35basins.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return out_path


def _plot_percent_reduction_35basins(
    df: pd.DataFrame,
    *,
    con: str,
    out_dir: Path,
) -> Path:
    """
    Plot GBR-wide percent reduction at Basin_35 scale.

    Region labels are placed further left using axes-fraction coordinates,
    so they do not overlap basin names.
    """
    plot_df = df.copy()

    plot_df["Region"] = pd.Categorical(
        plot_df["Region"],
        categories=REGION_ORDER,
        ordered=True,
    )

    plot_df = plot_df.sort_values(["Region", "Basin"]).reset_index(drop=True)

    labels = plot_df["Basin"].astype(str).tolist()
    values = plot_df["PercentReduction"].fillna(0.0).to_numpy()
    regions = plot_df["Region"].astype(str).tolist()

    y = np.arange(len(labels))

    fig_h = max(9.0, 0.30 * len(labels) + 2.2)
    fig, ax = plt.subplots(figsize=(8.4, fig_h))

    ax.barh(
        y,
        values,
        edgecolor="black",
        linewidth=0.7,
    )

    ax.axvline(0, color="black", linewidth=1.0)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()

    ax.set_title(
        f"GBR — {con} percent reduction (35 basins)",
        fontsize=12,
    )

    ax.set_xlabel(
        f"{con} reduction (%) = "
        f"(BASE − CHANGE) / (BASE − PREDEV) × 100",
        fontsize=9,
    )

    grouped = (
        plot_df.reset_index()
        .groupby("Region", observed=True)["index"]
        .agg(["min", "max"])
        .reset_index()
    )

    for _, row in grouped.iterrows():
        region = str(row["Region"])
        y_min = float(row["min"])
        y_max = float(row["max"])
        y_mid = (y_min + y_max) / 2.0

        ax.axhline(
            y_min - 0.5,
            color="black",
            linestyle="--",
            linewidth=0.6,
        )

        ax.text(
            -0.18,
            y_mid,
            region,
            transform=ax.get_yaxis_transform(),
            ha="right",
            va="center",
            fontsize=9,
            fontweight="bold",
            clip_on=False,
        )

    if not grouped.empty:
        ax.axhline(
            float(grouped["max"].max()) + 0.5,
            color="black",
            linestyle="--",
            linewidth=0.6,
        )

    # Extra left margin so region labels sit left of basin names.
    fig.subplots_adjust(left=0.30, right=0.98, top=0.95, bottom=0.06)

    out_path = out_dir / f"GBR_percentReduction_35basins_{con}.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return out_path


def _process_table_to_long(
    *,
    region: str,
    basin: str,
    con: str,
    base_df: pd.DataFrame,
    change_df: pd.DataFrame,
    years: float,
) -> pd.DataFrame:
    bdf = base_df.copy().reset_index()
    cdf = change_df.copy().reset_index()

    bdf = bdf.rename(columns={bdf.columns[0]: "ProcessRaw"})
    cdf = cdf.rename(columns={cdf.columns[0]: "ProcessRaw"})

    b_val = _first_numeric_column(bdf.drop(columns=["ProcessRaw"]))
    c_val = _first_numeric_column(cdf.drop(columns=["ProcessRaw"]))

    bdf = bdf[["ProcessRaw", b_val]].rename(columns={b_val: "BASE_kg"})
    cdf = cdf[["ProcessRaw", c_val]].rename(columns={c_val: "CHANGE_kg"})

    merged = bdf.merge(cdf, on="ProcessRaw", how="outer")

    merged["BASE_kg"] = pd.to_numeric(
        merged["BASE_kg"],
        errors="coerce",
    ).fillna(0.0)

    merged["CHANGE_kg"] = pd.to_numeric(
        merged["CHANGE_kg"],
        errors="coerce",
    ).fillna(0.0)

    merged["Process"] = merged["ProcessRaw"].map(_normalise_process_name)
    merged = merged.dropna(subset=["Process"])

    merged["Value"] = _kg_to_report(
        merged["BASE_kg"] - merged["CHANGE_kg"],
        con,
        years,
    )

    merged["Region"] = region
    merged["Basin"] = basin
    merged["Constituent"] = con
    merged["Units"] = _report_unit(con)

    return merged[
        [
            "Region",
            "Basin",
            "Constituent",
            "Process",
            "Value",
            "Units",
            "BASE_kg",
            "CHANGE_kg",
        ]
    ]


def run_change_summary_plots(
    *,
    cfg,
    output_dir: str | Path,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    bundle_dirs: dict[str, Path] | None = None,
):
    """
    Create change-model summary plots at Basin_35 scale.

    Outputs
    -------
    1. reduction_mass_per_y/<constituent>/
       - region process plots:
         BASE - CHANGE by Hillslope / Streambank / Gully
       - grouped to 35 basins, not 48 management units

    2. reduction_%/<constituent>/
       - GBR-wide percent reduction:
         (BASE - CHANGE) / (BASE - PREDEV) * 100
       - grouped to 35 basins
    """
    output_dir = ensure_output_dir(output_dir)
    constituents = _normalise_constituents(constituents)

    years = float(getattr(cfg, "model_years", 30))

    files: dict[str, str] = {}

    mass_root = ensure_output_dir(output_dir / "reduction_mass_per_y")
    percent_root = ensure_output_dir(output_dir / "reduction_%")

    # ------------------------------------------------------------
    # 1. Process change plots: BASE - CHANGE
    #    build_process_export_summaries returns:
    #    basin_by_region, region_by_region, combined
    # ------------------------------------------------------------
    base_basin, _, _ = build_process_export_summaries(
        cfg=cfg,
        regions=cfg.regions,
        constituents=constituents,
        model="BASE",
        value_column=value_column,
        units="kg",
    )

    change_basin, _, _ = build_process_export_summaries(
        cfg=cfg,
        regions=cfg.regions,
        constituents=constituents,
        model="CHANGE",
        value_column=value_column,
        units="kg",
    )

    for con in constituents:
        con_dir = ensure_output_dir(mass_root / con)
        all_rows = []

        for region in cfg.regions:
            base_region = base_basin.get(region, {})
            change_region = change_basin.get(region, {})

            for basin, base_con_dict in base_region.items():
                if con not in base_con_dict:
                    continue

                if basin not in change_region:
                    continue

                if con not in change_region[basin]:
                    continue

                long_df = _process_table_to_long(
                    region=region,
                    basin=str(basin),
                    con=con,
                    base_df=base_con_dict[con],
                    change_df=change_region[basin][con],
                    years=years,
                )

                if not long_df.empty:
                    all_rows.append(long_df)

        if not all_rows:
            continue

        process_48_df = pd.concat(all_rows, ignore_index=True)

        # This is the key fix:
        # aggregate the process-change output to 35 basins.
        # If the upstream workflow already returns Basin_35 names,
        # this preserves them. If it returns MU_48 but named as Basin,
        # this will still group by current Basin field.
        #
        # Your workflows_process should be configured to Basin_35 for this
        # output. The plot title and filename now clearly label 35 basins.
        process_35_df = (
            process_48_df
            .groupby(
                [
                    "Region",
                    "Basin",
                    "Constituent",
                    "Process",
                    "Units",
                ],
                as_index=False,
            )
            .agg(
                {
                    "Value": "sum",
                    "BASE_kg": "sum",
                    "CHANGE_kg": "sum",
                }
            )
        )

        csv_path = con_dir / f"GBR_{con}_process_change_35basins.csv"
        process_35_df.to_csv(csv_path, index=False)
        files[f"process_change_csv_{con}"] = str(csv_path)

        for region in cfg.regions:
            region_df = process_35_df.loc[
                process_35_df["Region"] == region
            ].copy()

            if region_df.empty:
                continue

            png_path = _plot_process_change_by_region_35(
                region_df,
                cfg=cfg,
                region=region,
                con=con,
                out_dir=con_dir,
            )

            files[f"process_change_plot_{region}_{con}"] = str(png_path)

    # ------------------------------------------------------------
    # 2. Percent reduction plots:
    #    (BASE - CHANGE) / (BASE - PREDEV) * 100
    #    build_fu_basin_scenario_comparison should return Basin_35 here.
    # ------------------------------------------------------------
    basin_compare = build_fu_basin_scenario_comparison(
        cfg=cfg,
        regions=cfg.regions,
        constituents=constituents,
        value_column=value_column,
        units="kg",
    )

    predev = basin_compare.get("predev_basin", {})
    base = basin_compare.get("base_basin", {})
    change = basin_compare.get("change_basin", {})

    for con in constituents:
        con_dir = ensure_output_dir(percent_root / con)
        rows = []

        for region in cfg.regions:
            base_region = base.get(region, {})
            predev_region = predev.get(region, {})
            change_region = change.get(region, {})

            for basin, base_df in base_region.items():
                if basin not in predev_region:
                    continue

                if basin not in change_region:
                    continue

                def _total(df: pd.DataFrame) -> float:
                    if con not in df.columns:
                        return 0.0

                    return float(
                        pd.to_numeric(
                            df[con],
                            errors="coerce",
                        )
                        .fillna(0.0)
                        .sum()
                    )

                base_total = _total(base_df)
                predev_total = _total(predev_region[basin])
                change_total = _total(change_region[basin])

                anthropogenic = base_total - predev_total
                reduction = base_total - change_total

                if np.isclose(anthropogenic, 0.0):
                    percent_reduction = np.nan
                else:
                    percent_reduction = reduction / anthropogenic * 100.0

                rows.append(
                    {
                        "Region": region,
                        "Basin": str(basin),
                        "Constituent": con,
                        "BASE_kg": base_total,
                        "PREDEV_kg": predev_total,
                        "CHANGE_kg": change_total,
                        "Anthropogenic_kg": anthropogenic,
                        "Reduction_kg": reduction,
                        "PercentReduction": percent_reduction,
                    }
                )

        percent_df = pd.DataFrame(rows)

        if percent_df.empty:
            continue

        percent_35_df = (
            percent_df
            .groupby(["Region", "Basin", "Constituent"], as_index=False)
            .agg(
                {
                    "BASE_kg": "sum",
                    "PREDEV_kg": "sum",
                    "CHANGE_kg": "sum",
                }
            )
        )

        percent_35_df["Anthropogenic_kg"] = (
            percent_35_df["BASE_kg"] - percent_35_df["PREDEV_kg"]
        )
        percent_35_df["Reduction_kg"] = (
            percent_35_df["BASE_kg"] - percent_35_df["CHANGE_kg"]
        )

        percent_35_df["PercentReduction"] = np.where(
            np.isclose(percent_35_df["Anthropogenic_kg"], 0.0),
            np.nan,
            percent_35_df["Reduction_kg"]
            / percent_35_df["Anthropogenic_kg"]
            * 100.0,
        )

        csv_path = con_dir / f"GBR_percentReduction_35basins_{con}.csv"
        percent_35_df.to_csv(csv_path, index=False)
        files[f"percent_reduction_csv_{con}"] = str(csv_path)

        png_path = _plot_percent_reduction_35basins(
            percent_35_df,
            con=con,
            out_dir=con_dir,
        )

        files[f"percent_reduction_plot_{con}"] = str(png_path)

    return {
        "output_dir": output_dir,
        "files": files,
    }