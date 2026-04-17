"""
Literature-derived hydrogeological defaults by aquifer rock-type.
Used only when a real measured value is not present in the source dataset.
Sources: Freeze & Cherry (1979), CGWB Jharkhand Dynamic GW Resource reports (averages).

Values:
    porosity                  [fraction, 0-1]
    hydraulic_conductivity    [m/day]
"""
from typing import Dict, Optional

LITERATURE_HYDRO_PROPS: Dict[str, Dict[str, float]] = {
    "basalt":                    {"porosity": 0.08, "hydraulic_conductivity": 0.30},
    "charnockite":               {"porosity": 0.03, "hydraulic_conductivity": 0.05},
    "gneiss":                    {"porosity": 0.04, "hydraulic_conductivity": 0.10},
    "basement_gneissic_complex": {"porosity": 0.04, "hydraulic_conductivity": 0.08},
    "granite":                   {"porosity": 0.03, "hydraulic_conductivity": 0.05},
    "intrusive":                 {"porosity": 0.03, "hydraulic_conductivity": 0.05},
    "laterite":                  {"porosity": 0.20, "hydraulic_conductivity": 1.20},
    "limestone":                 {"porosity": 0.15, "hydraulic_conductivity": 1.00},
    "sandstone":                 {"porosity": 0.20, "hydraulic_conductivity": 0.50},
    "alluvium":                  {"porosity": 0.30, "hydraulic_conductivity": 5.00},
    "quartzite":                 {"porosity": 0.02, "hydraulic_conductivity": 0.02},
    "schist":                    {"porosity": 0.04, "hydraulic_conductivity": 0.08},
}


def get_literature_defaults(aquifer_type: Optional[str]) -> Dict[str, float]:
    """Return {'porosity': x, 'hydraulic_conductivity': y} for the given rock type.
    Falls back to 'gneiss' (dominant Chota Nagpur plateau aquifer) when type is unknown."""
    key = (aquifer_type or "").lower().strip()
    return LITERATURE_HYDRO_PROPS.get(key, LITERATURE_HYDRO_PROPS["gneiss"])
