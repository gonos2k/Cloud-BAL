"""Gas-only dry-mass-fixed transform for one supported pressure column.

Each input q is kg vapor per kg (dry air + vapor). Layer values are pressure-
weighted endpoint means, held constant within their respective pressure cells.
"""

import numpy as np


G0 = 9.80665
RD = 287.05
EPSILON = 0.622


def dry_mass_column(pressure, q_before, q_after, temperature):
    """Keep each initial dry layer mass; fix the upper pressure boundary."""
    pressure = np.asarray(pressure, dtype=np.float64)
    q_before = np.asarray(q_before, dtype=np.float64)
    q_after = np.asarray(q_after, dtype=np.float64)
    temperature = np.asarray(temperature, dtype=np.float64)
    if (pressure.ndim != 1 or pressure.size < 2 or
            any(x.shape != pressure.shape for x in (q_before, q_after, temperature)) or
            not np.isfinite(pressure).all() or not np.isfinite(q_before).all() or
            not np.isfinite(q_after).all() or not np.isfinite(temperature).all() or
            np.any(pressure <= 0) or np.any(np.diff(pressure) >= 0) or
            np.any(q_before < 0) or np.any(q_after < 0) or
            np.any(q_before >= 1) or np.any(q_after >= 1) or
            np.any((temperature < 150) | (temperature > 350))):
        raise ValueError('invalid supported gas column')

    q0 = (q_before[:-1] + q_before[1:]) / 2
    q1 = (q_after[:-1] + q_after[1:]) / 2
    t = (temperature[:-1] + temperature[1:]) / 2
    old_width = pressure[:-1] - pressure[1:]
    dry_mass = old_width * (1 - q0) / G0
    old_vapor = old_width * q0 / G0
    new_vapor = dry_mass * q1 / (1 - q1)
    new_vapor = np.where(q1 == q0, old_vapor, new_vapor)
    # Accumulate only the width change, so identical humidity preserves every
    # original interface exactly, including on a nonuniform pressure grid.
    width_change = old_width * (q1 - q0) / (1 - q1)
    new_pressure = pressure.copy()
    accumulated_change = 0.0
    for k in range(width_change.size - 1, -1, -1):
        accumulated_change += width_change[k]
        new_pressure[k] += accumulated_change

    # Constant T and q within each cell give this exact hypsometric thickness.
    old_tv = t * (1 - q0 + q0 / EPSILON)
    new_tv = t * (1 - q1 + q1 / EPSILON)
    old_thickness = RD / G0 * old_tv * np.log(pressure[:-1] / pressure[1:])
    new_thickness = RD / G0 * new_tv * np.log(new_pressure[:-1] / new_pressure[1:])
    if (not all(np.isfinite(x).all() for x in (
            dry_mass, old_vapor, new_vapor, new_pressure, old_thickness, new_thickness)) or
            np.any(np.diff(new_pressure) >= 0)):
        raise ValueError('gas column calculation is not finite and ordered')
    return {
        'old_pressure': pressure, 'new_pressure': new_pressure,
        'old_q': q0, 'new_q': q1, 'layer_temperature_K': t,
        'dry_mass': dry_mass, 'old_vapor': old_vapor, 'new_vapor': new_vapor,
        'old_thickness': old_thickness, 'new_thickness': new_thickness,
    }


def remap_component_masses(donor_pressure, dry_mass, vapor_mass, target_pressure):
    """Remap two extensive gas components over identical pressure endpoints."""
    donor = np.asarray(donor_pressure, dtype=np.float64)
    target = np.asarray(target_pressure, dtype=np.float64)
    dry = np.asarray(dry_mass, dtype=np.float64)
    vapor = np.asarray(vapor_mass, dtype=np.float64)
    if (donor.ndim != 1 or target.ndim != 1 or donor.size < 2 or target.size < 2 or
            dry.shape != (donor.size - 1,) or vapor.shape != dry.shape or
            not all(np.isfinite(x).all() for x in (donor, target, dry, vapor)) or
            np.any(donor <= 0) or np.any(target <= 0) or
            np.any(np.diff(donor) >= 0) or np.any(np.diff(target) >= 0) or
            np.any(dry <= 0) or np.any(vapor < 0) or
            donor[0] != target[0] or donor[-1] != target[-1]):
        raise ValueError('remap needs finite positive masses and identical endpoints')
    widths = donor[:-1] - donor[1:]
    overlap = np.maximum(0.0, np.minimum(donor[:-1, None], target[None, :-1]) -
                         np.maximum(donor[1:, None], target[None, 1:]))
    fractions = overlap / widths[:, None]
    mapped_dry, mapped_vapor = dry @ fractions, vapor @ fractions
    if (not np.isfinite(mapped_dry).all() or not np.isfinite(mapped_vapor).all() or
            np.any(mapped_dry <= 0) or np.any(mapped_vapor < 0)):
        raise ValueError('remapped component mass is invalid')
    return mapped_dry, mapped_vapor
