"""A module providing selection strategies for the Kaczmarz algorithm."""

from collections import deque

import numpy as np

import kaczmarz


class Cyclic(kaczmarz.Base):
    """Cycle through the equations of the system in order, repeatedly.

    References
    ----------
    1. S. Kaczmarz.
       "Angenäherte Auflösung von Systemen linearer Gleichungen."
       *Bulletin International de l’Académie Polonaise
       des Sciences et des Lettres.
       Classe des Sciences Mathématiques et Naturelles.
       Série A, Sciences Mathématiques*, 35, 335–357, 1937
    """

    def __init__(self, *base_args, **base_kwargs):
        super().__init__(*base_args, **base_kwargs)
        self._row_index = -1

    def _select_row_index(self, xk):
        self._row_index = (1 + self._row_index) % self._n_rows
        return self._row_index


class MaxDistance(kaczmarz.Base):
    """Choose equations which leads to the most progress.

    This selection strategy is also known as `Motzkin's method`.

    References
    ----------
    1. T. S. Motzkin and I. J. Schoenberg.
       "The relaxation method for linear inequalities."
       *Canadian Journal of Mathematics*, 6:393–404, 1954.
    """

    def _select_row_index(self, xk):
        # TODO: use auxiliary update for the residual.
        residual = self._b - self._A @ self._xk
        return np.argmax(np.abs(residual))


class Lookahead(kaczmarz.Base):
    """Choose equations which leads to the most progress after a 2 step lookahead
    """

    def __init__(self, *base_args, **base_kwargs):
        super().__init__(*base_args, **base_kwargs)
        self._next_i = None

    def _select_row_index(self, xk):
        if self._next_i is not None:
            temp = self._next_i
            self._next_i = None
            return temp
        best_i = -1
        self._next_i = -1
        best_residual_norms = (float("inf"), float("inf"))
        for ik in range(self._n_rows):
            next_xk = self._update_iterate(self._xk, ik)
            residual = self._b - self._A @ next_xk
            ik2 = np.argmax(np.abs(residual))
            next_next_xk = self._update_iterate(next_xk, ik2)
            next_residual_norm = np.linalg.norm(self._b - self._A @ next_next_xk)
            residual_norms = (next_residual_norm, np.linalg.norm(residual))
            if residual_norms < best_residual_norms:
                best_i = ik
                self._next_i = ik2
                best_residual_norms = residual_norms
        return best_i


class Random(kaczmarz.Base):
    """Sample equations according to a `fixed` probability distribution.

    Parameters
    ----------
    p : (m,) array_like, optional
        Sampling probability for each equation. Uniform by default.
    """

    def __init__(self, *base_args, p=None, **base_kwargs):
        super().__init__(*base_args, **base_kwargs)
        self._p = p  # p=None corresponds to uniform.

    def _select_row_index(self, xk):
        return np.random.choice(self._n_rows, p=self._p)


class SVRandom(Random):
    """Sample equations with probability proportional to the squared row norms.

    References
    ----------
    1. T. Strohmer and R. Vershynin,
       "A Randomized Kaczmarz Algorithm with Exponential Convergence."
       Journal of Fourier Analysis and Applications 15, 262 2009.
    """

    def __init__(self, *base_args, **base_kwargs):
        super().__init__(*base_args, **base_kwargs)
        squared_row_norms = self._row_norms ** 2
        self._p = squared_row_norms / squared_row_norms.sum()


class UniformRandom(Random):
    """Sample equations uniformly at random."""

    # Nothing to do since uniform sampling is the default behavior of Random.


class Quantile(Random):
    """Reject equations whose normalized residual is above a quantile.

    This algorithm is intended for use in solving corrupted systems of equations.
    That is, systems where a subset of the equations are consistent,
    while a minority of the equations are not.
    Such systems are almost always overdetermined.

    Parameters
    ----------
    quantile : float, optional
        Quantile of normalized residual above which to reject.

    References
    ----------
    1. There will be a reference soon. Keep an eye out for that.
    """

    def __init__(self, *args, quantile=1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._quantile = quantile

    def _distance(self, xk, ik):
        return np.abs(self._b[ik] - self._A[ik] @ xk)

    def _threshold_distances(self, xk):
        return np.abs(self._b - self._A @ xk)

    def _threshold(self, xk):
        distances = self._threshold_distances(xk)

        return np.quantile(distances, self._quantile)

    def _select_row_index(self, xk):
        ik = super()._select_row_index(xk)

        distance = self._distance(xk, ik)
        threshold = self._threshold(xk)

        if distance < threshold or np.isclose(distance, threshold):
            return ik

        return -1  # No projection please


class SampledQuantile(Quantile):
    """Reject equations whose normalized residual is above a quantile of a random subset of residual entries.

    Parameters
    ----------
    n_samples: int, optional
        Number of normalized residual samples used to compute the threshold quantile.

    References
    ----------
    1. There will be a reference soon. Keep an eye out for that.
    """

    def __init__(self, *args, n_samples=None, **kwargs):
        super().__init__(*args, **kwargs)
        if n_samples is None:
            n_samples = self._n_rows
        self._n_samples = n_samples

    def _threshold_distances(self, xk):
        idxs = np.random.choice(self._n_rows, self._n_samples, replace=False)
        return np.abs(self._b[idxs] - self._A[idxs] @ xk)


class WindowedQuantile(Quantile):
    """Reject equations whose normalized residual is above a quantile of the most recent normalized residual values.

    Parameters
    ----------
    window_size : int, optional
        Number of recent normalized residual values used to compute the threshold quantile.

    Note
    ----
    ``WindowedQuantile`` also accepts the parameters of ``Quantile``.

    References
    ----------
    1. There will be a reference soon. Keep an eye out for that.
    """

    def __init__(self, *args, window_size=None, **kwargs):
        super().__init__(*args, **kwargs)
        if window_size is None:
            window_size = self._n_rows
        self._window = deque([], maxlen=window_size)

    def _distance(self, xk, ik):
        distance = super()._distance(xk, ik)
        self._window.append(distance)
        return distance

    def _threshold_distances(self, xk):
        return self._window


class RandomOrthoGraph(kaczmarz.Base):
    """Try to only sample equations which are not already satisfied.

    Use the orthogonality graph defined in [1] to decide which rows should
    be considered "selectable" at each iteration.

    Parameters
    ----------
    p : (m,) array_like, optional
        Sampling probability for each equation. Uniform by default.
        These probabilities will be re-normalized based on the selectable rows
        at each iteration.

    References
    ----------
    1. Nutini, Julie, et al.
       "Convergence rates for greedy Kaczmarz algorithms,
       and faster randomized Kaczmarz rules using the orthogonality graph."
       arXiv preprint arXiv:1612.07838 2016.
    """

    def __init__(self, *args, p=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._ortho_graph = self._A @ self._A.T

        self._i_to_newly_selectable = {
            i: self._newly_selectable(i) for i in range(self._n_rows)
        }

        self._selectable = np.argwhere(self._A @ self._x0 - self._b).flatten()
        if p is None:
            p = np.ones((self._n_rows,))
        self._p = p

    def _newly_selectable(self, i):
        return np.argwhere(self._ortho_graph[i, :])

    def _update_selectable(self, ik):
        # Every time a row is selected, all of its neighbors become selectable, and itself becomes unselectable.
        newly_selectable = self._i_to_newly_selectable[ik]
        selectable_with_ik = np.union1d(self._selectable, newly_selectable)
        self._selectable = np.setdiff1d(selectable_with_ik, [ik], assume_unique=True)

    def _select_row_index(self, xk):
        unnormalized_p = self._p[self._selectable]
        p = unnormalized_p / unnormalized_p.sum()
        ik = np.random.choice(self._selectable, p=p)
        self._update_selectable(ik)
        return ik
