About Fetch AZA
===============

Two Sonardyne Fetch AZA instruments have the possibility to self-correct the pressure drift, a common and known problem that occurs with sensing pressure in the ocean. It does this by using three separate pressure sensors and an internal volume within the sensor, which is kept at a controlled pressure (near atmospheric pressure). Of these three sensors, one sensor is rated to near-atmospheric pressure (the "Low" pressure sensor), and two are rated to deep pressures (the Digiquartz or "transfer" pressure, and the Keller or "ambient" pressure). The Keller sensor reads seawater pressure, the low-pressure sensor reads in the controlled pressure volume, and the Digiquartz sensor "transfers" between seawater pressure and the controlled pressure volume.

At a set interval (starting frequent and with sample intervals increasing with time), the sensor runs through an AZA sequence. During this sequence, it makes an instantaneous pressure measurement (sequence 1) with the Keller/Ambient and Transfer/Digiquartz measuring seawater pressure, and the low-pressure sensor measuring in the controlled volume. It then makes an AZA measurement, which is provided as an average over 30 sections with the same quantities. The Transfer/Digiquartz sensor then switches to measure the pressure in the controlled pressure volume, and the Fetch instrument makes a 30-second average of data in this configuration. Finally, the Transfer/Digiquartz sensor returns to measuring seawater pressure, and another 30-second average is made. At the end of the sequence, an instantaneous measurement is made by the three sensors.

See figure:

.. figure:: _static/transfer-table.png
    :alt: Figure: Transfer Table

    Figure: Transfer Table

The idea is that the AZA sequence 3 will provide the offset or drift on the Digiquartz sensor at increasing intervals:

.. math::

     dP_{offset,1}(t_i) = P_{low}(t_i)-P_{DQZ}(t_i)

where :math:`i` indicates that these are measured at AZA sampling intervals (roughly 150 samples over a 2-year deployment). However, the Transfer/Digiquartz sensor and Ambient/Keller sensor also measure pressure at hourly intervals. We will call this :math:`j`.

A fit can be calculated against :math:`dP_{offset,1}(t_i)` and then linearly interpolated onto the hourly time vector :math:`t_j`. This can be used to correct the Transfer/Digiquartz sensor as:

.. math::

     P_{DQZ,corr}(t_j) = P_{DQZ}(t_j) + dP_{offset,1}(t_j)

and to determine an offset between the Ambient/Keller and Transfer/Digiquartz as:

.. math::

     dP_{offset,2}(t_j) = P_{DQZ}(t_j) - D_{KLR}(t_j)

This can then further be used to correct the Ambient/Keller pressure sensor as:

.. math::

     P_{KLR,corr}(t_j) = P_{KLR}(t_j) + dP_{offset,1}(t_j) + dP_{offset,2}(t_j)

Note that offset :math:`dP_{offset,1}` is available at AZA sampling intervals (roughly 150 over a 2-year deployment), whereas the other samples are hourly (15,000 over a 2-year deployment).
