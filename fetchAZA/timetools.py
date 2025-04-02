import numpy as np
import pandas as pd
import xarray as xr
from datetime import datetime
from collections import Counter
from fetchAZA import readers, writers, plotters, utilities, tools
import logging
import re
_log = logging.getLogger(__name__)

# AZA has so many issues with time, needs its own module
#

def assign_sample_time(ds, pattern=['AZS','AZA','AZA','AZA','AZS'], adjust_time=None):
    """
    Assigns SAMPLE_TIME to the dataset based on SEQUENCE_NUM and AGE.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to process.

    Returns
    -------
    xarray.Dataset
        The dataset with the SAMPLE_TIME variable assigned.
    """
    snum = len(pattern)
    # Filter the dataset for sequence_num == 5 (or length of pattern)
    sequence_5 = ds.where(ds['SEQUENCE_NUM'] == snum, drop=True)

    # Compute the sequence_start as Record_time minus the age in seconds
    sequence_5_start = sequence_5['RECORD_TIME'] 
    sequence_start = sequence_5['RECORD_TIME'] - np.timedelta64(1, 'ms') * (1000 * sequence_5['AGE'])
    sequence_start_repeated = np.repeat(sequence_start.values, snum)

    sequence_1 = ds.where(ds['SEQUENCE_NUM'] == 1, drop=True)
    sequence_1_start = sequence_1['RECORD_TIME'] 
    # Check if sequence_1_start and sequence_5_start are identical
    if not np.array_equal(sequence_1_start, sequence_5_start):
        mismatch_count = np.sum(sequence_1_start != sequence_5_start)
        _log.warning(f"sequence_1_start and sequence_5_start are not identical {mismatch_count} times.")

    # Set dimensions for the new variable
    dims = list(ds['RECORD_TIME'].dims)

    # Create a new variable in ds called SAMPLE_TIME
    ds['SAMPLE_TIME'] = (dims, sequence_start_repeated)

    # Add the AGE in seconds to SAMPLE_TIME
    ds['SAMPLE_TIME'] += (1000 * ds['AGE']).astype('timedelta64[ms]')

    descript_str1 = f"Time of the sample. For each {str(snum)}-sequence AZA cycle, the start time of the sample is recorded as the Record Time minus the age in seconds for sequence {str(snum)}."
    _log.info(f"Assigning SAMPLE_TIME based on RECORD_TIME minus AGE in seconds for SEQUENCE_NUM {str(snum)}.")

    # Adjust SAMPLE_TIME for SEQUENCE_NUM 2, 3, or 4 by subtracting 15 seconds
    if adjust_time is not None:
        sequence_nums = list(range(2, snum))
        ds['SAMPLE_TIME'] = ds['SAMPLE_TIME'].where(~ds['SEQUENCE_NUM'].isin(sequence_nums), ds['SAMPLE_TIME'] - np.timedelta64(adjust_time, 's'))

        descript_str2 = f" The sample time is then adjusted forward based on the age in seconds for each measurement in the sequence, and then further adjusted for sequences 2:{str(snum-1)} by subtracting {str(adjust_time)} seconds (mid-point for a {str(2*adjust_time)}-second average)."
        _log.info(f"Adjusting SAMPLE_TIME for SEQUENCE_NUM 2:{str(snum-1)} by subtracting {str(adjust_time)} seconds.")
    else:
        descript_str2 = ''
    
    ds['SAMPLE_TIME'].attrs['description'] = descript_str1 + descript_str2

    return ds

def cut_to_deployment(datasets2, deploy_date, recovery_date):
    """
    Filter datasets to include only data within the specified deployment and recovery dates.

    Parameters
    ----------
    data_sets : dict
        A dictionary where keys are dataset names and values are xarray datasets.
    deploy_date : str or datetime-like
        The deployment date. Data before this date will be excluded.
    recovery_date : str or datetime-like
        The recovery date. Data after this date will be excluded.

    Returns
    -------
    dict
        A dictionary of filtered datasets with the same keys as the input dictionary.
    """
    # Cut to deployment period
    if deploy_date is not None:
        deploy_datetime = np.datetime64(deploy_date)
    else:
        deploy_datetime = np.datetime64('1900-01-01')
    if recovery_date is not None:
        recovery_datetime = np.datetime64(recovery_date)    
    else:
        recovery_datetime = np.datetime64('2100-01-01')
    
    for key in datasets2:
        indices = np.where((datasets2[key]['RECORD_TIME'] >= deploy_datetime) & 
                           (datasets2[key]['RECORD_TIME'] <= recovery_datetime))[0]   
        if len(indices)<len(datasets2[key]['RECORD_TIME']):
            _log.warning(f"Dataset '{key}' has been truncated to the deployment period. Original length: {len(datasets2[key]['RECORD_TIME'])}, New length: {len(indices)}")
        datasets2[key] = datasets2[key].isel(index=indices)

    return datasets2

def convert_seconds_to_float(ds):
    """
    Convert variables with units of 'seconds' in an xarray Dataset to float type.

    Parameters
    ----------
    ds : xarray.Dataset
        The input dataset containing variables to be converted.

    Returns
    -------
    xarray.Dataset
        The dataset with variables in 'seconds' units converted to float type.
    """
    for var in ds.variables:
        if ds[var].attrs.get('units') == 'seconds':
            if np.issubdtype(ds[var].dtype, np.timedelta64):
                ds[var].values = ds[var].values.astype('timedelta64[s]').astype('float')
                _log.info(f"{var}".ljust(20) + f"Recast dtype timedelta64[s] --> float")
    return ds



def increment_duplicate_time(time_values):
    """
    Increment a time by a small amount to make it unique.

    Parameters:
        time (numpy.datetime64): A time.

    Returns:
        numpy.datetime64: A time incremented by a small amount.
    """
    increment = np.timedelta64(1, 'ns')
    duplicate_times = time_values[time_values.duplicated()]
    if len(duplicate_times):

        for time in duplicate_times:
            indices = np.where(time_values == time)[0]
            if len(indices):

                for i in indices[1:]:
                    time_values = time_values.to_list()
                    time_values[i] += increment * (i - indices[0])
                    time_values = pd.to_datetime(time_values)

    return time_values, len(duplicate_times) 

def reindex_on_time(ds):
    """
    Ensure unique time values and set them as the dimension.

    Parameters:
    ds (xarray.Dataset): The input xarray dataset.

    Returns:
    xarray.Dataset: The processed dataset.
    """
    if 'SAMPLE_TIME' in ds:
        time_var = 'SAMPLE_TIME'
    elif 'RECORD_TIME' in ds:
        time_var = 'RECORD_TIME'
    else:
        raise ValueError("Dataset must contain either 'RECORD_TIME' or 'SAMPLE_TIME'.")

    # Ensure time values are unique
    time_vals = ds[time_var].to_series()
    if not time_vals.is_unique:
        new_time, _ = increment_duplicate_time(time_vals)
        ds[time_var].values[:] = new_time.values

    # Assign the time variable as new dimension
    ds = ds.swap_dims({'index': time_var})
    ds = ds.set_coords(time_var)

    return ds


def compare_record_times(keys, time_var, datasets):
    # Extract record times for the given keys
    record_times = {key: datasets[key][time_var] for key in keys}

    # Compare record times for all keys
    first_key = keys[0]
    all_identical = all(record_times[first_key].equals(record_times[key]) for key in keys[1:])
    
    if all_identical:
        print("All record times are identical.")
    else:
        print("Record times are not identical.")
        mismatches = []
        for i, key1 in enumerate(keys):
            for key2 in keys[i+1:]:
                if not record_times[key1].equals(record_times[key2]):
                    mismatches.append(f"Mismatch between {key1} ({len(record_times[key1])}) and {key2} ({len(record_times[key2])}).")
        
        if mismatches:
            print("Record time mismatches found:")
            for mismatch in mismatches:
                print(mismatch)
        else:
            print("No mismatches found in record times.")

    # Find the indices where the first and last keys differ
    diff_indices = record_times[keys[-1]] != record_times[first_key]

    # Print the differing times
    print(f"Times where {keys[-1]} differs from {first_key}: {len(diff_indices)}")
    # Uncomment the following lines to print the differing times
    # print(record_times[keys[-1]].where(diff_indices, drop=True))
    # print(record_times[first_key].where(diff_indices, drop=True))

    # Convert the record times to sets
    record_time_sets = {key: set(record_times[key].values) for key in keys}

    # Find intersections and differences between all pairs of keys
    for i, key1 in enumerate(keys):
        for key2 in keys[i+1:]:
            common = record_time_sets[key1] & record_time_sets[key2]
            distinct = record_time_sets[key1] ^ record_time_sets[key2]
            print(f"{key1} and {key2}: {len(common)} in common, {len(distinct)} distinct")
            # Print the distinct values between the first two keys
            distinct_values = record_time_sets[key1] ^ record_time_sets[key2]
            print(f"Distinct values between {key1} and {key2}:")
            for value in sorted(distinct_values):
                print(value)

    # Create the union of record_times
    union_record_times = set()
    for key in keys:
        union_record_times |= record_time_sets[key]

    return union_record_times

def calculate_sample_rate(data, name=None):
    """
    Calculate the mean and median sample rates for a given dataset or a dictionary of datasets based on time differences.
    This function determines the time variable in the dataset (e.g., 'RECORD_TIME', 'TIME', or 'SAMPLE_TIME'),
    computes the time differences between consecutive entries, and calculates the mean and median sample rates.

    Parameters
    -----------
        data (dict or xarray.Dataset): A dictionary of datasets or a single xarray dataset.
        name (str, optional): The key in the `data` dictionary corresponding to the dataset to analyze.
                              Required if `data` is a dictionary.

    Returns
    -----------
        tuple: A tuple containing:
            - mean_sample_rate (float): The mean sample rate in seconds.
            - median_sample_rate (float): The median sample rate in seconds.

    Raises
    ------
        ValueError: If the dataset does not contain a recognized time variable or if `name` is not provided for a dictionary input.
    """
    if isinstance(data, dict):
        if name is None:
            raise ValueError("When providing a dictionary of datasets, the 'name' parameter must be specified.")
        dataset = data[name]
    elif isinstance(data, xr.Dataset):
        dataset = data
    else:
        raise ValueError("Input must be either a dictionary of datasets or a single xarray.Dataset.")

    if 'RECORD_TIME' in dataset.dims:
        time_var = 'RECORD_TIME'
    elif 'TIME' in dataset.dims:
        time_var = 'TIME'
    elif 'SAMPLE_TIME' in dataset.dims:
        time_var = 'SAMPLE_TIME'
    else:
        raise ValueError("Dataset does not contain a recognized time variable.")

    data_array = dataset[time_var]
    # Calculate time differences in seconds
    time_diffs = np.diff(data_array.values).astype('timedelta64[s]').astype(int)
    
    # Calculate mean and median
    mean_sample_rate = np.mean(time_diffs)
    median_sample_rate = np.median(time_diffs)
    
    return mean_sample_rate, median_sample_rate