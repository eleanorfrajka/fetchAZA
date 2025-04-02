import pathlib
import sys

script_dir = pathlib.Path(__file__).parent.absolute()
parent_dir = script_dir.parents[0]
sys.path.append(str(parent_dir))

import pytest
import numpy as np
import pandas as pd
import xarray as xr
from AZApressure import utilities







@pytest.mark.parametrize("input_value,expected", [
    ("00123", "00123"),
    ("123", 123),
    ("12.3", 12.3),
    ("abc", "abc")
])
def test_convert_type(input_value, expected):
    result = utilities.convert_type(input_value)
    assert result == expected


def test_convert_float_to_int():
    ds = xr.Dataset({"a": ("x", [1.0, 2.0, 3.0])})
    new_ds = utilities.convert_float_to_int(ds)
    assert np.issubdtype(new_ds["a"].dtype, np.integer)

