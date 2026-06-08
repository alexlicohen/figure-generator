"""Lightweight inferential statistics for data plots.

Scatter/correlation and group-comparison annotations need exact p-values and effect sizes,
not just asterisks — reporting both is the publication standard (see ``RuleId.STAT_REPORTING``).
These helpers are pure (numpy + scipy) and return plain dataclasses so the generator stays a
thin drawing layer. scipy is an optional ``plots`` extra, imported lazily alongside matplotlib.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Fit:
    """An ordinary-least-squares line with a Pearson correlation and a 95% mean-response band."""

    slope: float
    intercept: float
    r: float
    p: float
    n: int
    xs: np.ndarray  # grid for the fitted line / CI band
    ys: np.ndarray  # fitted line over xs
    lo: np.ndarray  # lower 95% CI of the mean response over xs
    hi: np.ndarray  # upper 95% CI of the mean response over xs

    @property
    def annotation(self) -> str:
        """Compact, paste-ready stats string: ``r = .42, p = .003, n = 88``."""
        return f"r = {_fmt_coef(self.r)}, {fmt_p(self.p)}, n = {self.n}"


@dataclass(frozen=True)
class Comparison:
    """A two-group test with an effect size, for a significance bracket."""

    a: str
    b: str
    stat: float
    p: float
    test: str  # "Welch t" | "paired t" | "Mann-Whitney U"
    effect_name: str  # "Cohen's d" | "Hedges' g" | "rank-biserial r"
    effect: float
    n_a: int
    n_b: int

    @property
    def stars(self) -> str:
        return p_to_stars(self.p)

    @property
    def annotation(self) -> str:
        """Paste-ready: ``control vs ADHD: Welch t = 3.1, p = .004, Cohen's d = 0.82``."""
        return (
            f"{self.a} vs {self.b}: {self.test} = {self.stat:.2g}, "
            f"{fmt_p(self.p)}, {self.effect_name} = {self.effect:.2g}"
        )


def linfit(x, y, *, grid: int = 100) -> Fit:
    """Ordinary least-squares fit with Pearson r/p and a 95% CI band on the mean response."""
    from scipy import stats

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = int(x.size)
    res = stats.linregress(x, y)
    xs = np.linspace(float(x.min()), float(x.max()), grid)
    ys = res.slope * xs + res.intercept
    # 95% confidence band for the mean response: t * s * sqrt(1/n + (x0-xbar)^2 / Sxx)
    xbar = x.mean()
    sxx = float(np.sum((x - xbar) ** 2)) or 1.0
    dof = max(n - 2, 1)
    resid = y - (res.slope * x + res.intercept)
    s = float(np.sqrt(np.sum(resid**2) / dof))
    tcrit = float(stats.t.ppf(0.975, dof))
    se = s * np.sqrt(1.0 / n + (xs - xbar) ** 2 / sxx)
    band = tcrit * se
    return Fit(
        slope=float(res.slope),
        intercept=float(res.intercept),
        r=float(res.rvalue),
        p=float(res.pvalue),
        n=n,
        xs=xs,
        ys=ys,
        lo=ys - band,
        hi=ys + band,
    )


def compare(a, b, *, paired: bool = False, parametric: bool = True) -> Comparison:
    """Two-group comparison with a matched effect size.

    Parametric → Welch's (or paired) t-test + Cohen's d / Hedges' g. Non-parametric →
    Mann-Whitney U + rank-biserial r. Defaults to the parametric path; callers can switch.
    """
    from scipy import stats

    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = int(a.size), int(b.size)
    if not parametric:
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        rb = 1.0 - 2.0 * float(u) / (na * nb) if na and nb else 0.0
        return Comparison(
            "", "", float(u), float(p), "Mann-Whitney U", "rank-biserial r", abs(rb), na, nb
        )
    if paired:
        m = min(na, nb)
        t, p = stats.ttest_rel(a[:m], b[:m])
        diff = a[:m] - b[:m]
        sd = float(diff.std(ddof=1)) or 1.0
        d = float(diff.mean()) / sd
        return Comparison("", "", float(t), float(p), "paired t", "Cohen's d", abs(d), na, nb)
    t, p = stats.ttest_ind(a, b, equal_var=False)
    d, name = _cohens_d(a, b)
    return Comparison("", "", float(t), float(p), "Welch t", name, abs(d), na, nb)


def _cohens_d(a, b) -> tuple[float, str]:
    """Cohen's d with the small-sample Hedges' g correction (renamed when applied)."""
    na, nb = a.size, b.size
    pooled = np.sqrt(
        ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / max(na + nb - 2, 1)
    )
    d = float(a.mean() - b.mean()) / (float(pooled) or 1.0)
    dof = na + nb - 2
    if dof < 50:  # small-sample bias correction
        g = d * (1 - 3 / (4 * dof - 1))
        return g, "Hedges' g"
    return d, "Cohen's d"


def p_to_stars(p: float) -> str:
    """GraphPad/Nature convention: ns / * / ** / *** / ****."""
    if p < 1e-4:
        return "****"
    if p < 1e-3:
        return "***"
    if p < 1e-2:
        return "**"
    if p < 5e-2:
        return "*"
    return "ns"


def fmt_p(p: float) -> str:
    """APA-style exact p: ``p < .001`` below the floor, else ``p = .034`` (no leading zero)."""
    if p < 1e-3:
        return "p < .001"
    return f"p = {format(p, '.3f').lstrip('0')}"


def _fmt_coef(r: float) -> str:
    """Correlation coefficient without a leading zero (``.42``, ``-.07``)."""
    s = f"{r:.2f}"
    return s.replace("0.", ".").replace("-0.", "-.")
