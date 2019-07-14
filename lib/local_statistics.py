import numpy as np
from skimage.util.shape import view_as_windows
from skimage.util import pad

from raster_to_array import raster_to_array
from array_to_raster import array_to_raster
import numba
from numba import jit


@numba.jit(nopython=True, fastmath=True)
def rolling_window(arr, shape):
    d2x = arr.shape[0] - shape[0] + 1
    d2y = arr.shape[1] - shape[1] + 1
    s = (d2x, d2y, shape[0], shape[1])

    strides = arr.strides + arr.strides
    return np.lib.stride_tricks.as_strided(arr, shape=s, strides=strides)


@numba.jit(nopython=True, parallel=True, fastmath=True)
def create_view(arr, shape=(3, 3)):
    r_extra = int(shape[0] / 2)
    c_extra = int(shape[1] / 2)

    out = np.empty((
        arr.shape[0] + 2 * r_extra,
        arr.shape[1] + 2 * c_extra,
    ), dtype=arr.dtype)

    out.fill(np.nan)

    out[r_extra:-r_extra, c_extra:-c_extra] = arr

    return rolling_window(out, shape)


@numba.jit(nopython=True, parallel=True, fastmath=True)
def _local_statistics(raster_arr, radius=1):
    if radius == 1:
        view_shape = (3, 3)
    else:
        view_size = (3 * radius) - 1
        view_shape = (view_size, view_size)

    view = create_view(raster_arr, view_shape)

    new_array = np.empty(raster_arr.shape, dtype=raster_arr.dtype)

    for index, value in np.ndenumerate(raster_arr):
        # new_array[index] = np.nanstd(view[index])
        new_array[index] = np.mean(view[index])
        # new_array[index] = np.quantile(view[index], 0.75)

    return new_array


def local_statistics(in_raster, out_raster=None, radius=1):
    '''
        Calculates the local standard deviation in a given radius. Output is a dateframe.

        Example:
            base = 'D:\\PhD\\Projects\\SavingsAtTheFrontiers\\data\\s2\\mosaic\\'
            b8 = f'{base}mosaic_R10m_B04.tif'
            b8_arr = raster_to_array(b8)

            rad3 = local_statistics(b8, radius=3)
            rad2 = local_statistics(b8, radius=2)
            rad1 = local_statistics(b8, radius=1)

            avg_std = np.divide(np.add(np.add(rad3, rad2), rad1), 3)
            array_to_raster(avg_std.astype('float32'), reference_raster=b8, out_raster=f'{base}mosaic_R10m_B04_STD3.tif')
    '''
    raster_arr = raster_to_array(in_raster)
    stats = _local_statistics(raster_arr, radius)

    if out_raster is None:
        return stats
    else:
        return array_to_raster(stats, reference_raster=in_raster, out_raster=out_raster)


def local_statistics2(in_raster, out_raster=None, radius=1):
    '''
        Calculates the local standard deviation in a given radius. Output is a dateframe.

    '''

    raster_arr = raster_to_array(in_raster)

    padded = np.pad(raster_arr, radius, 'edge')

    if radius is 1:
        window = view_as_windows(padded, 3, 1)
    else:
        if radius % 2 is 0:
            rad = 3 + radius
        else:
            rad = 3 + radius + 1

        window = view_as_windows(padded, rad, 1)

    stats = np.max(window, axis=(2, 3))

    if out_raster is None:
        return stats
    else:
        return array_to_raster(stats, reference_raster=in_raster, out_raster=out_raster)
