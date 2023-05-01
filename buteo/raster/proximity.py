"""
### Calculate distances on a raster. ###

Module to calculate the distance from a pixel value to other pixels.
"""

# Standard library
import sys; sys.path.append("../../")
from uuid import uuid4
from typing import Union, List

# External
import numpy as np
from osgeo import gdal

# Internal
from buteo.utils import utils_base, utils_gdal
from buteo.raster import core_raster
from buteo.raster.borders import add_border_to_raster



def calc_proximity(
    input_rasters: List,
    target_value: Union[int, float] = 1,
    unit: str = "GEO",
    out_path: Union[str, None, List] = None,
    max_dist: Union[int, float] = 1000,
    add_border: bool = False,
    border_value: Union[int, float] = 0,
    weighted: bool = False,
    invert: bool = False,
    return_array: bool = False,
    prefix: str = "",
    suffix: str = "_proximity",
    add_uuid: bool = False,
    overwrite: bool = True,
) -> Union[str, np.ndarray]:
    """
    Calculate the proximity of input_raster to values.

    Parameters
    ----------
    input_rasters : List
        A list of rasters to use as input.

    target_value : Union[int, float], optional
        The value to use as target, default: 1.

    unit : str, optional
        The unit to use for the distance, GEO or PIXEL, default: "GEO".

    out_path : Union[str, None, List], optional
        The output path, default: None.

    max_dist : Union[int, float], optional
        The maximum distance to use, default: 1000.

    add_border : bool, optional
        If True, a border will be added to the raster, default: False.

    border_value : Union[int, float], optional
        The value to use for the border, default: 0.

    weighted : bool, optional
        If True, the distance will be divided by the max distance, default: False.

    invert : bool, optional
        If True, the target will be inversed, default: False.

    return_array : bool, optional
        If True, a NumPy array will be returned instead of a raster, default: False.

    prefix : str, optional
        Prefix to add to the output, default: "".

    suffix : str, optional
        Suffix to add to the output, default: "_proximity".

    add_uuid : bool, optional
        Should a uuid be added to the output path?, default: False.

    overwrite : bool, optional
        If the output path exists already, should it be overwritten?, default: True.

    Returns
    -------
    Union[str, np.ndarray]
        A path to a raster with the calculated proximity, or a numpy array with the data.
    """
    utils_base.type_check(input_rasters, [str, gdal.Dataset, [str, gdal.Dataset]], "input_rasters")
    utils_base.type_check(target_value, [int, float], "target_value")
    utils_base.type_check(out_path, [str, [str], None], "out_path")
    utils_base.type_check(max_dist, [int, float], "max_dist")
    utils_base.type_check(add_border, [bool], "add_border")
    utils_base.type_check(border_value, [int, float], "border_value")
    utils_base.type_check(weighted, [bool], "weighted")
    utils_base.type_check(invert, [bool], "invert")
    utils_base.type_check(return_array, [bool], "return_array")
    utils_base.type_check(prefix, [str], "prefix")
    utils_base.type_check(suffix, [str], "suffix")
    utils_base.type_check(add_uuid, [bool], "add_uuid")
    utils_base.type_check(overwrite, [bool], "overwrite")

    raster_list = utils_base._get_variable_as_list(input_rasters)
    path_list = utils_gdal.create_output_path_list(
        raster_list,
        out_path=out_path,
        overwrite=overwrite,
        prefix=prefix,
        suffix=suffix,
        add_uuid=add_uuid,
    )

    output = []
    for index, input_raster in enumerate(raster_list):
        out_path = path_list[index]

        in_arr = core_raster.raster_to_array(input_raster, filled=True)
        bin_arr = (in_arr != target_value).astype("uint8")
        bin_raster = core_raster.array_to_raster(bin_arr, reference=input_raster)

        in_raster = core_raster._open_raster(bin_raster)
        in_raster_path = bin_raster

        if add_border:
            border_size = 1
            border_raster = add_border_to_raster(
                in_raster,
                border_size=border_size,
                border_value=border_value,
                overwrite=True,
            )

            in_raster = core_raster._open_raster(border_raster)

            gdal.Unlink(in_raster_path)
            in_raster_path = border_raster

        src_band = in_raster.GetRasterBand(1)

        driver_name = "GTiff" if out_path is None else utils_gdal._get_raster_driver_from_path(out_path)
        if driver_name is None:
            raise ValueError(f"Unable to parse filetype from path: {out_path}")

        driver = gdal.GetDriverByName(driver_name)
        if driver is None:
            raise ValueError(f"Error while creating driver from extension: {out_path}")

        mem_path = f"/vsimem/raster_proximity_tmp_{uuid4().int}.tif"

        dest_raster = driver.Create(
            mem_path,
            in_raster.RasterXSize,
            in_raster.RasterYSize,
            1,
            gdal.GetDataTypeByName("Float32"),
        )

        dest_raster.SetGeoTransform(in_raster.GetGeoTransform())
        dest_raster.SetProjection(in_raster.GetProjectionRef())
        dst_band = dest_raster.GetRasterBand(1)

        gdal.ComputeProximity(
            src_band,
            dst_band,
            options=[
                "VALUES='1'",
                f"DISTUNITS={unit}",
                f"MAXDIST={max_dist}",
            ],
        )

        dst_arr = dst_band.ReadAsArray()
        gdal.Unlink(mem_path)
        gdal.Unlink(in_raster_path)

        dst_arr = np.where(dst_arr > max_dist, max_dist, dst_arr)

        if invert:
            dst_arr = max_dist - dst_arr

        if weighted:
            dst_arr = dst_arr / max_dist

        if add_border:
            dst_arr = dst_arr[border_size:-border_size, border_size:-border_size]

        src_band = None
        dst_band = None
        in_raster = None
        dest_raster = None

        if return_array:
            output.append(dst_arr)
        else:
            core_raster.array_to_raster(dst_arr, reference=input_raster, out_path=out_path)
            output.append(out_path)

        dst_arr = None

    if isinstance(input_rasters, list):
        return output

    return output[0]
