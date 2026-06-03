"""Server-side SGP4 propagation and coordinate transforms (authoritative).

The Python engine is the single source of truth for any position used in
screening / analysis / alerting (dev-plan §4.2). The browser's satellite.js is
display-only. To keep the two reconcilable, the transforms here mirror
satellite.js (same GMST polynomial, same WGS-84 iterative geodetic solution),
and both sides propagate the *same* TLE lines.
"""
