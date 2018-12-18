# -*- coding: utf-8 -*-
"""
Created on Thu Nov 29 14:51:33 2018

@author: Tim Bauer (tim.bauer@gmx.us)

Description:

This is a morphological filter to extract ground level points from unfiltered
elevation rasters. It can be used to generate a DTM from an unclassified LIDAR
pointcloud, assuming that this pointcloud has already been turned into an evenly
spaced minimum elevation raster (picking minimum z for each cell) which is used
as input.

The algorithm is build on the methodology described in Pingle, Clarke, McBride
(2013). The main filtering proceedure is comparison of the input raster to a
morphological opening of that input raster with a stepwise increasing window.
It discards non-ground points if the difference between original point and
opening exceeds a slope threshold. The algorithm is thus similar to the one
described by Vosselmann (2000) which utilizes morphological erosion. The
advantage of using opening instead of erosion is the improved preservation of
distinct ground features such as tunnels or bridges.

The algorithm proceeds in two steps: First an initial filtering with a
conservative slope threshold (parameter: initial_cutoff) removes the most
prominent artefacts. The resulting provisional surface is interpolated with a
nearest neighbor algorithm. On this interpolated surface the z component of the
normal vectors is estimated for each cell and then averaged out
(parameter: average_sigma) in order to receive an average slope for each area.
This average slope is transformed into a scaling matrix which serves as slope
cutoff in the second iteration. This way it is ensured that the subsequent
round of filtering uses a maximal slope cutoff in evenly sloped areas, while
performing a more moderate filtering along slopes. The parameter scaling_factor
times 0.1 is then equal to the maximum slope tolerated in steep areas.

The resulting raster is finally filtered for single pixel holes which can be
assumed to be measurement errors.


Sources:

Pingle, Clarke, McBride (2013). "An Improved Simple Morphological Filter for the
    Terrain Classification of Airborne LIDAR Data". ISPRS Journal of Photogrammetry
    and Remote Sensing, 77, 21-30.

Vosselman, G. (2000). Slope based filtering of laser altimetry data. International
    Archives of Photogrammetry and Remote Sensing, 33(B3/2; PART 3), 935-942.
"""


import numpy as np
from scipy import ndimage
from .MyRasterTools import slopeEstimation, nnInterpolation, tinInterpolation

################################################################################
# The Filter Class
"""
# Parameters
parameters = {'c' : 0.5,                     # The cell size of the input raster
              'kernel_radius' : 2,           # The kernel size of the first filter iteration
              'initial_cutoff' : 0.4,        # The slope threshold of the first filter iteration
              'average_sigma' : 7,           # The gaussian function used to average out local slope
              'dh0' : 0.1,                   # The slope threshold for flat areas
              'hole_cutoff' : -0.2}          # Threshold for individual holes beneath median in 3x3 kernel
"""
class ProgressiveMorphologicalFilter():
    def __init__(self, input_raster, parameters):
        for key, value in parameters.items():
            setattr(self, key, value)
        
        #Interpolate nan
        self.input_raster = tinInterpolation(input_raster)
        
    # To get rid of holes
    def medianFilter(self, input_raster):
        filter_raster = nnInterpolation(input_raster)
        median = ndimage.median_filter(filter_raster, size = (3,3))
        output = np.where(filter_raster - median < self.hole_cutoff, np.nan, input_raster)
        return output

    # The main filter algorithm
    def progressiveMorphologicalfilter(self, input_raster, slope_threshold):
        
        input_raster = tinInterpolation(input_raster)
        last_surface = np.copy(input_raster)
        
        #The mask we use to indicate non-ground points
        mask = np.zeros(input_raster.shape)
        final = int(self.kernel_radius/self.c)
        k = 1
        while k <= final:
            #Generate window
            w = k*2 + 1
            window = (w,w)
            #Opening
            this_surface = ndimage.morphology.grey_opening(last_surface, size = window)
            #Increasing maxdh by footprint radius in cells
            dhmax = np.sqrt(k**2 + k**2) * self.c * slope_threshold
            #Only mask those below cutoff
            mask = np.where(input_raster - this_surface > dhmax, 1, mask)      #Could also subtract from last surface
            last_surface = this_surface
            k += 1          #one step further

        output = np.where(mask, np.nan, input_raster)
        return output

    def scalingMatrix(self, input_raster):
        z = slopeEstimation(input_raster, self.c)
        # assume nans are even surfaces
        z = np.where(np.isnan(z), 0, z)
        # average slope out with wide gaussian filter
        average_slope = ndimage.gaussian_filter(z, self.average_sigma)
        average_slope += self.dh0
        return average_slope


    def filter(self):
        self.hole_filtered = self.medianFilter(self.input_raster)
        self.initial_filtered = self.progressiveMorphologicalfilter(self.hole_filtered, self.initial_cutoff)
        self.scaling_matrix = self.scalingMatrix(self.initial_filtered)
        self.final_filtered = self.progressiveMorphologicalfilter(self.hole_filtered, self.scaling_matrix)
        return self.final_filtered
