# Based on https://github.com/voto-ocean-knowledge/votoutils/blob/main/votoutils/utilities/utilities.py
import re
import numpy as np
import pandas as pd
import datetime
import xarray as xr
from AZApressure import readers, writers, plotters, tools

import logging

_log = logging.getLogger(__name__)




def netcdf_compliancer(ds):
    """
    Check for variables and attributes with empty string values in the dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to check.

    Returns
    -------
    None
    """
    # Find variables with empty string values
    empty_string_vars = {var: ds[var].values for var in ds.data_vars if (ds[var].dtype == object and (ds[var] == '').any())}

    # Print the variables with empty string values
    for var, values in empty_string_vars.items():
        _log.warning(f"Variable '{var}' has empty string values.")

    # Find attributes with empty string values
    empty_string_attrs = {attr: value for attr, value in ds.attrs.items() if value == ''}

    # Print the attributes with empty string values
    #for attr, value in empty_string_attrs.items():
    #    _log.warning(f"Attribute '{attr}' has an empty string value.")

    # Find attributes on variables with empty string values
    empty_string_attr_vars = {}
    for var in ds.data_vars:
        empty_attrs = {attr: value for attr, value in ds[var].attrs.items() if value == ''}
        if empty_attrs:
            empty_string_attr_vars[var] = empty_attrs

    # Print the variables and their attributes with empty string values
    #for var, attrs in empty_string_attr_vars.items():
    #    for attr, value in attrs.items():
    #        _log.warning(f"Variable '{var}' has attribute '{attr}' has an empty string value.")

    return empty_string_vars, empty_string_attrs, empty_string_attr_vars

def find_best_dtype(var_name, da):
    """
    Determines the most appropriate data type for a given variable based on its name and data array.

    Rules
    ------
    1. If the variable name contains "latitude" or "longitude" (case-insensitive), return `np.double`.
    2. If the variable name ends with "qc" (case-insensitive), return `np.int8`.
    3. If the variable name contains "time" (case-insensitive), return the input data type.
    4. If the variable name ends with "raw" or the input data type is an integer:
       - If the maximum value in the data array is less than 2^15, return `np.int16`.
       - If the maximum value in the data array is less than 2^31, return `np.int32`.
    5. If the input data type is `np.float64`, return `np.float32`.
    6. Otherwise, return the input data type.

    Parameters
    -----------
    var_name : str
        The name of the variable. This is used to infer the type based on naming conventions.
    da : xarray.DataArray
        The data array containing the variable's values and its current data type.

    Returns
    --------
    numpy.dtype
        The recommended data type for the variable.
    """

    input_dtype = da.dtype.type
    if "latitude" in var_name.lower() or "longitude" in var_name.lower():
        return np.double
    if var_name[-2:].lower() == "qc":
        return np.int8
    if "time" in var_name.lower():
        return input_dtype
    if var_name[-3:] == "raw" or "int" in str(input_dtype):
        if np.nanmax(da.values) < 2**16 / 2:
            return np.int16
        elif np.nanmax(da.values) < 2**32 / 2:
            return np.int32
    if input_dtype == np.float64:
        return np.float32
    return input_dtype



def set_best_dtype(ds):
    """
    Adjusts the data types of variables in an xarray Dataset to optimize memory usage 
    while preserving data integrity. The function evaluates each variable's current 
    data type and determines a more efficient data type, if applicable. It also updates 
    attributes like `valid_min` and `valid_max` to match the new data type.

    Parameters
    ----------
    ds : xarray.Dataset
        The input dataset whose variables' data types will be evaluated and potentially 
        adjusted.

    Returns
    --------
    xarray.Dataset
        A new dataset with optimized data types for its variables, potentially saving 
        memory space.

    Notes
    ------
    - If a variable's data type is changed to an integer type, NaN values are replaced 
      with a fill value, and the `_FillValue` encoding is updated accordingly.
    - Logs the percentage of memory saved due to data type adjustments.
    - Relies on the helper functions `find_best_dtype` and `set_fill_value` to determine 
      the optimal data type and appropriate fill value, respectively.
    - Logs debug messages for each variable whose data type is changed, including the 
      original and new data types.
    - Logs an info message summarizing the overall memory savings.
    - Raises: Assumes that `find_best_dtype` and `set_fill_value` are defined elsewhere in the 
      codebase.
    - Raises: Assumes that `_log` is a configured logger available in the current scope.
    """

    bytes_in = ds.nbytes
    for var_name in list(ds):
        da = ds[var_name]
        input_dtype = da.dtype.type
        new_dtype = find_best_dtype(var_name, da)
        for att in ["valid_min", "valid_max"]:
            if att in da.attrs.keys():
                da.attrs[att] = np.array(da.attrs[att]).astype(new_dtype)
        if new_dtype == input_dtype:
            continue
        _log.debug(f"{var_name} input dtype {input_dtype} change to {new_dtype}")
        da_new = da.astype(new_dtype)
        ds = ds.drop_vars(var_name)
        if "int" in str(new_dtype):
            fill_val = set_fill_value(new_dtype)
            da_new[np.isnan(da)] = fill_val
            da_new.encoding["_FillValue"] = fill_val
        ds[var_name] = da_new
    bytes_out = ds.nbytes
    _log.info(
        f"Space saved by dtype downgrade: {int(100 * (bytes_in - bytes_out) / bytes_in)} %",
    )
    return ds

def set_fill_value(new_dtype):
    """
    Calculate and return the maximum fill value for a given numeric data type.
    The function extracts the bit-width of the provided data type (e.g., int32, uint16)
    and computes the maximum value that can be represented by that type, assuming it
    is a signed integer type.

    Parameters
    ----------
    new_dtype : str
        A string representation of the data type (e.g., 'int32', 'uint16').

    Returns
    -------
    int
        The maximum fill value for the given data type.

    Raises
    ------
    ValueError: If the bit-width cannot be extracted from the provided data type string.
    """

    fill_val = 2 ** (int(re.findall("\d+", str(new_dtype))[0]) - 1) - 1
    return fill_val



def convert_float_to_int(ds):
    """
    Converts float variables in an xarray dataset to integer type if all values 
    are sufficiently close to their integer representation.

    Parameters
    ----------
    ds : xarray.Dataset 
        An xarray dataset containing variables to be checked and potentially converted.

    Returns
    -------
    None 
        The dataset is modified in place, with applicable variables converted to integer type.
    """
    for var in ds.data_vars:
        # Check if the variable is of type float
        if np.issubdtype(ds[var].dtype, np.floating):
            # Check if all values are equal to their integer representation
            with np.errstate(invalid='ignore'):
                if np.all(np.isclose(ds[var].values, ds[var].values.astype(int), equal_nan=True)):

                    # Convert the variable to integer type
                    ds[var] = ds[var].astype(int)
                    _log.info(f"Converted {var} to integer type.")
    return ds

# Convert column types
def convert_type(value):
    """
    Convert a string value to an appropriate type.

    This function attempts to convert a string value to an integer or a float.
    If the value contains a leading zero and is entirely numeric, it is returned as a string to preserve the leading zero.
    If the value contains a decimal point, it is converted to a float.
    If the value is numeric without a decimal point, it is converted to an integer.
    If the conversion to an integer or float fails, the value is returned as a string.

    Parameters
    ----------
    value : str
        The string value to be converted.

    Returns
    -------
    int, float, or str
        The converted value as an integer, float, or string.
    """

    if value.isdigit() and value.startswith("0"):
        return str(value)  # Keep leading zeros
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return str(value)

def reformat_object_vars(data):
    """
    Fix variables with mixed data types in xarray datasets or a single xarray dataset.

    This function processes variables with mixed data types (e.g., object type) by attempting to convert them 
    to a single consistent type (e.g., float, int, or string). It removes common fill values ('0') and checks 
    the remaining values to determine the appropriate type. If conversion to integer is not possible, the 
    variable is converted to a string.

    Parameters
    ----------
    data : dict or xarray.Dataset
        A dictionary of xarray datasets or a single xarray dataset.

    Returns
    -------
    dict or xarray.Dataset
        A dictionary of modified xarray datasets or a single modified xarray dataset with variables of type 
        object converted to numeric (if possible) or string (otherwise).
    """
    def _fix_multitype_object_variables(ds):
        for var in ds.variables:
            d1 = ds[var]
            if ds[var].dtype == object:
                indices = np.where(d1 == '0')[0]
                other_indices = np.where(d1 != '0')[0]
                d2 = ds[var][other_indices]
                d3 = d2.values

                if isinstance(d3, np.ndarray):
                    number_type = type(d3[0])
                    if number_type is float:
                        newtype = 'FLOAT'
                        ds[var][indices] = np.nan
                        ds[var] = ds[var].astype(float)
                    elif number_type is int:
                        try:
                            newtype = 'INT'
                            ds[var] = ds[var].astype(int)
                            ds[var][indices] = -9999
                            ds[var].attrs['_FillValue'] = -9999
                        except:
                            newtype = 'STR (not INT)'
                            ds[var] = ds[var].astype(str)
                            ds[var][indices] = ''
                            ds[var].attrs['_FillValue'] = ''
                    elif number_type is str:
                        newtype = 'STR'
                        ds[var] = ds[var].astype(str)
                        ds[var][indices] = ''
                        ds[var].attrs['_FillValue'] = ''

                    _log.info(f"- '{var}' is dtype object / '0' occurs {str(len(indices))} times --> {newtype}.")
                else:
                    _log.warning(f"Variable '{var}' is not a numpy array.")
        return ds

    if isinstance(data, dict):
        _log.info('-------------- utilities.reformat_object_vars --------------')
        data_new = {}
        for key, ds in data.items():
            _log.info(f"{key}")
            data_new[key] = _fix_multitype_object_variables(ds)
        return data_new
    elif isinstance(data, xr.Dataset):
        return _fix_multitype_object_variables(data)
    else:
        raise TypeError("Input must be a dictionary of xarray datasets or a single xarray dataset.")
