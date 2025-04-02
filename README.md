# fetchAZA

Repository for reading pressure data from the [Sonardyne Fetch AZA](https://www.sonardyne.com/product/fetch-aza-2/) into netCDF (xarray) format.

For documentation, see http://eleanorfrajka.github.io/fetchAZA.

## Background

Two Sonardyne Fetch AZA instruments were deployed at the western boundary of the [RAPID 26°N array](http://rapid.ac.uk), as a collaboration between the University of Hamburg in the [EPOC](http://epoc-eu.org) project, geophysicists [Kate Rychert](https://www.whoi.edu/profile/catherine.rychert/) and [Nick Harmon](https://directory.whoi.edu/profile/nicholas-harmon/) at WHOI, [Shane Elipot](https://selipot.github.io) at University of Miami and the RAPID array with the [RAPID evolution project](https://noc.ac.uk/projects/rapid-evolution).

These sensors have the possibility to self-correct the pressure drift, a common and known problem that occurs with sensing pressure in the ocean.  It does this by using 3 separate pressure sensors, and an internal volume within the sensor which is kept at a controlled pressure (near atmospheric pressure).  Of these three sensors, 1 sensor is rated to near-atmospheric pressure (the "Low" pressure sensor), and two are rated to deep pressures (the Digiquartz or "transfer" pressure, and the Keller or "ambient" pressure).  The Keller sensor reads seawater pressure, the low pressure reads in the controlled pressure volume, and the digiquartz sensor "transfers" between seawater pressure and the controlled pressure volume.  

At a set interval (starting frequent and with sample intervals increasing with time), the sensor runs through an AZA sequence.  During this sequence, it makes an instantaneous pressure measurement (sequence 1) with the Keller/Ambient and Transfer/Digiquartz measuring seawater pressure, and the low pressure sensor measuring in the controlled volume.  It then makes an AZA measurement which is provided as an average over 30 sections with the same quantities.  The transfer/Digiquartz sensor then switches to measure the pressure in the controlled pressure volume and the Fetch instrument makes a 30 second average of data in this configuration.  Finally, the transfer/Digiquartz sensor returns to measuring seawater pressure and another 30 second average is made.  At the end of the sequence, an instantaneous measurement is made by the three sensors.

See figure:
<img width="912" alt="image" src="https://github.com/user-attachments/assets/8be3df28-4b33-43bb-8d03-5fe1d9cb5aac" />

The idea is that the AZA sequence 3 will provide the offset or drift on the digiquartz sensor at increasing intervals:

$$dP_{offset,1}(t_i) = P_{low}(t_i)-P_{DQZ}(t_i)$$

where $i$ indicates that these are measured at AZA sampling intervals (roughly 150 samples over a 2 year deployment).  However, the Transfer/Digiquartz sensor and Ambient/Keller sensor also measure pressure at hourly intervals.  We will call this $j$.

A fit can be calculated against $dP_{offset,1}(t_i)$ and then linearly interpolated onto the hourly time vector $t_j$.  This can be used to correct the Transfer/Digiquartz sensor as

$$P_{DQZ,corr}(t_j) = P_{DQZ}(t_j) + dP_{offset,1}(t_j)$$

and to determine an offset between the Ambient/Keller and Transfer/Digiquartz as

$$dP_{offset,2}(t_j) = P_{DQZ}(t_j) - D_{KLR}(t_j)$$

This can then further be used to correct the Ambient/Keller pressure sensor as

$$P_{KLR,corr}(t_j) = P_{KLR}(t_j) + dP_{offset,1}(t_j) + dP_{offset,2}(t_j)\qquad .$$

Note that offset $dP_{offset,1}$ is available at AZA sampling intervals (roughly 150 over a 2 year deployment), whereas the other samples are hourly (15000 over a 2-year deployment).  

## Contributions

Currently the code is developed by one person.  Contributions welcome.
