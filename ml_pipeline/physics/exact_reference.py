"""
ml_pipeline.physics.exact_reference
===================================
EXACT analytical reference for the plan-view advection-dispersion problem the
production engine solves with the Domenico (1987) approximation, so that
approximation's error can be MEASURED rather than assumed.

WHY THIS EXISTS
---------------
The whole physics engine -- and therefore every ML training label -- rests on
Domenico's product-form approximation. That approximation has a peer-reviewed
error characterisation the project had never bounded:

    West, M.R., Kueper, B.H. & Ungs, M.J. (2007), "On the Use and Error of
    Approximation in the Domenico (1987) Solution", Ground Water 45(2):126-135.
    Errors range 2-80% depending on parameters; the solution UNDERPREDICTS
    centreline concentrations by as much as 80%. It is exact only at zero
    longitudinal dispersivity, and error grows with dispersivity and time.

`review2.md` finding V-1. This module supplies the exact solution; the sweep in
`ml_pipeline/validation/domenico_error_sweep.py` publishes the envelope.

THE TWO SOLUTIONS, AND EXACTLY WHERE THEY DIFFER
------------------------------------------------
For a continuous strip source of full width W at x = 0, uniform pore velocity v
(already retarded), longitudinal/transverse dispersion D_L = aL*v, D_T = aT*v,
the concentration is a convolution of the 1-D first-passage density with the
transverse spreading at the SAME arrival time tau:

    g(x, tau) = x / sqrt(4*pi*D_L*tau^3) * exp(-(x - v*tau)^2 / (4*D_L*tau))
    T(y, tau) = 1/2 [ erf((y + W/2) / (2*sqrt(D_T*tau)))
                    - erf((y - W/2) / (2*sqrt(D_T*tau))) ]

    EXACT:     C(x,y,t) = C0 * INTEGRAL_0^t  g(x,tau) * T(y,tau) d(tau)
    DOMENICO:  C(x,y,t) = C0 * [INTEGRAL_0^t g(x,tau) d(tau)] * T(y, x/v)

Domenico pulls the transverse factor OUT of the integral and evaluates it at the
single mean advective arrival time tau = x/v. That is the entire approximation.
It is exact when D_T -> 0 (T == 1 inside the strip) and when D_L -> 0 (the
first-passage density collapses to a delta at tau = x/v, so pulling T out is
free). Between those limits it is not, and the error is the quantity West et al.
report.

g is the inverse-Gaussian (Wald) first-passage density for advection-dispersion
[Wexler 1992, USGS TWRI 3-B7; Kreft & Zuber 1978]. Its time-integral reproduces
the Ogata-Banks (1961) 1-D solution exactly, which is the self-check in
`validate_against_ogata_banks()` -- this module is not trusted until that passes.

Deliberately NOT modelled here: matrix diffusion (Tang), the leach-zone disc,
first-order attenuation, and the restoration deficit wave. This is a clean
comparison of the TRANSPORT KERNEL alone. Mixing the overlays in would confound
the very error being measured.
"""
from __future__ import annotations

import numpy as np
from scipy.special import erf, erfc
from scipy.integrate import quad

__all__ = ["exact_concentration", "domenico_concentration",
           "ogata_banks", "validate_against_ogata_banks"]


def ogata_banks(x: float, t: float, v: float, D_L: float) -> float:
    """1-D continuous-source solution [Ogata & Banks 1961], BOTH terms.

    C/C0 = 1/2 erfc[(x - v t)/(2 sqrt(D_L t))]
         + 1/2 exp(v x / D_L) erfc[(x + v t)/(2 sqrt(D_L t))]

    The production engine keeps only the first term (ARCHITECTURE section 10) --
    that omission is a SEPARATE approximation from the Domenico product form and
    is what paints the upstream half-plane at C0.
    """
    if t <= 0.0 or x < 0.0:
        return 0.0
    s = 2.0 * np.sqrt(D_L * t)
    a = 0.5 * erfc((x - v * t) / s)
    # exp(v x / D_L) overflows for large Peclet while erfc underflows; the
    # product is negligible there, so guard rather than let it become inf*0.
    expo = v * x / D_L
    b = 0.0 if expo > 700.0 else 0.5 * np.exp(expo) * erfc((x + v * t) / s)
    return float(a + b)


def _g(tau, x, v, D_L):
    """Inverse-Gaussian first-passage density g(x, tau)."""
    return (x / np.sqrt(4.0 * np.pi * D_L * tau ** 3)
            * np.exp(-((x - v * tau) ** 2) / (4.0 * D_L * tau)))


def _T(tau, y, W, D_T):
    """Transverse strip factor at arrival time tau."""
    s = 2.0 * np.sqrt(D_T * tau)
    return 0.5 * (erf((y + W / 2.0) / s) - erf((y - W / 2.0) / s))


def exact_concentration(x: float, y: float, t: float, *, v: float,
                        D_L: float, D_T: float, W: float,
                        C0: float = 1.0, epsabs: float = 1e-10) -> float:
    """EXACT C(x,y,t)/C0 * C0 by numerical convolution (see module docstring).

    The integrand is sharply peaked around tau ~ x/v, so the quadrature is given
    that point explicitly -- adaptive quadrature on a narrow spike in a wide
    interval silently returns ~0 otherwise.
    """
    if t <= 0.0 or x <= 0.0 or D_L <= 0.0:
        return 0.0
    if D_T <= 0.0:                       # degenerate: no transverse spreading
        return C0 * ogata_banks(x, t, v, D_L) if abs(y) <= W / 2.0 else 0.0

    def integrand(tau):
        if tau <= 0.0:
            return 0.0
        return _g(tau, x, v, D_L) * _T(tau, y, W, D_T)

    peak = max(x / max(v, 1e-12), 1e-9)
    pts = [p for p in (peak * 0.25, peak * 0.5, peak, peak * 2.0, peak * 4.0)
           if 0.0 < p < t]
    val, _ = quad(integrand, 0.0, t, points=pts or None, limit=400,
                  epsabs=epsabs, epsrel=1e-9)
    return float(C0 * max(val, 0.0))


def domenico_concentration(x: float, y: float, t: float, *, v: float,
                           D_L: float, D_T: float, W: float,
                           C0: float = 1.0,
                           second_ob_term: bool = False) -> float:
    """The DOMENICO product form, in the exact convention the production engine
    uses (physics.transport._long_factor / _tran_factor).

    second_ob_term=False reproduces the production engine (first Ogata-Banks
    term only). True isolates the product-decoupling error alone, with the
    dropped-term error removed -- useful for attributing the total.
    """
    if t <= 0.0 or x <= 0.0:
        return 0.0
    Xc = v * t
    if second_ob_term:
        long_f = ogata_banks(x, t, v, D_L)
    else:
        long_f = 0.5 * erfc((x - Xc) / (2.0 * np.sqrt(D_L * t)))
    # transverse factor frozen at the mean advective arrival time tau = x/v,
    # i.e. sqrt(D_T * x/v) == sqrt(aT * x). THIS is the approximation.
    tran_f = _T(max(x, 1e-9) / max(v, 1e-12), y, W, D_T)
    return float(C0 * long_f * tran_f)


def validate_against_ogata_banks(verbose: bool = True) -> bool:
    """SELF-CHECK: as W -> infinity the transverse factor is 1 everywhere on the
    centreline, so the exact convolution must collapse onto Ogata-Banks. If this
    fails the reference is wrong and no error figure derived from it means
    anything."""
    ok = True
    rows = []
    for v, D_L, x, t in ((0.1, 1.0, 50.0, 2000.0), (0.5, 5.0, 200.0, 1000.0),
                         (0.02, 0.5, 10.0, 5000.0), (1.0, 20.0, 500.0, 800.0)):
        ref = ogata_banks(x, t, v, D_L)
        got = exact_concentration(x, 0.0, t, v=v, D_L=D_L, D_T=1e-9,
                                  W=1e9, C0=1.0)
        rel = abs(got - ref) / max(ref, 1e-300)
        ok &= rel < 2e-3
        rows.append((v, D_L, x, t, ref, got, rel))
    if verbose:
        print("SELF-CHECK  exact convolution (W->inf) vs Ogata-Banks")
        print(f"  {'v':>6}{'D_L':>7}{'x':>7}{'t':>8}"
              f"{'Ogata-Banks':>14}{'convolution':>14}{'rel err':>11}")
        for v, D_L, x, t, ref, got, rel in rows:
            print(f"  {v:>6}{D_L:>7}{x:>7}{t:>8}{ref:>14.8f}{got:>14.8f}{rel:>11.2e}")
        print(f"  -> {'PASS' if ok else 'FAIL'}")
    return bool(ok)


if __name__ == "__main__":
    validate_against_ogata_banks()
