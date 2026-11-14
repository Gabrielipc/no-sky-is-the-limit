"""Instrument-independent CRISM summary parameters (audit 2026-11-14, section 1.2, priority 6).

One operator for every body: given a reflectance cube and its band centres, compute the
CRISM summary parameters exactly as the CRISM Analysis Toolkit (CAT) does, so CRISM (Mars),
EMIT L2A (Earth) and Chandrayaan-1 M3 (Moon) share magnitude, threshold and denominator.

Source of the formulas: "CRISM Summary Parameter Calculation Reference", PDS Geosciences
Node (J. Christian, July 2026), https://pds-geosciences.wustl.edu/missions/mro/crism_summary_parameter_reference.pdf,
which reproduces Viviano et al. (2014, doi:10.1002/2014JE004627) with the later CAT adjustments.

Hyperspectral formulation (section 2 of the reference):
- R_lambda: median of a window of k bands centred on the band nearest to lambda (an even k
  becomes k + 1; the window is truncated at the detector edge; invalid bands are ignored and
  an even count takes the mean of the two middle values, i.e. numpy's median).
- RC_lambda: straight line between the anchors using the actual band wavelengths W:
  a = (W_C - W_L) / (W_H - W_L), b = 1 - a, RC = b R_L + a R_H (extrapolates outside the anchors).
- RB_lambda = 1 - R_lambda / RC_lambda.

Kernel widths are defined in channels of CRISM's ~6.55 nm sampling. `Cube(kernel_mode='channels')`
applies them literally (CRISM). `kernel_mode='nm'` keeps the same physical window for another
instrument: the bands whose centres lie within +-k x 6.55 / 2 nm of the band nearest to lambda
(at least that band). For CRISM's 6.5 nm spacing both modes select the same k bands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import warnings

import numpy as np

CRISM_SAMPLING_NM = 6.55
DEFAULT_KERNEL = 5


@dataclass(frozen=True)
class Term:
    wavelength: float
    kernel: int = DEFAULT_KERNEL


@dataclass(frozen=True)
class Param:
    """A summary parameter.

    kind:
      'rb'      1 - R_c / RC_c with anchors (low, high)
      'wsum'    sum of weight * RB over `terms` with shared anchors (indices; OLINDEX3 extrapolates)
      'min_rb'  min of two band depths, each with its own anchors (`pairs`)
      'ratio'   1 - (sum R/RC over `terms`) / (scale * sum R/RC over `ref_terms`) with shared anchors
      'avg_rb'  mean of RB over `terms` with shared anchors (BD1900_2)
    """
    name: str
    kind: str
    low: Term | None = None
    high: Term | None = None
    terms: tuple[Term, ...] = ()
    weights: tuple[float, ...] = ()
    ref_terms: tuple[Term, ...] = ()
    scale: float = 1.0
    pairs: tuple[tuple[Term, Term, Term], ...] = field(default_factory=tuple)


T = Term
# Definitions transcribed from the CAT reference (hyperspectral column). Only the parameters
# used by the six absorption complexes of `contrato-comun-superficie-v1`, plus BD1900_2 and BD920_2.
PARAMS: dict[str, Param] = {
    'BD530_2': Param('BD530_2', 'rb', T(440), T(614), (T(530),)),
    'BD860_2': Param('BD860_2', 'rb', T(755), T(977), (T(860),)),
    # Fe2+ 0.92 um (pyroxene) from VNIR only: the one mafic parameter EMIT sees through the atmosphere.
    'BD920_2': Param('BD920_2', 'rb', T(807), T(984), (T(920),)),
    'OLINDEX3': Param('OLINDEX3', 'wsum', T(1750, 7), T(1862, 7),
                      (T(1210, 7), T(1250, 7), T(1263, 7), T(1276, 7), T(1330, 7)),
                      (0.1, 0.1, 0.2, 0.2, 0.4)),
    'LCPINDEX2': Param('LCPINDEX2', 'wsum', T(1560, 7), T(2450, 7),
                       (T(1690, 7), T(1750, 7), T(1810, 7), T(1870, 7)), (0.2, 0.2, 0.3, 0.3)),
    # Weights as printed in the July 2026 reference (they sum to 1.1).
    'HCPINDEX2': Param('HCPINDEX2', 'wsum', T(1690, 7), T(2530, 7),
                       (T(2120, 5), T(2140, 7), T(2230, 7), T(2250, 7), T(2430, 7), T(2460, 7)),
                       (0.1, 0.2, 0.15, 0.3, 0.2, 0.15)),
    'BD1900_2': Param('BD1900_2', 'avg_rb', T(1850), T(2067), (T(1930), T(1985))),
    'BD1900R2': Param('BD1900R2', 'ratio', T(1815), T(2132),
                      tuple(T(w, 1) for w in (1908, 1914, 1921, 1928, 1934, 1941)),
                      ref_terms=tuple(T(w, 1) for w in (1862, 1869, 1875, 2112, 2120, 2126))),
    'D2200': Param('D2200', 'ratio', T(1815, 7), T(2430, 7), (T(2210, 7), T(2230, 7)),
                   ref_terms=(T(2165, 5),), scale=2.0),
    'BD2210_2': Param('BD2210_2', 'rb', T(2165), T(2290), (T(2210),)),
    'BD2265': Param('BD2265', 'rb', T(2120), T(2340), (T(2265, 3),)),
    'BD2290': Param('BD2290', 'rb', T(2250), T(2350), (T(2290),)),
    'D2300': Param('D2300', 'ratio', T(1815), T(2530), (T(2290, 3), T(2320, 3), T(2330, 3)),
                   ref_terms=(T(2120), T(2170), T(2210))),
    'MIN2295_2480': Param('MIN2295_2480', 'min_rb', pairs=(
        (T(2165), T(2295), T(2364)),
        (T(2364), T(2480), T(2570)),
    )),
    'BD2500_2': Param('BD2500_2', 'rb', T(2364), T(2570), (T(2480),)),
}


class Cube:
    """Reflectance cube (bands, rows, cols) with band centres in nm; invalid values are NaN."""

    def __init__(self, data: np.ndarray, wavelengths_nm, kernel_mode: str = 'channels'):
        self.data = np.asarray(data, dtype='float64')
        self.wl = np.asarray(wavelengths_nm, dtype='float64')
        if self.data.shape[0] != self.wl.size:
            raise ValueError('El número de bandas no coincide con las longitudes de onda')
        if np.any(np.diff(self.wl) <= 0):
            raise ValueError('Las longitudes de onda deben ser crecientes')
        if kernel_mode not in ('channels', 'nm'):
            raise ValueError('kernel_mode debe ser channels o nm')
        self.kernel_mode = kernel_mode
        self._cache: dict[tuple[float, int], np.ndarray] = {}

    def index(self, wavelength: float) -> int:
        return int(np.argmin(np.abs(self.wl - wavelength)))

    def W(self, wavelength: float) -> float:
        return float(self.wl[self.index(wavelength)])

    def covers(self, wavelength: float, tolerance_nm: float) -> bool:
        return abs(self.W(wavelength) - wavelength) <= tolerance_nm

    def window(self, term: Term) -> tuple[int, int]:
        """Band index range [lo, hi) of the median window of `term`."""
        i = self.index(term.wavelength)
        k = term.kernel + 1 if term.kernel % 2 == 0 else term.kernel
        if self.kernel_mode == 'channels':
            return max(0, i - k // 2), min(self.wl.size, i + k // 2 + 1)
        half_nm = k * CRISM_SAMPLING_NM / 2
        inside = np.nonzero(np.abs(self.wl - self.wl[i]) <= half_nm)[0]
        return int(inside.min()), int(inside.max()) + 1

    def R(self, term: Term) -> np.ndarray:
        key = (term.wavelength, term.kernel)
        if key not in self._cache:
            lo, hi = self.window(term)
            window = self.data[lo:hi]
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)  # all-NaN windows stay NaN
                self._cache[key] = np.nanmedian(window, axis=0)
        return self._cache[key]

    def RC(self, centre: Term, low: Term, high: Term) -> np.ndarray:
        wl, wc, wh = self.W(low.wavelength), self.W(centre.wavelength), self.W(high.wavelength)
        a = (wc - wl) / (wh - wl)
        return (1.0 - a) * self.R(low) + a * self.R(high)

    def RB(self, centre: Term, low: Term, high: Term) -> np.ndarray:
        with np.errstate(divide='ignore', invalid='ignore'):
            return 1.0 - self.R(centre) / self.RC(centre, low, high)


def compute(cube: Cube, name: str) -> np.ndarray:
    """Parameter `name` for every pixel of `cube`."""
    p = PARAMS[name]
    with np.errstate(divide='ignore', invalid='ignore'):
        if p.kind == 'rb':
            return cube.RB(p.terms[0], p.low, p.high)
        if p.kind == 'wsum':
            return sum(w * cube.RB(t, p.low, p.high) for t, w in zip(p.terms, p.weights))
        if p.kind == 'avg_rb':
            return sum(cube.RB(t, p.low, p.high) for t in p.terms) / len(p.terms)
        if p.kind == 'min_rb':
            return np.minimum(*[cube.RB(c, lo, hi) for lo, c, hi in p.pairs])
        if p.kind == 'ratio':
            num = sum(cube.R(t) / cube.RC(t, p.low, p.high) for t in p.terms)
            den = sum(cube.R(t) / cube.RC(t, p.low, p.high) for t in p.ref_terms)
            return 1.0 - num / (p.scale * den)
    raise ValueError(f'Tipo de parámetro desconocido: {p.kind}')


def required_wavelengths(name: str) -> list[float]:
    p = PARAMS[name]
    terms = [p.low, p.high, *p.terms, *p.ref_terms, *(t for pair in p.pairs for t in pair)]
    return sorted({t.wavelength for t in terms if t is not None})


def covered(cube: Cube, name: str) -> bool:
    """True when every wavelength of `name` is inside the instrument range and has valid bands.

    A wavelength counts when its nearest band is within the local band spacing (so the edges of
    the range do not snap to a distant band) and its median window holds finite data somewhere
    (bands flagged bad, e.g. EMIT water-vapour bands, are NaN).
    """
    spacing = np.gradient(cube.wl)
    p = PARAMS[name]
    for t in [p.low, p.high, *p.terms, *p.ref_terms, *(t for pair in p.pairs for t in pair)]:
        if t is None:
            continue
        i = cube.index(t.wavelength)
        if abs(cube.wl[i] - t.wavelength) > spacing[i] or not np.isfinite(cube.R(t)).any():
            return False
    return True


def required_band_indices(wavelengths_nm, names, kernel_mode: str = 'channels') -> list[int]:
    """Band indices read by `names` (windows included), so a reader can fetch only those bands."""
    cube = Cube(np.zeros((len(wavelengths_nm), 1, 1)), wavelengths_nm, kernel_mode)
    out: set[int] = set()
    for name in names:
        p = PARAMS[name]
        for t in [p.low, p.high, *p.terms, *p.ref_terms, *(t for pair in p.pairs for t in pair)]:
            if t is not None:
                out.update(range(*cube.window(t)))
    return sorted(out)
