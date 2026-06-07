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

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..models import PlotRequest, StandardsAction  # noqa: E402
from ..palette import PaletteRegistry  # noqa: E402
from ..standards.linter import RuleId, rule  # noqa: E402
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


def select_geom(n: int) -> str:
    if n <= 10:
        return "dots"
    if n <= 50:
        return "box_points"
    return "violin_box"


def point_alpha(n: int) -> float:
    return float(np.clip(1000.0 / max(n, 1), 0.3, 0.9))


def build_distribution_svg(
    request: PlotRequest, style: StyleSpec, palette: PaletteRegistry
) -> tuple[str, list[StandardsAction]]:
    """Render a compliant distribution plot. Returns (svg, standards actions)."""
    actions: list[StandardsAction] = []
    groups = list(request.groups.items())
    rng = np.random.default_rng(0)

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

    with plt.rc_context(mpl_rcparams(style)):
        fig, ax = plt.subplots(figsize=(max(3.0, 1.3 * len(groups) + 1), 3.2))
        positions = range(1, len(groups) + 1)

        for x, (name, values) in zip(positions, groups, strict=False):
            arr = np.asarray(values, dtype=float)
            color = palette.assign(name).color
            if request.force_kind == "bar":
                self_bar(ax, x, arr, color)
                continue
            if superplot:
                self_superplot(ax, x, arr, request.replicates.get(name, []), rng)
            else:
                self_geom(ax, x, arr, color, rng)

        ax.set_xticks(list(positions))
        ax.set_xticklabels([g for g, _ in groups])
        ax.set_ylabel(request.ylabel)
        if request.xlabel:
            ax.set_xlabel(request.xlabel)
        if request.title:
            ax.set_title(request.title)

        buf = io.StringIO()
        fig.savefig(buf, format="svg")
        plt.close(fig)

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
