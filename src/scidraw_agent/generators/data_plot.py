"""Data-plot generator (matplotlib) — distribution rigor behind the same engine.

Enforces, by construction:
- NO dynamite (bar+SEM) plots for continuous data — show the distribution (BLOCK).
- geometry by sample size: n<=10 jittered dots; 10<n<=50 box + jittered points;
  n>50 violin + box.
- overplotting: point opacity scaled to n.
- SuperPlot when nested replicates (>=3) are provided: points coloured by replicate,
  replicate means overlaid (stats belong on N replicates, not n observations).

Consumes the shared StyleSpec via `theme.mpl_rcparams`; the SVG it returns still passes
through `style_guard` in compose, so the same floors apply as for every other generator.
"""

from __future__ import annotations

import io
from dataclasses import replace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..models import PlotRequest, ScatterRequest, StandardsAction  # noqa: E402
from ..palette import PaletteRegistry  # noqa: E402
from ..standards.linter import RuleId, rule  # noqa: E402
from ..stats import Comparison, compare, linfit  # noqa: E402
from ..theme import StyleSpec, mpl_rcparams  # noqa: E402


class DynamitePlotError(Exception):
    """Raised when a bar+SEM plot is requested for continuous data (without override)."""

    def __init__(self) -> None:
        r = rule(RuleId.NO_DYNAMITE)
        super().__init__(r.message + f" ({r.source_url})")


def _action(rule_id: RuleId, message: str, *, auto_fixed: bool = True) -> StandardsAction:
    r = rule(rule_id)
    return StandardsAction(
        rule_id=str(rule_id),
        tier=r.tier,
        message=message,
        auto_fixed=auto_fixed,
        source_url=r.source_url,
    )


# palette.SHAPE_CYCLE names -> matplotlib marker codes (shape encodes group redundantly to colour)
_MPL_MARKER = {
    "circle": "o",
    "square": "s",
    "triangle": "^",
    "diamond": "D",
    "cross": "X",
    "star": "*",
    "hexagon": "h",
    "wye": "v",
}


def select_geom(n: int) -> str:
    if n <= 10:
        return "dots"
    if n <= 50:
        return "box_points"
    return "violin_box"


def point_alpha(n: int) -> float:
    return float(np.clip(1000.0 / max(n, 1), 0.3, 0.9))


def _draw_distribution(ax, request: PlotRequest, style: StyleSpec, palette, rng) -> list:
    """Draw one distribution request onto ``ax`` (no ylabel/title — the caller owns those).

    Shared by the single-figure builder and the shared-axis panel builder, so a panel and a
    standalone plot enforce identical distribution rigor. Returns the standards actions.
    """
    actions: list[StandardsAction] = []
    groups = list(request.groups.items())
    superplot = bool(
        request.replicates and any(len(set(request.replicates.get(g, []))) >= 3 for g, _ in groups)
    )
    if request.force_kind == "bar":
        if not style.is_overridden(RuleId.NO_DYNAMITE):
            raise DynamitePlotError()
        actions.append(
            _action(
                RuleId.NO_DYNAMITE, "Dynamite bar kept (override) — discouraged.", auto_fixed=False
            )
        )

    positions = list(range(1, len(groups) + 1))
    pos = {name: x for x, (name, _) in zip(positions, groups, strict=False)}
    arrs = {name: np.asarray(values, dtype=float) for name, values in groups}
    for x, (name, _values) in zip(positions, groups, strict=False):
        arr = arrs[name]
        color = palette.assign(name).color
        if request.force_kind == "bar":
            self_bar(ax, x, arr, color)
            continue
        if superplot:
            self_superplot(ax, x, arr, request.replicates.get(name, []), rng)
        else:
            self_geom(ax, x, arr, color, rng)

    comparisons: list[Comparison] = []
    if request.annotate_stats and request.force_kind != "bar" and len(groups) >= 2:
        comparisons = _sig_brackets(ax, pos, arrs, _comparison_pairs(request), request)

    ax.set_xticks(positions)
    labels = [g for g, _ in groups]
    if request.annotate_n:
        labels = [f"{g}\n(n={len(arrs[g])})" for g in labels]
    ax.set_xticklabels(labels)
    if request.xlabel:
        ax.set_xlabel(request.xlabel)

    if superplot:
        actions.append(_action(RuleId.SUPERPLOT, "Nested replicates rendered as a SuperPlot."))
    elif request.force_kind != "bar":
        sizes = {select_geom(len(v)) for _, v in groups}
        actions.append(
            _action(RuleId.DISTRIBUTION_GEOM, f"Geometry by sample size: {sorted(sizes)}.")
        )
        ns = [len(v) for _, v in groups]
        actions.append(
            _action(RuleId.OVERPLOT_ALPHA, f"Point alpha for n in {min(ns)}..{max(ns)}.")
        )
    for cmp in comparisons:
        actions.append(_action(RuleId.STAT_REPORTING, cmp.annotation))
    return actions


def build_distribution_svg(
    request: PlotRequest, style: StyleSpec, palette: PaletteRegistry
) -> tuple[str, list[StandardsAction]]:
    """Render a compliant distribution plot. Returns (svg, standards actions)."""
    rng = np.random.default_rng(0)
    with plt.rc_context(mpl_rcparams(style)):
        fig, ax = plt.subplots(figsize=(max(3.0, 1.3 * len(request.groups) + 1), 3.2))
        actions = _draw_distribution(ax, request, style, palette, rng)
        ax.set_ylabel(request.ylabel)
        if request.title:
            ax.set_title(request.title)
        buf = io.StringIO()
        fig.savefig(buf, format="svg")
        plt.close(fig)
    return buf.getvalue(), actions


def build_distribution_panels_svg(
    requests: list[PlotRequest],
    style: StyleSpec,
    palette: PaletteRegistry,
    *,
    shared_y: bool = True,
) -> tuple[str, list[StandardsAction]]:
    """Tile distribution plots as subplots that **share a y-axis** with one **shared legend**.

    The natural multi-panel for the lab's box/violin-across-conditions figures: a common
    y-scale makes panels directly comparable, the group→colour legend is drawn once, and the
    shared PaletteRegistry keeps each group's colour stable across panels. Returns (svg,
    deduplicated standards actions). Panel letters (A, B, C…) are added per subplot.
    """
    from matplotlib.lines import Line2D

    rng = np.random.default_rng(0)
    n = len(requests)
    widths = [max(2.2, 1.0 * len(r.groups) + 0.8) for r in requests]
    actions: list[StandardsAction] = []
    with plt.rc_context(mpl_rcparams(style)):
        fig, axes = plt.subplots(
            1, n, figsize=(sum(widths), 3.4), sharey=shared_y,
            gridspec_kw={"width_ratios": widths},
        )
        axes = list(np.atleast_1d(axes))
        letter_pt = style.preset.default_font_pt + 5
        for i, (ax, req) in enumerate(zip(axes, requests, strict=False)):
            actions += _draw_distribution(ax, req, style, palette, rng)
            ax.set_title(chr(ord("A") + i), loc="left", fontweight="bold", fontsize=letter_pt)
            if req.title:
                ax.set_title(req.title, loc="center")
        axes[0].set_ylabel(requests[0].ylabel)

        names: list[str] = []
        for r in requests:
            for g in r.groups:
                if g not in names:
                    names.append(g)
        if len(names) >= 2:
            handles = [
                Line2D(
                    [0], [0], marker=_MPL_MARKER.get(palette.assign(g).shape, "o"),
                    linestyle="", color=palette.assign(g).color, label=g,
                )
                for g in names
            ]
            fig.legend(
                handles=handles, loc="lower center", ncol=min(len(names), 5),
                frameon=False, bbox_to_anchor=(0.5, -0.04),
            )
        fig.tight_layout()
        buf = io.StringIO()
        fig.savefig(buf, format="svg", bbox_inches="tight")
        plt.close(fig)

    # dedup the per-panel actions (geom/overplot repeat across panels) for a clean manifest
    seen, deduped = set(), []
    for a in actions:
        key = (a.rule_id, a.message)
        if key not in seen:
            seen.add(key)
            deduped.append(a)
    return buf.getvalue(), deduped


# -- significance brackets --------------------------------------------------- #
def _comparison_pairs(request: PlotRequest) -> list[tuple[str, str]]:
    """Pairs to bracket: the explicit ``comparisons``, else every adjacent pair."""
    if request.comparisons:
        return [(c[0], c[1]) for c in request.comparisons if len(c) >= 2]
    names = list(request.groups.keys())
    return list(zip(names, names[1:], strict=False))


def _sig_brackets(ax, pos, arrs, pairs, request: PlotRequest) -> list[Comparison]:
    """Draw stacked significance brackets (stars on the plot) and return the tests run.

    Stars go on the figure; exact p, n and effect size travel in the returned Comparisons so
    the legend can report them (STAT_REPORTING) — asterisks alone are not sufficient.
    """
    results: list[Comparison] = []
    ymax = max(float(np.max(v)) for v in arrs.values())
    ymin = min(float(np.min(v)) for v in arrs.values())
    span = (ymax - ymin) or 1.0
    tick, step = 0.05 * span, 0.13 * span
    level = ymax + 0.08 * span
    drawn = 0
    for a, b in pairs:
        if a not in pos or b not in pos:
            continue
        cmp = replace(
            compare(arrs[a], arrs[b], paired=request.paired, parametric=request.parametric),
            a=a,
            b=b,
        )
        results.append(cmp)
        x1, x2 = pos[a], pos[b]
        y = level + drawn * step
        ax.plot([x1, x1, x2, x2], [y, y + tick, y + tick, y], color="#333333", lw=1.0, zorder=6)
        ax.text(
            (x1 + x2) / 2, y + tick, cmp.stars, ha="center", va="bottom", color="#333333", zorder=6
        )
        drawn += 1
    if drawn:
        ax.set_ylim(top=level + drawn * step + 0.12 * span)
    return results


# -- scatter / correlation --------------------------------------------------- #
def build_scatter_svg(
    request: ScatterRequest, style: StyleSpec, palette: PaletteRegistry
) -> tuple[str, list[StandardsAction]]:
    """Render a scatter plot with an optional OLS fit + 95% band and Pearson r/p/n.

    Points are coloured by ``groups`` (stable house palette) when given; the correlation and
    fit are computed on all points together. Returns (svg, standards actions).
    """
    actions: list[StandardsAction] = []
    x = np.asarray(request.x, dtype=float)
    y = np.asarray(request.y, dtype=float)
    n = int(min(x.size, y.size))
    x, y = x[:n], y[:n]
    alpha = point_alpha(n)

    with plt.rc_context(mpl_rcparams(style)):
        fig, ax = plt.subplots(figsize=(3.6, 3.4))
        if request.groups:
            labels = list(request.groups[:n])
            names = list(dict.fromkeys(labels))  # stable first-seen order
            for name in names:
                gstyle = palette.assign(name)
                idx = [i for i, g in enumerate(labels) if g == name]
                ax.scatter(
                    x[idx], y[idx], s=26, color=gstyle.color, alpha=alpha,
                    marker=_MPL_MARKER.get(gstyle.shape, "o"), edgecolors="none",
                    zorder=3, label=name,
                )
            ax.legend(frameon=False, loc="best")
            if len(names) >= 2:
                # Redundant encoding (colour + marker shape) so groups separate under CVD.
                actions.append(
                    _action(
                        RuleId.GROUP_SHAPE,
                        f"{len(names)} groups encoded by colour + marker shape (CVD-safe).",
                    )
                )
        else:
            color = palette.assign("data").color
            ax.scatter(x, y, s=26, color=color, alpha=alpha, edgecolors="none", zorder=3)

        if request.fit == "linear" and n >= 3:
            fit = linfit(x, y)
            ax.fill_between(fit.xs, fit.lo, fit.hi, color="#999999", alpha=0.20, zorder=1, lw=0)
            ax.plot(fit.xs, fit.ys, color="#333333", lw=1.4, zorder=4)
            if request.annotate_stats:
                ax.text(
                    0.04, 0.96, fit.annotation, transform=ax.transAxes, va="top", ha="left",
                    zorder=6, color="#222222",
                )
            actions.append(_action(RuleId.STAT_REPORTING, f"OLS fit: {fit.annotation}."))

        ax.set_xlabel(request.xlabel)
        ax.set_ylabel(request.ylabel)
        if request.title:
            ax.set_title(request.title)
        actions.append(_action(RuleId.OVERPLOT_ALPHA, f"Point alpha {alpha:.2f} for n={n}."))

        buf = io.StringIO()
        fig.savefig(buf, format="svg")
        plt.close(fig)

    return buf.getvalue(), actions


# -- per-group drawing ------------------------------------------------------- #
def self_geom(ax, x, arr, color, rng) -> None:
    geom = select_geom(len(arr))
    alpha = point_alpha(len(arr))
    if geom == "dots":
        jitter = x + rng.uniform(-0.12, 0.12, len(arr))
        ax.scatter(jitter, arr, s=22, color=color, alpha=alpha, edgecolors="none", zorder=3)
        ax.hlines(arr.mean(), x - 0.2, x + 0.2, color="#333333", lw=1.5, zorder=4)
    elif geom == "box_points":
        _box(ax, x, arr, color)
        jitter = x + rng.uniform(-0.10, 0.10, len(arr))
        ax.scatter(jitter, arr, s=10, color=color, alpha=alpha, edgecolors="none", zorder=3)
    else:  # violin_box
        parts = ax.violinplot([arr], positions=[x], showextrema=False, widths=0.7)
        for body in parts["bodies"]:
            body.set_facecolor(color)
            body.set_alpha(0.25)
            body.set_edgecolor(color)
        _box(ax, x, arr, color, width=0.12)


def self_superplot(ax, x, arr, reps, rng) -> None:
    rep_ids = sorted(set(reps))
    rep_palette = PaletteRegistry()
    means = []
    for rid in rep_ids:
        idx = [i for i, r in enumerate(reps) if r == rid]
        vals = arr[idx]
        c = rep_palette.assign(rid).color
        jitter = x + rng.uniform(-0.12, 0.12, len(vals))
        ax.scatter(jitter, vals, s=14, color=c, alpha=0.5, edgecolors="none", zorder=2)
        means.append(vals.mean())
    ax.scatter(
        [x] * len(means),
        means,
        s=70,
        color="#333333",
        marker="D",
        zorder=5,
        edgecolors="white",
        linewidths=0.5,
    )


def self_bar(ax, x, arr, color) -> None:
    mean = arr.mean()
    sem = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else 0.0
    ax.bar(x, mean, width=0.6, color=color, yerr=sem, capsize=3, edgecolor="#333333")


def _box(ax, x, arr, color, width=0.5) -> None:
    bp = ax.boxplot(
        [arr], positions=[x], widths=width, showfliers=False, patch_artist=True, zorder=2
    )
    for patch in bp["boxes"]:
        patch.set_facecolor("#FFFFFF")
        patch.set_edgecolor(color)
    for el in ("whiskers", "caps", "medians"):
        for line in bp[el]:
            line.set_color(color)
