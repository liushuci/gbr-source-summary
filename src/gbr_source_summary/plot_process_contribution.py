from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd


KG_TO_T = 1 / 1000.0
KG_TO_KT = 1 / 1_000_000.0

PROCESS_COLORS = [
    "green",
    "blue",
    "pink",
    "orange",
    "purple",
    "red",
    "gold",
]

DROP_PROCESSES = [
    "ChannelRemobilisation",
    "Channel Remobilisation",
    "ChannelRemobilisationExport",
    "Channel Remobilisation Export",
]

REGION_DISPLAY_NAMES = {
    "CY": "Cape York",
    "WT": "Wet Tropics",
    "BU": "Burdekin",
    "MW": "Mackay\nWhitsunday",
    "FI": "Fitzroy",
    "BM": "Burnett Mary",
}


def _constituent_plot_name(constituent: str) -> str:
    return constituent


def _constituent_unit(constituent: str) -> str:
    return "kt/yr" if constituent in {"FS", "CS"} else "t/yr"


def _convert_units(
    df: pd.DataFrame,
    constituent: str,
    years: int,
) -> pd.DataFrame:
    out = df.astype(float).copy()

    if constituent in {"FS", "CS"}:
        return out * KG_TO_KT / years

    return out * KG_TO_T / years


def _rename_management_units(names: list[str]) -> list[str]:
    mapping = {
        "Olive-Pascoe": "Olive Pascoe",
        "Jacky Jacky Creek": "Jacky Jacky",
        "Jeannie River": "Jeannie",
        "Endeavour River": "Endeavour",
        "Normanby River": "Normanby",
        "Lockhart River": "Lockhart",
        "Stewart River": "Stewart",
        "PlaneC": "Plane",
        "Prossie": "Proserpine",
        "OConnel": "O-Connell",
        "Waterpark": "Water Park",
        "Don River": "Don",
    }

    return [mapping.get(x, x) for x in names]


def _clean_process_columns(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()

    out = out.drop(
        columns=[c for c in DROP_PROCESSES if c in out.columns],
        errors="ignore",
    )

    out = out.loc[:, out.abs().sum(axis=0) > 0]

    return out


def _plot_stacked_barh(
    table: pd.DataFrame,
    *,
    output_path: Path,
    xlabel: str,
    fontsize: int,
    legend_fontsize: int,
    xlim=None,
    region_labels: list[tuple[str, int, int]] | None = None,
) -> None:
    if table.empty:
        return

    n_rows = len(table)

    fig_height = max(5.5, n_rows * 0.34)
    fig_width = 14 if region_labels else 10

    fig, ax = plt.subplots(
        figsize=(fig_width, fig_height),
    )

    table.plot(
        kind="barh",
        stacked=True,
        fontsize=fontsize,
        color=PROCESS_COLORS[: len(table.columns)],
        edgecolor="black",
        ax=ax,
        legend=False,
    )

    if xlim is not None:
        ax.set_xlim(xlim)

    ax.set_xlabel(xlabel, size=12)
    ax.set_ylabel("")

    ax.get_xaxis().set_major_formatter(
        matplotlib.ticker.FuncFormatter(
            lambda x, p: format(int(x), ",")
        )
    )

    if region_labels:
        x_min, x_max = ax.get_xlim()
        label_x = x_min - (x_max - x_min) * 0.16

        for label, start, end in region_labels:
            mid = (start + end) / 2.0

            ax.text(
                label_x,
                mid,
                label,
                size=11,
                rotation=0,
                weight="bold",
                va="center",
                ha="right",
                clip_on=False,
            )

            if end < len(table) - 1:
                ax.axhline(
                    y=end + 0.5,
                    color="black",
                    linestyle="-",
                    lw=0.8,
                )

    handles, labels = ax.get_legend_handles_labels()

    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.01),
        fancybox=True,
        shadow=True,
        ncol=min(4, max(1, len(table.columns))),
        fontsize=legend_fontsize,
        frameon=True,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if region_labels:
        fig.subplots_adjust(
            left=0.28,
            right=0.98,
            bottom=0.06,
            top=0.93,
        )
    else:
        fig.tight_layout(
            rect=[0, 0, 1, 0.90],
        )

    fig.savefig(
        output_path,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close(fig)


def plot_process_contribution_exports(
    basin_by_region: dict,
    *,
    output_dir: str | Path,
    constituents: list[str] | None = None,
    years: int = 30,
    value_column: str = "LoadToRegExport (kg)",
) -> dict[str, Path]:
    output_dir = Path(output_dir)

    files: dict[str, Path] = {}

    if constituents is None:
        constituents = [
            "FS",
            "CS",
            "PN",
            "PP",
            "DIN",
            "DON",
            "DIP",
            "DOP",
        ]

    for constituent in constituents:
        constituent_name = _constituent_plot_name(constituent)

        gbr_tables = []
        gbr_names = []
        gbr_region_ranges = []
        row_start = 0

        for region, basin_dict in basin_by_region.items():
            region_tables = []
            region_names = []

            for basin, constituent_dict in basin_dict.items():
                if constituent not in constituent_dict:
                    continue

                df = constituent_dict[constituent]

                if df.empty:
                    continue

                if value_column not in df.columns:
                    continue

                series = df[value_column].copy().astype(float)
                series.index = df.index

                region_tables.append(series)
                region_names.append(basin)

                gbr_tables.append(series)
                gbr_names.append(basin)

            if not region_tables:
                continue

            row_end = row_start + len(region_tables) - 1
            gbr_region_ranges.append(
                (
                    REGION_DISPLAY_NAMES.get(region, region),
                    row_start,
                    row_end,
                )
            )
            row_start = row_end + 1

            region_plot_table = pd.DataFrame(
                region_tables,
                index=_rename_management_units(region_names),
            )

            region_plot_table = _clean_process_columns(region_plot_table)

            if region_plot_table.empty:
                continue

            region_plot_table = _convert_units(
                region_plot_table,
                constituent,
                years,
            )

            region_plot_table = region_plot_table.fillna(0)

            region_plot_table["total"] = region_plot_table.sum(axis=1)

            region_percent = (
                region_plot_table.div(
                    region_plot_table["total"].replace(0, pd.NA),
                    axis="index",
                )
                * 100
            ).fillna(0)

            region_plot_table = region_plot_table.iloc[:, :-1]
            region_percent = region_percent.iloc[:, :-1]

            region_out = output_dir / region / "processBasedExports"

            unit = _constituent_unit(constituent)

            tonnage_path = region_out / f"processTonnage_{constituent_name}.png"
            percent_path = region_out / f"processPercent_{constituent_name}.png"

            _plot_stacked_barh(
                region_plot_table,
                output_path=tonnage_path,
                xlabel=f"{constituent_name} Load ({unit})",
                fontsize=14,
                legend_fontsize=12,
            )

            _plot_stacked_barh(
                region_percent,
                output_path=percent_path,
                xlabel=f"{constituent_name} Load Contribution (%)",
                fontsize=14,
                legend_fontsize=12,
                xlim=[0, 100],
            )

            files[f"{region}_{constituent_name}_tonnage_png"] = tonnage_path
            files[f"{region}_{constituent_name}_percent_png"] = percent_path

        if not gbr_tables:
            continue

        gbr_plot_table = pd.DataFrame(
            gbr_tables,
            index=_rename_management_units(gbr_names),
        )

        gbr_plot_table = _clean_process_columns(gbr_plot_table)

        if gbr_plot_table.empty:
            continue

        gbr_plot_table = _convert_units(
            gbr_plot_table,
            constituent,
            years,
        )

        gbr_plot_table = gbr_plot_table.fillna(0)

        gbr_plot_table["total"] = gbr_plot_table.sum(axis=1)

        gbr_percent = (
            gbr_plot_table.div(
                gbr_plot_table["total"].replace(0, pd.NA),
                axis="index",
            )
            * 100
        ).fillna(0)

        export_table = pd.DataFrame(
            gbr_plot_table["total"],
        )

        export_table.columns = [
            f"export({_constituent_unit(constituent)})",
        ]

        gbr_plot_table = gbr_plot_table.iloc[:, :-1]
        gbr_percent = gbr_percent.iloc[:, :-1]

        gbr_out = output_dir / "GBR"
        various_tables_out = gbr_out / "variousTables"
        process_out = gbr_out / "processBasedExports"

        various_tables_out.mkdir(
            parents=True,
            exist_ok=True,
        )

        process_out.mkdir(
            parents=True,
            exist_ok=True,
        )

        tonnage_path = process_out / f"processTonnage_{constituent_name}.png"
        percent_path = process_out / f"processPercent_{constituent_name}.png"
        export_csv = various_tables_out / f"exportTonnage_{constituent_name}.csv"

        _plot_stacked_barh(
            gbr_plot_table,
            output_path=tonnage_path,
            xlabel=f"{constituent_name} Load ({_constituent_unit(constituent)})",
            fontsize=10,
            legend_fontsize=10,
            region_labels=gbr_region_ranges,
        )

        _plot_stacked_barh(
            gbr_percent,
            output_path=percent_path,
            xlabel=f"{constituent_name} Load Contribution (%)",
            fontsize=10,
            legend_fontsize=10,
            xlim=[0, 100],
            region_labels=gbr_region_ranges,
        )

        export_table.to_csv(export_csv)

        files[f"GBR_{constituent_name}_tonnage_png"] = tonnage_path
        files[f"GBR_{constituent_name}_percent_png"] = percent_path
        files[f"GBR_{constituent_name}_export_csv"] = export_csv

    return files