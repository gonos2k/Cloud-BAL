"""Read-only support and common-pressure checks for a gas-only dry-mass column."""

import numpy as np

from qbal_dry_mass_column import G0, remap_component_masses


T0 = 273.15
CP_DRY = 1004.5
CP_VAPOR = 1846.4
H_VAPOR_0 = 2.5e6


def surface_support(surface_pressure, pressure_10m, old_bottom, new_bottom, mixing_ratio):
    """Account only for the surface-to-10 m prior; leave the higher gap unknown."""
    values = np.asarray((surface_pressure, pressure_10m, old_bottom,
                         new_bottom, mixing_ratio), dtype=np.float64)
    if (not np.isfinite(values).all() or mixing_ratio < 0 or
            not 0 < old_bottom <= surface_pressure or
            not 0 < new_bottom <= surface_pressure or
            not 0 < pressure_10m <= surface_pressure):
        raise ValueError('invalid surface pressure support')
    q_surface = mixing_ratio / (1 + mixing_ratio)

    def interval(bottom):
        supported_width = surface_pressure - max(bottom, pressure_10m)
        gap_width = max(0.0, pressure_10m - bottom)
        gas_mass = supported_width / G0
        return {
            'supported_span_Pa': supported_width,
            'unsupported_span_Pa': gap_width,
            'supported_dry_mass_kg_m2': gas_mass * (1 - q_surface),
            'supported_vapor_mass_kg_m2': gas_mass * q_surface,
            'unsupported_gas_mass_kg_m2': gap_width / G0,
        }

    return {'old': interval(old_bottom), 'new_if_PS_fixed': interval(new_bottom)}


def gas_enthalpy(dry_mass, vapor_mass, temperature):
    """Dry-air and vapor enthalpy, J/m², with the Cloud-BAL dry-air convention."""
    return ((CP_DRY * dry_mass + CP_VAPOR * vapor_mass) * (temperature - T0)
            + H_VAPOR_0 * vapor_mass)


def common_pressure_projection(state):
    """Project the moved gas cells onto old intervals; retain the new edge separately."""
    old_pressure = state['old_pressure']
    new_pressure = state['new_pressure']
    if (new_pressure[0] < old_pressure[0] or
            new_pressure[-1] != old_pressure[-1]):
        raise ValueError('this comparison requires a new lower edge below the old one')
    has_edge = new_pressure[0] > old_pressure[0]
    target = np.r_[new_pressure[0], old_pressure] if has_edge else old_pressure
    dry, vapor = remap_component_masses(
        new_pressure, state['dry_mass'], state['new_vapor'], target)

    # The same overlap fractions carry the extensive mixture enthalpy.
    overlap = np.maximum(0.0, np.minimum(new_pressure[:-1, None], target[None, :-1]) -
                         np.maximum(new_pressure[1:, None], target[None, 1:]))
    fraction = overlap / (new_pressure[:-1] - new_pressure[1:])[:, None]
    donor_enthalpy = gas_enthalpy(
        state['dry_mass'], state['new_vapor'], state['layer_temperature_K'])
    enthalpy = donor_enthalpy @ fraction
    edge = int(has_edge)
    temperature = T0 + (enthalpy[edge:] - H_VAPOR_0 * vapor[edge:]) / (
        CP_DRY * dry[edge:] + CP_VAPOR * vapor[edge:])
    q = vapor[edge:] / (dry[edge:] + vapor[edge:])
    if not np.isfinite(temperature).all() or not np.isfinite(q).all():
        raise ValueError('common-pressure projection is not finite')
    return {
        'edge_dry_mass_kg_m2': float(dry[0]) if has_edge else 0.0,
        'edge_vapor_mass_kg_m2': float(vapor[0]) if has_edge else 0.0,
        'old_pressure_cell_dry_mass_kg_m2': dry[edge:],
        'old_pressure_cell_vapor_mass_kg_m2': vapor[edge:],
        'old_pressure_cell_q_kg_kg': q,
        'old_pressure_cell_temperature_K': temperature,
        'old_pressure_cell_enthalpy_J_m2': enthalpy[edge:],
        'total_enthalpy_J_m2': float(np.sum(enthalpy)),
    }
