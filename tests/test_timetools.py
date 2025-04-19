import pathlib
import sys

script_dir = pathlib.Path(__file__).parent.absolute()
parent_dir = script_dir.parents[0]
sys.path.append(str(parent_dir))

import pandas as pd
from fetchAZA import timetools


def test_increment_duplicate_time():
    times = pd.Series(pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-02"]))
    new_times, count = timetools.increment_duplicate_time(times)
    assert count == 1
    assert len(set(new_times)) == 3
