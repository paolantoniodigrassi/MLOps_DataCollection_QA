'''
Contiene operatori matematici e di parsing numerico per la parte
geometrica
'''
from typing import Any, List, Optional
import math


def x_to_float(x: Any) -> Optional[float]:
    '''
    Converts x to float if possible
    '''
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None
    

def xyz_as_floats(value: Any) -> Optional[List[float]]:
    '''
    Converts [x,y,z] to floats from a list/tuple value
    '''
    if value is None or not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    vals = [x_to_float(value[0]), x_to_float(value[1]), x_to_float(value[2])]
    if any(v is None for v in vals):
        return None
    return [vals[0], vals[1], vals[2]]


def six_as_floats(value: Any) -> Optional[List[float]]:
    '''
    Converts ImageOrientationPatient to 6 floats
    '''
    if value is None or not isinstance(value, (list, tuple)) or len(value) < 6:
        return None
    vals = [x_to_float(value[i]) for i in range(6)]
    if any(v is None for v in vals):
        return None
    return [vals[i] for i in range(6)]


def dot_product(a: List[float], b: List[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross_product(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0]
    ]


def normalize(v: List[float]) -> Optional[List[float]]:
    n = math.sqrt(dot_product(v, v))
    if n == 0:
        return None
    return [v[0] / n, v[1] / n, v[2] / n]


def slice_normal_from_iop(iop: List[float]) -> Optional[List[float]]:
    row = iop[0:3]
    col = iop[3:6]
    return normalize(cross_product(row, col))