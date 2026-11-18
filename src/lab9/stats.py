"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

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
    # TODO M4
    raise NotImplementedError


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    # TODO M6
    raise NotImplementedError


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    # TODO M6
    raise NotImplementedError
