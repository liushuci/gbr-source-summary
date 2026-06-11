from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .export import ensure_output_dir
from .workflows_compare import build_fu_basin_scenario_comparison
from .workflows_process import build_process_export_summaries


REGION_ORDER = ["CY", "WT", "BU", "MW", "FI", "BM"]

REGION_NAME_MAP = {
    "CY": "Cape York",
    "WT": "Wet Tropics",
    "BU": "Burdekin",
    "MW": "Mackay\nWhitsunday",
    "FI": "Fitzroy",
    "BM": "Burnett Mary",
}

SEDIMENT_PARTICULATE_CONSTITUENTS = {"FS", "CS", "PN", "PP"}
DISSOLVED_CONSTITUENTS = {"DIN", "DON", "DIP", "DOP"}

PROCESS_ORDER_BY_GROUP = {
    "sediment_particulate": ["Hillslope", "Streambank", "Gully"],
    "dissolved": ["SurfaceRunoff", "Seepage", "PointSource"],
}

PROCESS_COLOURS = {
    "Hillslope": "green",
    "Streambank": "blue",
    "Gully": "pink",
    "SurfaceRunoff": "green",
    "Seepage": "blue",
    "PointSource": "pink",
}

DEFAULT_SCALE_SUFFIX = "48mu"
DEFAULT_SCALE_LABEL = "48 management units"


def _normalise_constituents(constituents: list[str] | None) -> list[str]:
    if constituents is None:
        return ["FS", "CS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

    out = [str(c).strip().upper() for c in constituents if str(c).strip()]

    if "TSS" in out:
        raise ValueError("Use FS, not TSS.")

    return out


def _process_order_for_constituent(con: str) -> list[str]:
    con = str(con).upper().strip()

    if con in DISSOLVED_CONSTITUENTS:
        return PROCESS_ORDER_BY_GROUP["dissolved"]

    return PROCESS_ORDER_BY_GROUP["sediment_particulate"]


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
    s = str(name).lower().strip()

    if "hillslope" in s:
        return "Hillslope"

    if "streambank" in s:
        return "Streambank"

    if "gully" in s:
        return "Gully"

    if (
        "diffuse dissolved" in s
        or "surface runoff" in s
        or "surfacerunoff" in s
        or "runoff" in s
    ):
        return "SurfaceRunoff"

    if "seepage" in s or "leached" in s:
        return "Seepage"

    if "point source" in s or "pointsource" in s:
        return "PointSource"

    return None


def _first_numeric_column(df: pd.DataFrame) -> str:
    numeric_cols = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c])
    ]

    if numeric_cols:
        return numeric_cols[0]

    return df.columns[0]


def _ordered_region_units(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["Region", "Basin"]].drop_duplicates().copy()

    out["Region"] = pd.Categorical(
        out["Region"],
        categories=REGION_ORDER,
        ordered=True,
    )

    out = out.sort_values(["Region", "Basin"]).reset_index(drop=True)

    return out


def _sort_units(df: pd.DataFrame) -> list[str]:
    return sorted(
        df["Basin"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .tolist()
    )


def _plot_process_change_by_region(
    df: pd.DataFrame,
    *,
    region: str,
    con: str,
    out_dir: Path,
    scale_suffix: str = DEFAULT_SCALE_SUFFIX,
    scale_label: str = DEFAULT_SCALE_LABEL,
) -> Path:
    unit = _report_unit(con)

    basins = _sort_units(df)
    y = np.arange(len(basins))

    fig_h = max(3.2, 0.55 * len(basins) + 1.8)
    fig, ax = plt.subplots(figsize=(10.5, fig_h))

    left_pos = np.zeros(len(basins))
    left_neg = np.zeros(len(basins))

    for process in _process_order_for_constituent(con):
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
        f"{region} — {con} total change by process ({scale_label})",
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

    out_path = out_dir / f"{region}_{con}_process_change_{scale_suffix}.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return out_path


def _plot_process_change_combined_regions(
    df: pd.DataFrame,
    *,
    con: str,
    out_dir: Path,
    scale_suffix: str = DEFAULT_SCALE_SUFFIX,
    scale_label: str = DEFAULT_SCALE_LABEL,
) -> Path:
    unit = _report_unit(con)

    plot_df = df.copy()
    ordered_units = _ordered_region_units(plot_df)

    labels = ordered_units["Basin"].astype(str).tolist()

    keys = (
        ordered_units["Region"].astype(str)
        + "||"
        + ordered_units["Basin"].astype(str)
    ).tolist()

    plot_df["_key"] = (
        plot_df["Region"].astype(str)
        + "||"
        + plot_df["Basin"].astype(str)
    )

    y = np.arange(len(labels))

    fig_h = max(9.0, 0.30 * len(labels) + 2.2)
    fig, ax = plt.subplots(figsize=(10.5, fig_h))

    left_pos = np.zeros(len(labels))
    left_neg = np.zeros(len(labels))

    for process in _process_order_for_constituent(con):
        vals = (
            plot_df.loc[plot_df["Process"] == process]
            .groupby("_key")["Value"]
            .sum()
            .reindex(keys)
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
            linewidth=0.7,
        )

        ax.barh(
            y,
            neg,
            left=left_neg,
            color=PROCESS_COLOURS[process],
            edgecolor="black",
            linewidth=0.7,
        )

        left_pos += pos
        left_neg += neg

    ax.axvline(0, color="black", linewidth=1.0)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()

    ax.set_xlabel(
        f"{con} change ({unit})",
        fontsize=10,
    )

    ax.set_title(
        f"GBR — {con} total change by process ({scale_label})",
        fontsize=12,
        pad=28,
    )

    grouped = (
        ordered_units.reset_index()
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
            linewidth=0.8,
        )

        ax.text(
            -0.16,
            y_mid,
            REGION_NAME_MAP.get(region, region),
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
            linewidth=0.8,
        )

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.1),
        ncol=3,
        frameon=True,
        fontsize=9,
    )

    fig.subplots_adjust(
        left=0.26,
        right=0.98,
        top=0.90,
        bottom=0.06,
    )

    out_path = out_dir / f"GBR_{con}_process_change_{scale_suffix}.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return out_path


def _plot_percent_reduction(
    df: pd.DataFrame,
    *,
    con: str,
    out_dir: Path,
    scale_suffix: str = DEFAULT_SCALE_SUFFIX,
    scale_label: str = DEFAULT_SCALE_LABEL,
) -> Path:
    plot_df = df.copy()

    plot_df["Region"] = pd.Categorical(
        plot_df["Region"],
        categories=REGION_ORDER,
        ordered=True,
    )

    plot_df = plot_df.sort_values(["Region", "Basin"]).reset_index(drop=True)

    labels = plot_df["Basin"].astype(str).tolist()
    values = plot_df["PercentReduction"].fillna(0.0).to_numpy()

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
        f"GBR — {con} percent reduction ({scale_label})",
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

    fig.subplots_adjust(left=0.30, right=0.98, top=0.95, bottom=0.06)

    out_path = out_dir / f"GBR_percentReduction_{scale_suffix}_{con}.png"
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

    allowed_processes = _process_order_for_constituent(con)
    merged = merged.loc[merged["Process"].isin(allowed_processes)].copy()

    merged["Value"] = _kg_to_report(
        merged["BASE_kg"] - merged["CHANGE_kg"],
        con,
        years,
    )
    TOLERANCE = 1e-6

    merged.loc[
        merged["Value"].abs() < TOLERANCE,
        "Value"
    ] = 0.0


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
    scale_suffix: str = DEFAULT_SCALE_SUFFIX,
    scale_label: str = DEFAULT_SCALE_LABEL,
):
    output_dir = ensure_output_dir(output_dir)
    constituents = _normalise_constituents(constituents)

    years = float(getattr(cfg, "model_years", 30))

    files: dict[str, str] = {}

    mass_root = ensure_output_dir(output_dir / "reduction_mass_per_y")
    percent_root = ensure_output_dir(output_dir / "reduction_%")

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

        process_df = pd.concat(all_rows, ignore_index=True)

        process_df = (
            process_df
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

        TOLERANCE = 1e-6

        basin_totals = (
            process_df
            .groupby(["Region", "Basin"])["Value"]
            .apply(lambda x: np.abs(x).sum())
        )

        valid_basins = basin_totals[
            basin_totals > TOLERANCE
        ].index

        process_df = process_df[
            process_df.set_index(
                ["Region", "Basin"]
            ).index.isin(valid_basins)
        ]

        csv_path = con_dir / f"GBR_{con}_process_change_{scale_suffix}.csv"
        process_df.to_csv(csv_path, index=False)
        files[f"process_change_csv_{con}"] = str(csv_path)

        for region in cfg.regions:
            region_df = process_df.loc[
                process_df["Region"] == region
            ].copy()

            if region_df.empty:
                continue

            png_path = _plot_process_change_by_region(
                region_df,
                region=region,
                con=con,
                out_dir=con_dir,
                scale_suffix=scale_suffix,
                scale_label=scale_label,
            )

            files[f"process_change_plot_{region}_{con}"] = str(png_path)

        gbr_png_path = _plot_process_change_combined_regions(
            process_df,
            con=con,
            out_dir=con_dir,
            scale_suffix=scale_suffix,
            scale_label=scale_label,
        )

        files[f"process_change_plot_GBR_{con}"] = str(gbr_png_path)

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

                rows.append(
                    {
                        "Region": region,
                        "Basin": str(basin),
                        "Constituent": con,
                        "BASE_kg": base_total,
                        "PREDEV_kg": predev_total,
                        "CHANGE_kg": change_total,
                    }
                )

        percent_df = pd.DataFrame(rows)

        if percent_df.empty:
            continue

        percent_df = (
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

        percent_df["Anthropogenic_kg"] = (
            percent_df["BASE_kg"] - percent_df["PREDEV_kg"]
        )

        percent_df["Reduction_kg"] = (
            percent_df["BASE_kg"] - percent_df["CHANGE_kg"]
        )

        percent_df["PercentReduction"] = np.where(
            np.isclose(percent_df["Anthropogenic_kg"], 0.0),
            np.nan,
            percent_df["Reduction_kg"]
            / percent_df["Anthropogenic_kg"]
            * 100.0,
        )

        csv_path = con_dir / f"GBR_percentReduction_{scale_suffix}_{con}.csv"
        percent_df.to_csv(csv_path, index=False)
        files[f"percent_reduction_csv_{con}"] = str(csv_path)

        png_path = _plot_percent_reduction(
            percent_df,
            con=con,
            out_dir=con_dir,
            scale_suffix=scale_suffix,
            scale_label=scale_label,
        )

        files[f"percent_reduction_plot_{con}"] = str(png_path)

    return {
        "output_dir": output_dir,
        "files": files,
    }