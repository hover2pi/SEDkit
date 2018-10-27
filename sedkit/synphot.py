#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Joe Filippazzo, jfilippazzo@stsci.edu
#!python3
"""
A module to calculate synthetic photometry
"""
import glob
import itertools
import os
from pkg_resources import resource_filename
import warnings

import astropy.table as at
import astropy.constants as ac
import astropy.units as q
import astropy.io.ascii as asc
import astropy.io.votable as vo
from bokeh.plotting import figure, show
import numpy as np
import pysynphot as ps
# Area of the telescope has to be in centimeters2
# ps.setref(area=250000.)


BANDPASSES = [i.split('/')[-1] for i in glob.glob(resource_filename('sedkit', 'data/bandpasses/*'))]
BANDPASS_PATH = resource_filename('sedkit', 'data/bandpasses/')
warnings.simplefilter('ignore')


EXTINCTION = {'PS1.g':3.384, 'PS1.r':2.483, 'PS1.i':1.838, 'PS1.z':1.414, 'PS1.y':1.126,
              'SDSS.u':4.0, 'SDSS.g':3.384, 'SDSS.r':2.483, 'SDSS.i':1.838, 'SDSS.z':1.414,
              '2MASS.J':0.650, '2MASS.H':0.327, '2MASS.Ks':0.161}

# A dict of BDNYCdb band names to work with sedkit
PHOT_ALIASES = {'2MASS_J': '2MASS.J', '2MASS_H': '2MASS.H',
                '2MASS_Ks': '2MASS.Ks', 'WISE_W1': 'WISE.W1',
                'WISE_W2': 'WISE.W2', 'WISE_W3': 'WISE.W3',
                'WISE_W4': 'WISE.W4', 'IRAC_ch1': 'IRAC.I1',
                'IRAC_ch2': 'IRAC.I2', 'IRAC_ch3': 'IRAC.I3',
                'IRAC_ch4': 'IRAC.I4', 'SDSS_u': 'SDSS.u',
                'SDSS_g': 'SDSS.g', 'SDSS_r': 'SDSS.r',
                'SDSS_i': 'SDSS.i', 'SDSS_z': 'SDSS.z',
                'MKO_J': 'NSFCam.J', 'MKO_Y': 'Wircam.Y',
                'MKO_H': 'NSFCam.H', 'MKO_K': 'NSFCam.K',
                "MKO_L'": 'NSFCam.Lp', "MKO_M'": 'NSFCam.Mp',
                'Johnson_V': 'Johnson.V', 'Cousins_R': 'Cousins.R',
                'Cousins_I': 'Cousins.I', 'FourStar_J': 'FourStar.J',
                'FourStar_J1': 'FourStar.J1', 'FourStar_J2': 'FourStar.J2',
                'FourStar_J3': 'FourStar.J3', 'HST_F125W': 'WFC3_IR.F125W'}


class Bandpass(ps.ArrayBandpass):
    def __init__(self, name):
        """
        Creates a pysynphot bandpass with the given filter

        Parameters
        ----------
        name: str
            The filter name
        """
        # Look for the file
        if name in BANDPASSES:
            file = glob.glob(resource_filename('sedkit', 'data/bandpasses/{}'.format(name)))[0]

        else:
            raise IOError("No bandpass named {} in {}".format(name, BANDPASS_PATH))

        # Parse the XML file
        vot = vo.parse_single_table(file)
        wave, thru = np.array([list(i) for i in vot.array]).T

        # Convert um to A if necessary
        if wave[0]<100:
            wave *= 10000
        self._wave_units = q.AA

        # Inherit from ArrayBandpass
        super().__init__(wave=wave, throughput=thru, waveunits='Angstrom', name=name)

        # Set the effective wavelength
        self.eff = self.pivot()*q.AA

        # Parse the SVO filter metadata
        for p in [str(p).split() for p in vot.params]:

            # Extract the key/value pairs
            key = p[1].split('"')[1]
            val = p[-1].split('"')[1]

            # Do some formatting
            if p[2].split('"')[1]=='float' or p[3].split('"')[1]=='float':
                val = float(val)

            else:
                val = val.replace('b&apos;','').replace('&apos','').replace('&amp;','&').strip(';')

            # Set the attribute
            if key!='Description':
                setattr(self, key, val)

        # Convert Jy zero point to Flam units
        self._zero_point = (self.ZeroPoint*q.Jy*ac.c/self.eff**2).to(q.erg/q.s/q.cm**2/q.AA)

        # Try to get the extinction vector R from Green et al. (2018)
        self.ext_vector = EXTINCTION.get(name, 0)


    def overlap(self, other):
        """
            |---------- other ----------|
               |------ self ------|

        Examples of partial overlap::

            |---------- self ----------|
               |------ other ------|

            |---- other ----|
               |---- self ----|

            |---- self ----|
               |---- other ----|

        Examples of no overlap::

            |---- self ----|  |---- other ----|

            |---- other ----|  |---- self ----|

        Parameters
        ----------
        other: sedkit.spectrum.Spectrum
            The other spectrum

        Returns
        -------
        ans : {'full', 'partial', 'none'}
            Overlap status.

        """
        swave = self.wave[np.where(self.throughput != 0)]*self.wave_units
        s1, s2 = swave.min(), swave.max()

        owave = other[0]
        o1, o2 = owave.min(), owave.max()

        if (s1 >= o1 and s2 <= o2):
            ans = 'full'

        elif (s2 < o1) or (o2 < s1):
            ans = 'none'

        else:
            ans = 'partial'

        return ans


    def plot(self, fig=None):
        """Plot the throughput"""
        if fig is None:
            fig = figure()

        # Plot
        fig.line(self.wave, self.throughput)

        show(fig)

    @property
    def wave_units(self):
        """A property for wave_units"""
        return self._wave_units

    @wave_units.setter
    def wave_units(self, wave_units):
        """A setter for wave_units

        Parameters
        ----------
        wave_units: astropy.units.quantity.Quantity
            The astropy units of the SED wavelength
        """
        # Make sure it's a quantity
        if not isinstance(wave_units, (q.core.PrefixUnit, q.core.Unit, q.core.CompositeUnit)):
            raise TypeError('wave_units must be astropy.units.quantity.Quantity')

        # Make sure the values are in length units
        try:
            wave_units.to(q.um)
        except:
            raise TypeError("wave_units must be a unit of length, e.g. 'um'")

        # Update the wavelength array
        self.convert(str(wave_units))

        # Update the effective wavelength
        self.eff = self.eff.to(wave_units)

        # Set the wave_units!
        self._wave_units = wave_units


    @property
    def zero_point(self):
        return self._zero_point


    @property
    def zp_units(self):
        """A getter for the zeropoint units"""
        return self._zp_units


    @zp_units.setter
    def zp_units(self, zp_units):
        """
        Set the flux units of the zeropoint

        Parameters
        ----------
        zp_units: str, astropy.units.core.PrefixUnit
            The units of the zeropoint flux density
        """
        # Convert to units
        self._zero_point = self.zero_point.to(zp_units)
        self._zp_units = zp_units


def mag2flux(mag, bandpass, units=q.erg/q.s/q.cm**2/q.AA):
    """
    Caluclate the flux for a given magnitude

    Parameters
    ----------
    mag: float, sequence
        The magnitude or (magnitude, uncertainty)
    bandpass: pysynphot.spectrum.ArraySpectralElement
        The bandpass to use
    units: astropy.unit.quantity.Quantity
        The unit for the output flux
    """
    if isinstance(mag, float):
        mag = mag, np.nan

    # Calculate the flux density
    f = (bandpass.zero_point*10**(mag[0]/-2.5)).to(units)
    sig_f = (f*mag[1]*np.log(10)/2.5).to(units)

    return f, sig_f


def flux2mag(flx, bandpass):
    """Calculate the magnitude for a given flux

    Parameters
    ----------
    flx: astropy.units.quantity.Quantity, sequence
        The flux or (flux, uncertainty)
    bandpass: pysynphot.spectrum.ArraySpectralElement
        The bandpass to use
    """
    if isinstance(flx, (q.core.PrefixUnit, q.core.Unit, q.core.CompositeUnit)):
        flx = flx, np.nan*flx.unit

    # Calculate the magnitude
    eff = bandpass.eff
    zp = bandpass.zero_point
    flx, unc = flx
    unit = flx.unit

    # Convert energy units to photon counts
    flx = (flx*(eff/(ac.h*ac.c)).to(1/q.erg)).to(unit/q.erg)
    zp = (zp*(eff/(ac.h*ac.c)).to(1/q.erg)).to(unit/q.erg)
    unc = (unc*(eff/(ac.h*ac.c)).to(1/q.erg)).to(unit/q.erg)

    # Calculate magnitude
    m = -2.5*np.log10((flx/zp).value)
    m_unc = (2.5/np.log(10))*(unc/flx).value

    return m, m_unc


def mag_table(spectra=None, bandpasses=BANDPASSES, models='phoenix', jmag=10, save=None):
    """
    Calculate the magnitude of all given spectra in all given bandpasses

    Parameters
    ----------
    spectra: sequence
        A sequence of [Teff, FeH, logg] values 
    bandpasses: sequence
        A list of bandpass objects
    models: str
        The model grid to use
    jmag: float
        The J magnitude to renormalize to
    save: str
        The file to save the results to
    """
    # Get the J bandpass
    jband = ps.ObsBandpass('j')

    # Make the list of spectra
    if spectra==None:
        teff_range = np.arange(2000, 2550, 50)
        feh_range = np.arange(-0.5, 1.0, 0.5)
        logg_range = np.arange(4.5, 5.5, 0.5)
        ranges = [teff_range, feh_range, logg_range]
        spectra = list(itertools.product(*ranges))

    # Make the list of bandpasses if given a directory
    if isinstance(bandpasses, str) and os.path.exists(bandpasses):

        # Get the files
        files = glob.glob(os.path.join(bandpasses,'*'))
        bandpasses = [(i.split('.')[-3],i.split('.')[-4].split('_')[-1]) for i in files]

    # Make the list of bandpasse
    if isinstance(bandpasses, (list,tuple)):
        bandpasses = [Bandpass(filt, inst) for filt, inst in bandpasses]

    else:
        print("Please provide a list of (filter,instrument) tuples or a directory of filters.")
        return

    # An empty list of tables
    tables = []

    print("Calculating synthetic mags for...")

    # For each set of params...
    for n, (teff, feh, logg) in enumerate(spectra):

        # ...get the spectrum...
        spectrum = ps.Icat(models, teff, feh, logg)

        # Renormalize the spectrum
        try:
            spectrum = spectrum.renorm(jmag, 'vegamag', jband)
            print((teff, feh, logg))

        except:
            print('Error:',(teff, feh, logg))
            continue

        # Make the table for this spectrum
        table = at.Table([[teff], [feh], [logg]], names=('teff','feh','logg'))

        # ...and calculate the magnitude...
        for bp in bandpasses:

            # ...in each bandpass...
            mag = synthetic_magnitude(spectrum, bp)

            # ...and add the mag to the list
            table[bp.name] = [mag]

        tables.append(table)

    # Stack all the tables
    mag_table = at.vstack(tables)

    # Save to file
    if os.path.exists(os.path.dirname(save)) and '.' in save:

        if not save.endswith('.csv'):
            save = save.split('.')[0]+'.csv'

        mag_table.write(save, format='ascii.csv', overwrite=True)

    # Or return
    else:
        return mag_table

def color_color_plot(colorx, colory, table, **kwargs):
    """
    Make a color-color plot for the two bands

    Parameters
    ----------
    colorx: str
        Two bandpass names delimited with a '-' sign for the x axis, e.g. 'F115W-F356W'
    colory: str
        Two bandpass names delimited with a '-' sign for the y axis, e.g. 'F430M-F480M'
    table: str, astropy.table.Table
        An astropy table or path to a CSV file of magnitudes
    """
    # Get teh table of data
    if os.path.isfile(table):
        table = asc.read(table)

    # Get the bands to retrieve
    bandx1, bandx2 = colorx.split('-')
    bandy1, bandy2 = colory.split('-')

    # Make a new table with the calculated colors
    table[colorx] = table[bandx1]-table[bandx2]
    table[colory] = table[bandy1]-table[bandy2]

    # Filter by parameter
    for param in ['teff', 'logg', 'feh']:
        if isinstance(kwargs.get(param), (int, float)):
            table = table[table[param]==kwargs[param]]

    # Plot it
    markers = ['o','s','d','x','v']
    for i,g in enumerate(np.unique(table['logg'])):
        tab = table[table['logg']==g]
        plt.scatter(tab[colorx], tab[colory], c=tab['teff'], marker=markers[i%len(markers)], label='logg = {}'.format(g))

    plt.colorbar()
    plt.legend(loc=0)