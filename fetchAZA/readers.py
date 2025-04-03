import pandas as pd
import xarray as xr
import re
from collections import defaultdict
from fetchAZA import tools, utilities
import numpy as np

import glob
import re
import os
import datetime
import yaml
import pathlib
import logging
_log = logging.getLogger(__name__)

#------------------------------------------------------------
# Config files: Variables + variable attributes for archiving
#------------------------------------------------------------
# Set the directory for yaml files as the root directory + 'fetchAZA/config/'
script_dir = pathlib.Path(__file__).parent.absolute()
parent_dir = script_dir.parents[0]
rootdir = parent_dir
config_dir = os.path.join(rootdir, 'fetchAZA/config/')
# Vocabularies are loosely defined here
with open(config_dir + 'vocab_attrs.yaml', 'r') as file:
    vocab_attrs = yaml.safe_load(file)

record_types = {
    "AZA": "AZA averaged triple pressure sensor records",
    "AZS": "AZA starting point, simple triple pressure sensor record",
    "BAS": "Baseline Configuration",
    "BAT": "Battery",
    "BSL": "Baseline range",
    "DCS": "Doppler Current Sensor (Aanderaa model 4930R)",
    "DQZ": "Digiquartz Pressure & Temperature",
    "INC": "Inclinometer",
    "KLR": "Keller Pressure & Temperature",
    "MOD": "Module Settings",
    "PAG": "Page Record",
    "PIES": "PIES Record",
    "PNS": "Presens Pressure & Temperature",
    "QDN": "Quartzdyne Pressure & Temperature",
    "REP": "Log Repeat settings",
    "SLG": "Start Logging event",
    "SSP": "Sound Velocity",
    "STP": "Stop logging event",
    "TIM": "Time (RTC)",
    "TMP": "Temperature",
    "TPS": "TERPS Pressure",
    "TSO": "Time Sync Offset",
    "WUL": "Wake-Up Logging settings",
    "ERR": "Error code",
    "AZAseq": "AZS-AZA-AZA-AZA-AZS sequence of records"
}

def parse_header_data(lines, allowed_events=None):
    """
    Reads a CSV file and separates it into header and data lines, optionally filtering
    by allowed event types.

    Parameters
    ----------
    file_path : str
        Path to the CSV file.
    allowed_events : set, optional
        A set of allowed event types. If provided, only lines with the first field
        matching an allowed event type will be included. If None, all lines are included.

    Returns
    -------
    tuple
        A tuple containing:
        - header_lines (list of str): The header lines from the file.
        - data_lines (list of str): The data lines from the file.
    """
    header_lines = []
    data_lines = []
    data_section = False

    for line in lines:
        line = line.strip()
        if line.startswith("# Data"):
            data_section = True
            continue
        if not data_section:
            # Only keep header lines if allowed_events is None or the first field is in allowed_events.
            if line:
                first_field = line.split(',')[0].strip()
                if allowed_events is None or first_field in allowed_events:
                    header_lines.append(line)
        else:
            # Only keep data lines if allowed_events is None or the first field is in allowed_events.
            if line:
                first_field = line.split(',')[0].strip()
                if allowed_events is None or first_field in allowed_events:
                    data_lines.append(line)

    return header_lines, data_lines

def parse_column_name(col):
    """
    Extracts the column name and unit from a given column string.

    Parameters
    ----------
    col : str
        The column string, which may include a unit in parentheses or specific suffixes.

    Returns
    -------
    tuple
        A tuple containing the column name (str) and the unit (str or None).
    """
    match = re.match(r"(.*?)\((.*?)\)", col)  # Extract name and unit
    col_name = match.group(1).strip() if match else col.strip()
    unit = match.group(2).strip() if match else None

    # Check for specific units based on last two characters
    if col.endswith(" %"):
        col_name = col[:-2].strip()  # Remove " %" from the column name
        unit = "percent"
    elif col.endswith(" V"):
        col_name = col[:-2].strip()  # Remove " V" from the column name
        unit = "V"

    return col_name, unit

def process_header_lines(header_lines):
    """
    Processes the header lines to extract event headers and units.

    Parameters
    ----------
    header_lines : list of str
        List of header lines from the CSV file.

    Returns
    -------
    tuple
        A tuple containing:
        - event_headers (dict): A dictionary mapping event types to column headers.
        - event_units (dict): A dictionary mapping event types to column units.
    """
    event_headers = {}
    event_units = {}
    for line in header_lines:
        parts = [p.strip() for p in line.split(',')]
        event_type = parts[0]
        headers = parts[1:]

        clean_headers = []
        units = {}
        seen_columns = set()
        for col in headers:
            col_name, unit = parse_column_name(col)

            if col_name not in seen_columns:
                clean_headers.append(col_name)
                seen_columns.add(col_name)
                if unit:
                    units[col_name] = unit
            else:
                _log.info(f"Duplicate column name '{col_name}' found in event type '{event_type}'. Skipping.")
                continue

        event_headers[event_type] = clean_headers
        event_units[event_type] = units

    return event_headers, event_units

def csv_to_xarray(file_path):
    """
    Converts a CSV file into a dictionary of xarray Datasets, grouped by event type.
    The CSV file is expected to have a header section and a data section. The header section
    contains metadata about the columns, including event types, column names, and optional units.
    The data section contains the actual data values, with each row corresponding to an event type.
    The function processes the header to extract column names and units, and then groups the data
    by event type to create xarray Datasets. Units are assigned as attributes to the corresponding
    variables in the datasets.

    Parameters
    ----------
    file_path : str
        The path to the CSV file to be processed.

    Returns
    -------
    dict
        A dictionary where keys are event types (str) and values are xarray.Dataset objects
        containing the data for each event type. Each dataset includes variables with units
        assigned as attributes (if available).

    Notes
    -----
    - The header section should precede the data section in the CSV file.
    - The data section should start with a line containing "# Data".
    - Each row in the data section should begin with the event type, followed by the data values.
    - Column names in the header can include units in the format "Column Name (Unit)" or "Column Name %" or "Column Name V".
    """

    with open(file_path, 'r') as file:
        lines = file.readlines()
    
    # Extract header and data sections
    header_lines, data_lines = parse_header_data(lines)
    
    # Process header lines.
    # Each header line is assumed to have the form:
    #   EVENT,Col1,Col2,...,ColN
    # where some columns may include units in the form "Name (Unit)".
    event_headers, event_units = process_header_lines(header_lines)
    
    # Process data manually
    datasets = {}
    grouped_data = defaultdict(list)
    
    for line in data_lines:
        parts = line.split(',')
        event_type = parts[0]
        data_values = parts[1:]
        grouped_data[event_type].append(data_values)
    
    for event_type, data in grouped_data.items():
        if event_type in event_headers:
            event_df = pd.DataFrame(data, columns=event_headers[event_type][:len(data[0])])
            ds = xr.Dataset.from_dataframe(event_df)
            
            # Assign units as attributes
            for var in ds.data_vars:
                if var in event_units[event_type]:
                    ds[var].attrs['units'] = event_units[event_type][var]
            
            datasets[event_type] = ds
    
    return datasets

def csv_to_xarray_pattern(file_path, pattern=['AZS','AZA','AZA','AZA','AZS']):
    """
    Reads a CSV file with a header section and a data section (after a "# Data" line),
    then searches the data lines for contiguous groups of lines that match the given
    logging event pattern (by default: ['AZS', 'AZA', 'AZA', 'AZA', 'AZS']).
    
    For each matched group, two new columns are appended:
      - "Sample Num": increments for each matched group (starting at 1).
      - "Sequence Num": within the group, numbering from 1 to len(pattern).
    
    Only groups that match the pattern are processed; any data lines that do not belong
    to such a group are skipped.
    
    The function then groups rows by event type and creates an xarray.Dataset for each,
    using the header information (column names and units) for that event type.
    
    Parameters
    ----------
    file_path : str
        Path to the CSV file.
    pattern : list of str, optional
        A list of event types defining a valid group (default: ['AZS','AZA','AZA','AZA','AZS']).
    
    Returns
    -------
    dict
        A dictionary with keys for each event type found in matched groups and values
        that are xarray.Datasets built from the corresponding rows.
    """    
    # Read file lines.
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    _log.info(f"===================== Processing for pattern {pattern} ======================")

    # Extract header and data sections
    header_lines, data_lines = parse_header_data(lines, allowed_events=set(pattern))
    
    # Process header lines.
    # Each header line is assumed to have the form:
    #   EVENT,Col1,Col2,...,ColN
    # where some columns may include units in the form "Name (Unit)".
    event_headers, event_units = process_header_lines(header_lines)
    
    # Process data lines: scan for contiguous groups that exactly match the pattern.
    pattern_length = len(pattern)
    sample_num = 1
    index_num = 1
    # Collect rows for each event type.
    grouped_rows = defaultdict(list)
    
    i = 0
    while i <= len(data_lines) - pattern_length:
        group = data_lines[i:i+pattern_length]
        events_in_group = [line.split(',')[0].strip() for line in group]
        if events_in_group == pattern:
            # For each line in the matched group, split and add new columns.
            for seq_idx, line in enumerate(group):
                parts = [p.strip() for p in line.split(',')]
                # Append new columns.
                ev = parts[0]
                parts.append(str(index_num))
                parts.append(str(sample_num))       # "Sample Num"
                parts.append(str(seq_idx + 1))        # "Sequence Num"
                grouped_rows[ev].append(parts)
                index_num += 1
            sample_num += 1
            i += pattern_length  # Skip this group entirely.
        else:
            i += 1  # Slide the window
    
    # Build datasets for each event type present in the matched groups.
    datasets = {}
    for ev, rows in grouped_rows.items():
        if ev in event_headers:
            header = event_headers[ev]
            # Extend the header with the two new column names.
            header_extended = header + ["Index Num", "Sample Num", "Sequence Num"]
            # Remove the first column (event type) from the rows.
            rows = [row[1:] for row in rows]
            # Create a DataFrame from the rows.
            df = pd.DataFrame(rows, columns=header_extended)
            # Convert the DataFrame to an xarray Dataset.
            ds = xr.Dataset.from_dataframe(df)
            # Attach unit attributes if available.
            units = event_units.get(ev, {})
            for var in ds.data_vars:
                if var in units:
                    ds[var].attrs['units'] = units[var]
            ds.attrs['pattern'] = pattern

            datasets[ev] = ds

    
    return datasets

def combine_pattern(datasets, var_to_combine='INDEX_NUM'):
    """
    Combines multiple xarray datasets into a single dataset, adding relevant attributes.

    Parameters
    ----------
    datasets : dict
        A dictionary where keys are dataset names and values are xarray.Dataset objects.
    pattern : list
        The pattern used for grouping events.
    file_path : str
        The file path of the original CSV file.

    Returns
    -------
    xarray.Dataset
        A combined xarray dataset with added attributes.
    """

    for key, dataset in datasets.items():
        if var_to_combine in dataset:
            dataset = dataset.rename_dims({"index": "new_index"})
            dataset = dataset.rename_vars({"index": "new_index"})
            dataset = dataset.assign_coords(new_index=dataset[var_to_combine])
            datasets[key] = dataset
        else:
            _log.info(f"Variable '{var_to_combine}' not found in dataset '{key}'. Skipping renaming.")

    # Convert the datasets to a single xarray dataset
    combined_dataset = xr.merge(list(datasets.values()))

    # Add the attributes from ds in datasets to the combined dataset
    for ds in datasets.values():
        for attr, value in ds.attrs.items():
            if attr not in combined_dataset.attrs:
                combined_dataset.attrs[attr] = value

    if 1:
        # Remove variable Index Num
        if var_to_combine in combined_dataset:
            combined_dataset = combined_dataset.drop_vars(var_to_combine)
        # Rename dimensions to "index"
        combined_dataset = combined_dataset.rename_dims({"new_index": "index"})
        combined_dataset = combined_dataset.rename_vars({"new_index": "index"})
        combined_dataset = combined_dataset.assign_coords(index=combined_dataset["index"])

    return combined_dataset

def standardise_dataset(ds, replace_fill=True, fill_value=np.nan):
    """
    Standardizes the given dataset by:
      1. Converting constant variables to global attributes and removing them.
      2. Converting integer-like and float-like strings to numbers.
      3. Converting datetime strings to datetime64.
      4. Dropping variables marked for removal.
      5. Fixing object variables via utilities.reformat_object_vars.
      
    Additionally, for any variable of an integer type where the valid values should be >= 1,
    any 0 encountered is assumed to be a fill value. If `replace_fill` is True, those 0’s are
    replaced with `fill_value` (default –9999) and the variable is given an attribute '_FillValue'.

    Finally, for variables with "Serial" in their name that are effectively constant 
    (i.e. all non-fill values are the same), they are promoted to global attributes.
  
    Parameters
    ----------
    ds : xarray.Dataset
        The input dataset to be standardized.

    Returns
    -------
    xarray.Dataset
        The standardized dataset with updated variables and attributes.

    Notes
    -----
    - Variables with constant values are converted to global attributes and removed from the dataset.
    - Integer-like and float-like strings are converted to their respective numeric types.
    - Datetime strings are converted to pandas datetime64 format.
    - The function assumes the presence of a `utilities.reformat_object_vars` utility for handling object variables.
    """

    to_remove = []
    
    for var in list(ds.data_vars):
        values = ds[var].values
        dims = list(ds[var].dims)
     
        # Convert constant variables to global attributes
        unique_values = set(values)
        if len(unique_values) == 1:
            unique_value = next(iter(unique_values))
            if unique_value == "":
                to_remove.append(var)  # Mark for removal if empty
            else:
                ds.attrs[var] = unique_value  # Convert to global attribute
                to_remove.append(var)

        # Convert integer-like strings to integers
        elif all(re.match(r'^-?\d+$', str(v)) for v in values if v):
            ds[var] = ds[var].astype(int)
        
        # Convert float-like strings to floats
        elif all(re.match(r'^-?\d*\.\d+$', str(v)) for v in values if v):
            ds[var] = ds[var].astype(float)
        
        # Convert datetime strings to datetime64
        if all(re.match(r'\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}', str(v)) for v in values if v):
            try:
                rt_values = pd.to_datetime(values, errors='raise')
            except Exception:
                rt_values = pd.to_datetime(values, errors='coerce')
            ds = ds.drop_vars(var)
            ds[var] = (dims, rt_values)

    # Drop marked variables
    ds = ds.drop_vars(to_remove)

    # Fix object variables
    ds = utilities.reformat_object_vars(ds)

    # Handle fill values for integer variables
    if replace_fill:
        for var in ds.data_vars:
            # Check if the variable is of an integer type.
            if np.issubdtype(ds[var].dtype, np.integer):
                values = ds[var].values
                # Consider this variable a candidate if it contains any zeros
                # and if the smallest nonzero value is >= 1.
                nonzero = values[values != 0]
                if nonzero.size > 0 and nonzero.min() >= 1 and np.any(values == 0):
                    # Replace zeros with fill_value
                    new_values = np.where(values == 0, fill_value, values)
                    ds[var].values = new_values
                    # Add the _FillValue attribute
                    ds[var].attrs['_FillValue'] = fill_value
    
    # Additional pass: For variables with "Serial" in the name,
    # if the only variation is the fill value, promote them to global attributes.
    for var in list(ds.data_vars):
        if "Serial" in var:
            _log.info(f"Checking variable '{var}' for constant values.")
            values = ds[var].values
            # Create a set of unique values.
            unique_vals = set(values)
            # If the variable has a _FillValue attribute, remove that value from the set.
            if '_FillValue' in ds[var].attrs:
                unique_vals.discard(ds[var].attrs['_FillValue'])
            # If, after discarding fill values, only one unique value remains, then treat it as constant.
            if len(unique_vals) == 1:
                const_val = unique_vals.pop()
                _log.info(f"Variable '{var}' is constant with value '{const_val}'. Promoting to global attribute.")
                ds.attrs[var] = const_val
                ds = ds.drop_vars(var)

    # Check for attributes with value -9999
    attr_to_delete = []
    for attr, value in ds.attrs.items():
        if isinstance(value, (int, float)) and value == -9999:
            _log.info(f"Attribute '{attr}' has a fill value of -9999. Removing.")
            attr_to_delete.append(attr)
        elif isinstance(value, str) and value[:5] == "-9999":
            _log.info(f"Attribute '{attr}' has a string fill value of '-9999'. Removing.")
            attr_to_delete.append(attr)
    for attr in attr_to_delete:
        del ds.attrs[attr]

    # Make variable names uppercase and replace spaces with underscores
    for var in ds.data_vars:
        new_var = var.upper().replace(" ", "_")
        ds = ds.rename_vars({var: new_var})


    # Change floats to integer where possible
    ds = utilities.convert_float_to_int(ds)

    # Set the best dtype for each variable
    ds = utilities.set_best_dtype(ds)

    return ds

def load_netcdf_datasets(data_path, file_root, keys=None):
    """
    Load netCDF files matching the given file_root and optional keys from the specified data_path into a dictionary of xarray datasets.

    Parameters
    ----------
    data_path : str 
        The directory path where the netCDF files are located.
    file_root : str 
        The root name of the files to match.
    keys : list of str, optional
        A list of keys to filter the files. Only files containing these keys in their names will be loaded.
        If None, all matching files will be loaded.

    Returns
    -------
    dict 
        A dictionary where keys are dataset names and values are xarray datasets.
    """
    # Find matching netCDF files
    search_dir = os.path.join(data_path, f"{file_root}*.nc")
    matching_files = glob.glob(search_dir)
    print(search_dir)
    # Filter files based on keys if provided
    if keys is not None:
        matching_files = [
            file for file in matching_files
            if any(f"{file_root}_{key}" in os.path.basename(file) for key in keys)
        ]

    # Load the matching netCDF files into a dictionary of xarray datasets
    datasets_loaded = {}
    for file in matching_files:
        print(file)
        dataset_name = os.path.basename(file).split('_')[-1].split('.')[0]
        datasets_loaded[dataset_name] = xr.open_dataset(file)


    _log.info(f"Loaded {len(datasets_loaded)} datasets from files matching '{file_root}' with keys {keys}.")

    return datasets_loaded



def read_csv_to_xarray(input_file, deploy_date=None, recovery_date=None, pattern=['AZS','AZA','AZA','AZA','AZS']):
    """
    Processes a CSV file and converts it into NetCDF-compatible datasets.
    This function reads data from the input CSV file, processes it into xarray datasets
    by separating the data into datasets corresponding to each logging event type,
    standardizes the datasets, and then processes datasets that match a specified
    sequence pattern. The matched datasets are further combined into an additional
    xarray dataset.

    Parameters
    ----------
    input_file : str
        The path to the input CSV file.
    pattern : list of str, optional
        A list of event types defining a valid group (default: ['AZS', 'AZA', 'AZA', 'AZA', 'AZS']).

    Returns
    -------
    dict
        A dictionary of standardized xarray datasets. The keys are event types, and the values
        are the corresponding datasets. An additional dataset with the key 'AZAseq' contains
        the combined dataset created from patterns in the input CSV file.

    Notes
    -----
    - The function first processes the input file into individual datasets based on event types.
    - It then standardizes each dataset by converting constant variables to attributes, handling
      fill values, and ensuring proper data types.
    - The function identifies and processes groups of rows matching the specified pattern, adding
      sequence-related metadata.
    - The combined dataset ('AZAseq') includes additional attributes describing the sequence pattern.
    """
    datasets = csv_to_xarray(input_file)
    datasets2 = {}
    datasets4 = {}
    for key in datasets:
        _log.info(f"------------------------ Processing dataset '{key}' ------------------------")
        datasets2[key] = standardise_dataset(datasets[key])

    datasets3 = csv_to_xarray_pattern(input_file, pattern)
    for key in datasets3:
        datasets4[key] = standardise_dataset(datasets3[key])
    combined_ds = combine_pattern(datasets4)

    if pattern == ['AZS', 'AZA', 'AZA', 'AZA', 'AZS']:
        combined_ds['SEQUENCE_NUM'].attrs['description'] = (
            '1: Transfer measures ambient (single), '
            '2: Calibration start point (settled), transfer measures ambient (averaged pressure value over 30 seconds), '
            '3: Calibration zero point (settled), transfer measures low (averaged pressure value over 30 seconds), '
            '4: Calibration end point (settled), transfer measures ambient (averaged pressure value over 30 seconds), '
            '5: Transfer measures ambient (single)'
        )

    datasets2['AZAseq'] = combined_ds

    # Remove empty fill values
    for key in datasets2:
        ds = datasets2[key]
        _, empty_string_attrs, empty_string_attr_vars = utilities.netcdf_compliancer(ds)
        for attr in empty_string_attrs:
            if attr in ds.attrs:
                del ds.attrs[attr]
                _log.warning(f"Attribute '{attr}' has an empty string value. Removing it.")
        for var, attrs in empty_string_attr_vars.items():
            for attr in attrs:
                if attr in ds[var].attrs:
                    del ds[var].attrs[attr]
                    _log.warning(f"Attribute '{attr}' of variable '{var}' has an empty string value. Removing it.")

    return  datasets2


def data_overview(data_path, base_filename, extracted_parts, output_file_path=None):
    """
    Reads data details from a directory and prints or writes them to a file.

    Parameters
    ----------
    data_path : str
        The path to the data directory.
    base_filename : str
        The base filename for the data files.
    extracted_parts : list
        A list of parts to be extracted from the base filename.
    output_file_path : str, optional
        The path to the output file. If None, prints to standard output.

    Returns
    -------
    None
    """
    timevar = 'RECORD_TIME'

    def write_output(line):
        if output_file_path:
            f.write(line + '\n')
        else:
            print(line)

    with open(output_file_path, 'w') if output_file_path else None as f:
        for part in extracted_parts:
            print(f"Processing part: {part}")
            filename = f"{base_filename}_{part}.nc"
            write_output(f"{part}: {record_types[part]})")
            file = os.path.join(data_path, filename)
            dataset = xr.open_dataset(file)
            start_time = dataset[timevar].min().values
            end_time = dataset[timevar].max().values
            num_data_points = len(dataset[timevar])
            time_diffs = np.diff(dataset[timevar].values).astype('timedelta64[s]').astype(int)
            avg_temporal_resolution = np.mean(time_diffs) / (24 * 3600)  # Convert seconds to decimal days

            write_output(f"Filename: {os.path.basename(file)}")
            write_output(f"Start Time: {start_time}")
            write_output(f"End Time: {end_time}")
            write_output(f"Number of Data Points: {num_data_points}")
            write_output(f"Average Temporal Resolution: {avg_temporal_resolution:.3f} days")

            write_output("Variables with Units:")
            for var in dataset.data_vars:
                units = dataset[var].attrs.get('units', '')
                long_name = dataset[var].attrs.get('long_name', 'No long_name')
                if np.issubdtype(dataset[var].dtype, np.number):
                    if np.issubdtype(dataset[var].dtype, np.timedelta64):
                        d1 = dataset[var].values / np.timedelta64(1, 's')
                        avg_value = d1.mean()
                        max_value = d1.max()
                        min_value = d1.min()
                        std_value = d1.std()
                        units = 'seconds'
                    else:
                        avg_value = dataset[var].mean().values
                        max_value = dataset[var].max().values
                        min_value = dataset[var].min().values
                        std_value = dataset[var].std().values
                    write_output(f"  - {var} ({long_name}): mean({avg_value:.3f}), min({min_value:.3f})--max({max_value:.3f}), std({std_value:.3f}) {units}")
                else:
                    write_output(f"  - {var} ({long_name}): {units}")
            write_output("")

    if output_file_path:
        print(f"Overview written to {output_file_path}")