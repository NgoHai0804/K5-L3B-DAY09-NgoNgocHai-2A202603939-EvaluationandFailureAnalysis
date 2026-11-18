"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from math import comb

import numpy as np
from scipy import stats as scipy_stats

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(values: Sequence[str]) -> list[str]:
    return [str(v).strip().upper() for v in values]


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    h, j = _norm(human), _norm(judge)
    tp = fp = fn = tn = 0
    for human_label, judge_label in zip(h, j):
        if judge_label == POS:          # judge predicted a failure
            if human_label == POS:
                tp += 1
            else:
                fp += 1
        else:                            # judge predicted PASS
            if human_label == POS:
                fn += 1
            else:
                tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    # precision = tp/(tp+fp), recall = tp/(tp+fn); 0.0 when the denominator is 0
    cm = confusion(human, judge)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    h, j = _norm(human), _norm(judge)
    n = len(h)
    if n == 0 or n != len(j):
        raise ValueError("human and judge must be non-empty and the same length")
    observed = sum(1 for a, b in zip(h, j) if a == b) / n
    hc, jc = Counter(h), Counter(j)
    expected = sum((hc[label] / n) * (jc.get(label, 0) / n) for label in hc)
    if expected >= 1.0:                 # both raters used a single, identical label
        raise ValueError("kappa undefined: p_e == 1 (constant judge)")
    return (observed - expected) / (1 - expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    # (p_obs + spec - 1) / (sens + spec - 1)
    denominator = sensitivity + specificity - 1
    if denominator == 0:                # judge carries no information; fall back to 0
        return 0.0
    corrected = (observed_rate + specificity - 1) / denominator
    return max(0.0, min(1.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if x.shape != y.shape:
        raise ValueError("paired samples must have the same shape")
    if x.size == 0:
        return 0.0, 0.0, 0.0
    diff = x - y
    if np.all(diff == 0):
        return 0.0, 0.0, 0.0
    result = scipy_stats.bootstrap(
        (x, y),
        statistic=lambda xr, yr: np.mean(xr - yr),
        vectorized=False,
        paired=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    return (float(np.mean(diff)),
            float(result.confidence_interval.low),
            float(result.confidence_interval.high))


def _check_nck(n: int, c: int, k: int) -> None:
    if n < 0 or c < 0 or c > n or k < 1 or k > n:
        raise ValueError(f"invalid (n, c, k) = ({n}, {c}, {k})")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    if k > n - c:                       # not enough failing trials to draw an all-fail set
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    if k > c:                           # fewer than k passing trials -> impossible to draw k
        return 0.0
    return comb(c, k) / comb(n, k)
