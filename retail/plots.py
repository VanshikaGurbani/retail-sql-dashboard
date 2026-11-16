"""Static figures for the README and notebook. Titles state the finding and are built from the
results dict, so a title can never disagree with the number it describes. Colours are the
Okabe-Ito palette, which stays distinguishable under the common forms of colour blindness;
every series is also labelled directly, not by colour alone."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from retail.config import PALETTE as P  # noqa: E402

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "font.size": 10,
    }
)


def gbp(x: float, digits: int = 0) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}£{x / 1e6:.{max(digits, 2)}f}M"
    if x >= 1e3:
        return f"{sign}£{x / 1e3:.{digits}f}k"
    return f"{sign}£{x:.0f}"


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def revenue_trend(res: dict, out: Path) -> Path:
    m = res["monthly"]
    h = res["headline"]
    x = np.arange(len(m))
    rev = np.array([r["net_revenue"] for r in m])
    avg3 = np.array([r["net_revenue_3m_avg"] for r in m])
    labels = [r["month"][:7] for r in m]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.bar(x, rev / 1e3, color=P["blue"], label="Net revenue per month", width=0.75)
    ax.plot(x, avg3 / 1e3, color=P["orange"], lw=2.5, marker="o", ms=3, label="3-month average")
    for i, r in enumerate(m):
        if r["month"][5:7] in ("09", "10", "11"):
            ax.axvspan(i - 0.5, i + 0.5, color=P["sky"], alpha=0.18, lw=0)
    ax.set_xticks(x[::2])
    ax.set_xticklabels(labels[::2], rotation=45, ha="right")
    ax.set_ylabel("Net revenue (£ thousands)")
    direction = "up" if h["yoy_growth"] >= 0 else "down"
    ax.set_title(
        f"Revenue is {direction} {pct(abs(h['yoy_growth']))} on the first year, "
        f"and September to November brings {pct(h['sepnov_share_year2'], 0)} of it"
    )
    from matplotlib.patches import Patch

    handles, labels_ = ax.get_legend_handles_labels()
    handles.append(Patch(facecolor=P["sky"], alpha=0.3, label="September to November"))
    ax.legend(handles=handles, frameon=False, loc="upper left", ncols=3)
    ax.set_ylim(0, max(rev) / 1e3 * 1.15)
    return _save(fig, out)


def revenue_drivers(res: dict, out: Path) -> Path:
    d = [r for r in res["yoy"] if r["sort_order"] < 4]
    total = [r for r in res["yoy"] if r["sort_order"] == 4][0]["revenue_effect"]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    vals = [r["revenue_effect"] / 1e3 for r in d]
    colours = [P["blue"] if v >= 0 else P["vermillion"] for v in vals]
    y = np.arange(len(d))[::-1]
    ax.barh(y, vals, color=colours)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([r["driver"] for r in d])
    for yi, v in zip(y, vals):
        ax.text(
            v + (6 if v >= 0 else -6),
            yi,
            f"{'+' if v >= 0 else '-'}£{abs(v):.0f}k",
            va="center",
            ha="left" if v >= 0 else "right",
        )
    biggest = max(d, key=lambda r: abs(r["revenue_effect"]))
    word = "fell" if total < 0 else "rose"
    ax.set_title(
        f"Identified-customer revenue {word} {gbp(abs(total))}; "
        f"{biggest['driver'].lower()} was the largest driver"
    )
    ax.set_xlabel("Contribution to the year-on-year change in net revenue (£ thousands)")
    lim = max(abs(v) for v in vals) * 1.35
    ax.set_xlim(-lim, lim)
    return _save(fig, out)


def retention(res: dict, out_curve: Path, out_heatmap: Path) -> tuple[Path, Path]:
    c = [r for r in res["retention_curve"] if r["month_offset"] <= 12]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    xs = [r["month_offset"] for r in c]
    ys = [r["retention_rate"] * 100 for r in c]
    ax.plot(xs, ys, color=P["blue"], lw=2.5, marker="o")
    for xi, yi in zip(xs, ys):
        if xi in (1, 3, 6, 9, 12):
            ax.annotate(
                f"{yi:.0f}%", (xi, yi), textcoords="offset points", xytext=(0, 8), ha="center"
            )
    ax.set_xlabel("Months since a customer's first purchase")
    ax.set_ylabel("Share of the cohort buying that month (%)")
    ax.set_ylim(0, 40)
    m1 = next(r for r in res["retention_curve"] if r["month_offset"] == 1)
    ax.set_title(
        f"About {pct(m1['retention_rate'], 0)} of new customers buy again the next month, then it levels off"
    )
    _save(fig, out_curve)

    grid = res["cohort_grid"]
    observed = {r["cohort_month"] for r in grid if r["month_offset"] >= 1}
    cohorts = sorted(c for c in observed if c > res["headline"]["window_start"][:7] + "-01")
    max_off = 12
    mat = np.full((len(cohorts), max_off + 1), np.nan)
    for r in grid:
        if r["cohort_month"] in cohorts and r["month_offset"] <= max_off:
            mat[cohorts.index(r["cohort_month"]), r["month_offset"]] = (
                100 * r["active_customers"] / r["cohort_size"]
            )
    fig, ax = plt.subplots(figsize=(9, 6.2))
    im = ax.imshow(mat[:, 1:], aspect="auto", cmap="cividis", vmin=0, vmax=40)
    ax.set_xticks(range(max_off))
    ax.set_xticklabels(range(1, max_off + 1))
    ax.set_yticks(range(len(cohorts)))
    ax.set_yticklabels([c[:7] for c in cohorts], fontsize=8)
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Cohort (month of first purchase)")
    for i in range(mat.shape[0]):
        for j in range(1, mat.shape[1]):
            if not np.isnan(mat[i, j]):
                ax.text(
                    j - 1,
                    i,
                    f"{mat[i, j]:.0f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if mat[i, j] < 22 else "black",
                )
    cb = fig.colorbar(im, ax=ax)
    cb.set_label("% of cohort buying (blank = not yet observable)")
    early = np.nanmean(mat[:, 1:7], axis=1)
    worst = cohorts[int(np.nanargmin(early))][:7]
    ax.set_title(
        f"Retention by cohort: the {worst} cohort kept the fewest customers in its first 6 months"
    )
    ax.spines[:].set_visible(False)
    _save(fig, out_heatmap)
    return out_curve, out_heatmap


def segments(res: dict, out: Path) -> Path:
    s = sorted(res["segments"], key=lambda r: -r["revenue_share"])
    names = [r["segment"] for r in s]
    y = np.arange(len(s))[::-1]
    w = 0.26
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.barh(
        y + w, [r["customer_share"] * 100 for r in s], w, color=P["sky"], label="Share of customers"
    )
    ax.barh(
        y,
        [r["revenue_share"] * 100 for r in s],
        w,
        color=P["blue"],
        label="Share of trailing 12-month revenue",
    )
    ax.barh(
        y - w,
        [(r["same_season_lapse_rate"]) * 100 for r in s],
        w,
        color=P["vermillion"],
        label="Lapse rate (did not buy next Dec to Feb)",
    )
    for yi, r in zip(y, s):
        ax.text(
            r["customer_share"] * 100 + 0.8,
            yi + w,
            f"{r['customer_share'] * 100:.0f}%",
            va="center",
            fontsize=8,
        )
        ax.text(
            r["revenue_share"] * 100 + 0.8,
            yi,
            f"{r['revenue_share'] * 100:.0f}%",
            va="center",
            fontsize=8,
        )
        ax.text(
            r["same_season_lapse_rate"] * 100 + 0.8,
            yi - w,
            f"{r['same_season_lapse_rate'] * 100:.0f}%",
            va="center",
            fontsize=8,
        )
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlabel("Percent")
    top = s[0]
    ax.set_title(
        f"{top['segment']} are {pct(top['customer_share'], 0)} of customers but {pct(top['revenue_share'], 0)} of revenue"
    )
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncols=3)
    return _save(fig, out)


def scenario(res: dict, out: Path) -> Path:
    sc = res["scenario"]
    labels = [f"{r['lapse_reduction'] * 100:.0f}% fewer\nlapses" for r in sc]
    x = np.arange(len(sc))
    fig, ax = plt.subplots(figsize=(8.5, 4.3))
    ax.bar(
        x - 0.2,
        [r["recovered_revenue"] / 1e3 for r in sc],
        0.4,
        color=P["blue"],
        label="Winter lapse rates (base case)",
    )
    ax.bar(
        x + 0.2,
        [r["recovered_revenue_pooled_rates"] / 1e3 for r in sc],
        0.4,
        color=P["orange"],
        label="All-season average lapse rates",
    )
    for xi, r in zip(x, sc):
        ax.text(
            xi - 0.2,
            r["recovered_revenue"] / 1e3 + 2,
            f"£{r['recovered_revenue'] / 1e3:.0f}k",
            ha="center",
            fontsize=9,
        )
        ax.text(
            xi + 0.2,
            r["recovered_revenue_pooled_rates"] / 1e3 + 2,
            f"£{r['recovered_revenue_pooled_rates'] / 1e3:.0f}k",
            ha="center",
            fontsize=9,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Revenue recovered next quarter (£ thousands)")
    ax.set_title("Scenario, not a measurement: revenue a retention campaign could protect")
    ax.legend(frameon=False, loc="upper left")
    return _save(fig, out)


def dq_bridge(res: dict, out: Path) -> Path:
    steps = [r for r in res["bridge"] if r["step"] not in (0, 99) and r["n_rows"] != 0]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    y = np.arange(len(steps))[::-1]
    ax.barh(y, [-r["n_rows"] for r in steps], color=P["blue"])
    ax.set_yticks(y)
    ax.set_yticklabels([r["label"].replace("_", " ") for r in steps])
    for yi, r in zip(y, steps):
        ax.text(-r["n_rows"], yi, f" {-r['n_rows']:,}", va="center")
    h = res["headline"]
    ax.set_title(
        f"{h['kept_rows']:,} of {h['raw_rows']:,} rows ({pct(h['kept_rows'] / h['raw_rows'], 0)}) survive cleaning"
    )
    ax.set_xlabel("Rows removed by each rule (first matching rule wins)")
    ax.set_xlim(0, max(-r["n_rows"] for r in steps) * 1.18)
    return _save(fig, out)


def all_figures(res: dict, fig_dir: Path) -> dict[str, Path]:
    out = {
        "revenue_trend": revenue_trend(res, fig_dir / "revenue_trend.png"),
        "revenue_drivers": revenue_drivers(res, fig_dir / "revenue_drivers.png"),
        "segments": segments(res, fig_dir / "rfm_segments.png"),
        "scenario": scenario(res, fig_dir / "scenario_range.png"),
        "dq_bridge": dq_bridge(res, fig_dir / "dq_bridge.png"),
    }
    curve, heat = retention(res, fig_dir / "retention_curve.png", fig_dir / "cohort_heatmap.png")
    out["retention_curve"], out["cohort_heatmap"] = curve, heat
    return out
