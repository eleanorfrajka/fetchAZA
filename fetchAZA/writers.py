import numpy as np
import xarray as xr
from numbers import Number
import os
from fetchAZA import utilities
import logging
_log = logging.getLogger(__name__)

def save_dataset(ds, output_file='../data/test.nc'):
    """
    Attempts to save the dataset to a NetCDF file. If a TypeError occurs due to invalid attribute values,
    it converts the invalid attributes to strings and retries the save operation.

    Parameters
    ----------
    ds (xarray.Dataset): The dataset to be saved.
    output_file (str): The path to the output NetCDF file. Defaults to 'test.nc'.

    Returns
    -------
    bool: True if the dataset was saved successfully, False otherwise.

    Note
    ----    
    Based on: https://github.com/pydata/xarray/issues/3743
    """
    valid_types = (str, int, float, np.float32, np.float64, np.int32, np.int64)
    # More general
    valid_types = (str, Number, np.ndarray, np.number, list, tuple)


    # Check for empty strings
    encoding = { }
    for var in ds.variables:
        if ds[var].dtype == 'timedelta64[ns]':
            _log.warning(f"Variable '{var}' has dtype 'timedelta64[ns]'. Converting to float seconds.")
            ds[var] = ds[var].astype('timedelta64[s]').astype(float)
        if ds[var].dtype == 'datetime64[ns]':
            ds[var].encoding['units'] = 'seconds since 1970-01-01 00:00:00'
            _log.info(f"Variable '{var}' has dtype 'datetime64[ns]', and length {str(len(ds[var]))}. Encoding as {ds[var].encoding['units']}.")
            if 'units' in ds[var].attrs:
                _log.warning(f"Variable '{var}' has attribute 'units'={ds[var].attrs['units']}. Removing attribute")
                del ds[var].attrs['units']
        
    try:
        ds.to_netcdf(output_file)
        return True
    except TypeError as e:
        print(e.__class__.__name__, e)
        for varname, variable in ds.variables.items():
            for k, v in variable.attrs.items():
                if not isinstance(v, valid_types) or isinstance(v, bool):
                    _log.warning(f"variable '{varname}': Converting attribute '{k}' with value '{v}' to string.")
                    variable.attrs[k] = str(v)
        try:
            ds.to_netcdf(output_file) #, format='NETCDF4_CLASSIC'
            return True
        except Exception as e:
            _log.error("Failed to save dataset:", e)
            datetime_vars = [var for var in ds.variables if ds[var].dtype == 'datetime64[ns]']
            _log.info("Variables with dtype datetime64[ns]:", datetime_vars)
            float_attrs = [attr for attr in ds.attrs if isinstance(ds.attrs[attr], float)]
            _log.info("Attributes with dtype float64:", float_attrs)
            return False

def save_datasets(data_sets_new, input_fn):
    """
    Save multiple datasets to NetCDF files with filenames derived from the input filename.

    Parameters
    ----------
    data_sets_new : dict
        A dictionary where keys are dataset identifiers (e.g., strings) and values are the corresponding datasets to be saved.
    input_fn : str
        The input filename used as a base to generate output filenames.

    Notes
    -----
    - Iterates through the `data_sets_new` dictionary.
    - For each dataset, constructs an output filename by appending the dataset key to the base name of `input_fn` and adding the `.nc` extension.
    - Calls `save_dataset` to save each dataset to the corresponding output file.
    - Prints the key of each dataset being processed.
    - If saving a dataset fails, prints an error message indicating the failure.

    Assumes the existence of a `save_dataset` function that handles the actual saving of datasets to files.
    """

    for key, ds in data_sets_new.items():
        _log.info(f"------------ Saving dataset for key: {key} ------------")
        output_file = os.path.splitext(input_fn)[0] + f"_{key}.nc"

        if not save_dataset(ds, output_file):
            _log.error(f"Failed to save dataset for key: {key}")
            print(f"Failed to save dataset for key: {key}")