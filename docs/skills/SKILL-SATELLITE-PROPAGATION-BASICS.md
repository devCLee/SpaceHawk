## Satellite Propagation Basics

This document summarizes the key concepts needed to parse Two-Line Elements (TLEs), understand orbital elements, propagate orbits, and visualize satellite motion.

---

### TLEs (Two-Line Elements)

**TLEs** are a compact format describing an Earth-orbiting satellite’s orbit at a specific epoch, along with drag and other parameters for the SGP4 propagator.

**Example TLE:**

```text
ISS (ZARYA)
1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993
2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263
```

**Line 1 fields (key ones):**

- **Column 01**: Line number (`1`)
- **Columns 03–07**: Satellite number (`25544`)
- **Column 08**: Classification (`U` = unclassified)
- **Columns 10–17**: International designator (`98067A`)
- **Columns 19–32**: Epoch year and day of year (`24070.51782407`)
  - `24` → 2024
  - `070.51782407` → 70.5178th day of year
- **Columns 34–43**: First time derivative of mean motion (rev/day²)
- **Columns 45–52**: Second derivative of mean motion (rev/day³, in mantissa/exponent form)
- **Columns 54–61**: BSTAR drag term (1/earth radii, mantissa/exponent form)
- **Columns 63**: Ephemeris type (usually `0`)
- **Columns 65–68**: Element set number
- **Columns 69**: Checksum

**Line 2 fields (orbital elements):**

- **Column 01**: Line number (`2`)
- **Columns 03–07**: Satellite number (`25544`)
- **Columns 09–16**: Inclination \(i\) [deg]
- **Columns 18–25**: Right Ascension of Ascending Node (RAAN, \(\Omega\)) [deg]
- **Columns 27–33**: Eccentricity \(e\) (decimal point implied)
- **Columns 35–42**: Argument of Perigee \(\omega\) [deg]
- **Columns 44–51**: Mean Anomaly \(M\) [deg]
- **Columns 53–63**: Mean Motion \(n\) [rev/day]
- **Columns 64–68**: Revolution number at epoch

For SGP4, you typically feed **both TLE lines** as raw strings to a library function, which returns a satellite record that can be propagated to arbitrary times.

---

### Classical Orbital Elements (COEs)

For Keplerian orbits, you commonly use **six** classical orbital elements:

- **Semi-major axis** \(a\) [km]
- **Eccentricity** \(e\) (0 circular, <1 elliptical, =1 parabolic, >1 hyperbolic)
- **Inclination** \(i\) [rad/deg] – tilt of the orbit plane w.r.t. Earth’s equator
- **Right Ascension of Ascending Node** \(\Omega\) [rad/deg] – angle from reference direction to where the orbit crosses the equator northbound
- **Argument of Perigee** \(\omega\) [rad/deg] – angle from ascending node to perigee in the orbit plane
- **True Anomaly** \(\nu\) [rad/deg] – position of the satellite along the ellipse at a given time

**TLE → COE mapping (approximate):**

- \(i =\) inclination
- \(\Omega =\) RAAN
- \(\omega =\) argument of perigee
- Mean anomaly \(M\) and mean motion \(n\) are used with SGP4 to compute \(\nu\) and \(a\) at a given time (the mapping is non-trivial and handled by SGP4).

---

### Time Systems

Propagation and visualization require consistent time handling:

- **TLE epoch**: days of year relative to UTC.
- **Propagation time**: usually expressed as:
  - Offset seconds from TLE epoch, or
  - Absolute UTC timestamps (e.g., JS `Date`, Python `datetime`).

When using an SGP4 library, you typically:

- Parse the TLE to get an **epoch**.
- For a desired time \(t\), compute \(\Delta t = t - t_{\text{epoch}}\).
- Pass \(\Delta t\) into the SGP4 function, which returns the position/velocity at \(t\).

---

### SGP4 Propagation

**SGP4 (Simplified General Perturbations 4)** is the standard algorithm for propagating TLE-based orbits.

Key points:

- **Inputs**:
  - Two TLE lines.
  - Desired time(s) relative to the TLE epoch.
- **Outputs**:
  - Satellite position and velocity in **TEME** frame (usually \(x, y, z, \dot{x}, \dot{y}, \dot{z}\) in km and km/s).
- **Perturbations modeled**:
  - Earth’s oblateness (J2, J3, J4)
  - Atmospheric drag (via BSTAR)
  - Resonance effects for some orbits
- **Use cases**:
  - Short to medium term orbit prediction (days to weeks).
  - Visualization and basic analysis of LEO/MEO/GEO satellites.

In practice, for web/JS apps you often use `satellite.js` or similar to:

- Parse TLE → create satrec.
- Propagate satrec at many timestamps → get positions.

---

### Coordinate Frames

For visualization, you’ll often convert between several frames:

- **TEME (True Equator, Mean Equinox)**:
  - Native SGP4 output frame.
- **ECI (Earth-Centered Inertial)**:
  - Non-rotating frame, origin at Earth’s center.
  - Useful for physics and orbital mechanics.
- **ECEF (Earth-Centered, Earth-Fixed)**:
  - Rotates with the Earth; longitude/latitude fixed.
  - Needed for mapping and ground tracking.
- **Geodetic lat/lon/alt**:
  - Latitude, longitude, and altitude over an Earth ellipsoid.
  - Necessary to plot ground tracks, footprint circles, etc.

Common pipeline:

1. **TLE + time → SGP4 → TEME position/velocity.**
2. **TEME → ECI** (often handled implicitly by library).
3. **ECI → ECEF** (accounting for Earth rotation, polar motion, etc.).
4. **ECEF → lat/lon/alt** for ground track.
5. For 3D visualization tools (e.g., Cesium):
   - Convert ECEF or lat/lon/alt into the engine’s coordinate system (usually Earth-fixed).

---

### Orbital Period and Mean Motion

**Mean motion** \(n\) (from TLE) is in **revolutions per day**.

- Orbital period \(T\) is:

\[
T = \frac{1}{n} \text{ days} = \frac{86400}{n} \text{ seconds}
\]

For LEO, \(n \approx 15\) rev/day → \(T \approx 90\) minutes.

---

### Visualizing Orbits

To visualize orbits (e.g., in Cesium or other 3D engines), you typically:

- **Choose a time span**:
  - E.g., from now to now + 1 orbit period, or now to now + 24 hours.
- **Sample times**:
  - E.g., every 10–60 seconds.
- **Propagate**:
  - For each sample time, use SGP4 to get position in TEME/ECI.
- **Convert to visualization coordinates**:
  - Earth-fixed (ECEF) or lat/lon/alt.
  - Feed into the engine as positions over time (trajectories).
- **Render**:
  - Satellite marker at current position.
  - Polyline or path representing orbit track.
  - Optional: ground track, sensor cones, coverage footprints.

For multiple satellites:

- Repeat the above per TLE.
- Consider limiting the number of time samples or satellites rendered at once for performance.

---

### Practical Checklist for Visualization

To visualize orbits from TLEs you need:

- **Data**:
  - One or more valid TLEs (two-line strings).
- **Time handling**:
  - Current time and offsets from TLE epoch.
- **Propagation**:
  - SGP4 implementation (e.g., `satellite.js`, `python-sgp4`, etc.).
- **Coordinate transforms**:
  - TEME/ECI → ECEF → lat/lon/alt (provided by many libraries).
- **Visualization engine**:
  - 3D globe or 2D map (e.g., Cesium, Leaflet, custom WebGL).
- **Sampling strategy**:
  - Time range and step for generating orbit path and ground track.

With these components in place, you can parse TLEs, propagate satellite states over time, and render accurate, time-varying orbit visualizations.

