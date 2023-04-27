"""
This module contains functions for augmenting images that are
suited to remote sensing imagery.
"""
# Standard library
import sys; sys.path.append("../../")
from typing import Optional, Tuple, Any

# External
import numpy as np
from numba import jit, prange

# Internal
from buteo.ai.augmentation_utils import (
    rotate_arr,
    mirror_arr,
    _fit_data_to_dtype,
    _feather_box_2d,
)
from buteo.array.convolution import (
    convolve_array_simple,
    _simple_blur_kernel_2d_3x3,
    _simple_unsharp_kernel_2d_3x3,
    _simple_shift_kernel_2d,
)


@jit(nopython=True, nogil=True, cache=True, fastmath=True)
def augmentation_rotation(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    k: Optional[int] = None,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Randomly rotate the image by 90 degrees intervals. Images
    can be (channels, height, width) or (height, width, channels).
    
    Parameters
    ----------
    X : np.ndarray
        The image to rotate.

    y : np.ndarray, optional
        The label to rotate, default: None.

    chance : float, optional
        The chance of rotating the image, default: 0.2.

    k : int, optional
        The number of 90 degree intervals to rotate by, default: None.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The rotated image and optionally the label.
    """
    if np.random.rand() > chance or k == 0:
        return X, y

    random_k = np.random.randint(1, 4) if k is None else k
    X_rot = rotate_arr(X, random_k, channel_last)

    if y is None:
        return X_rot, y

    y_rot = rotate_arr(y, random_k, channel_last)

    return X_rot, y_rot


@jit(nopython=True, nogil=True, cache=True, fastmath=True)
def augmentation_mirror(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    k: Optional[int] = None,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Randomly mirrors the image. Images can be (channels, height, width) or (height, width, channels).
    
    Parameters
    ----------
    X : np.ndarray
        The image to mirror.

    y : np.ndarray, optional
        The label to mirror, default: None.

    chance : float, optional
        The chance of mirroring the image, default: 0.2.

    k : int, optional
        If None, randomly mirrors the image along the horizontal or vertical axis.
        1. mirrors the image along the horizontal axis.
        2. mirrors the image along the vertical axis.
        3. mirrors the image along both the horizontal and vertical axis, default: None.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The mirrored image and optionally the label.
    """
    if np.random.rand() > chance or k == 0:
        return X, y

    random_k = np.random.randint(1, 4) if k is None else k

    flipped_x = mirror_arr(X, random_k, channel_last)
    flipped_y = mirror_arr(y, random_k, channel_last) if y is not None else None

    return flipped_x, flipped_y


@jit(nopython=True, nogil=True, cache=True, fastmath=True)
def augmentation_noise(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    max_amount: float = 0.1,
    additive: bool = False,
    channel_last: Any = None, # pylint: disable=unused-argument
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Adds random noise seperately to each pixel of the image. The noise works
    for both channel first and last images. Input should be (height, width, channels) or (channels, height, width).
    
    Parameters
    ----------
    X : np.ndarray
        The image to add noise to.

    y : np.ndarray, optional
        The label to add noise to. If None, no label is returned, default: None.

    chance : float, optional
        The chance of adding noise, default: 0.2.

    max_amount : float, optional
        The maximum amount of noise to add, sampled uniformly, default: 0.1.

    additive : bool, optional
        Whether to add or multiply the noise, default: False.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), ignored for this function.
        Kept to keep the same function signature as other augmentations, default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The image with noise and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    amount = np.random.rand() * max_amount

    if additive:
        noisy_x = X + np.random.normal(0, amount, X.shape)
    else:
        noisy_x = X * np.random.normal(1, amount, X.shape)

    return _fit_data_to_dtype(noisy_x, X.dtype), y


@jit(nopython=True, nogil=True, cache=True, fastmath=True, parallel=True)
def augmentation_channel_scale(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    max_amount: float = 0.1,
    additive: bool = False,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Scales the channels of the image seperately by a fixed amount.
    Input should be (height, width, channels) or (channels, height, width).
    
    Parameters
    ----------
    X : np.ndarray
        The image to scale the channels of.

    y : np.ndarray, optional
        The label to scale the channels of. If None, no label is returned, default: None.

    chance : float, optional
        The chance of scaling the channels, default: 0.2.

    max_amount : float, optional
        The amount to possible scale the channels by. Sampled uniformly, default: 0.1.

    additive : bool, optional
        Whether to add or multiply the scaling, default: False.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The image with scaled channels and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_scaled = X.astype(np.float32)
    y_scaled = y

    amount = np.random.rand() * max_amount

    if channel_last:
        for i in prange(X.shape[2]):
            if additive:
                random_amount = np.random.uniform(-amount, amount)
                x_scaled[:, :, i] += random_amount
            else:
                random_amount = np.random.uniform(1 - amount, 1 + amount)
                x_scaled[:, :, i] *= random_amount
    else:
        for i in prange(X.shape[0]):
            if additive:
                random_amount = np.random.uniform(-amount, amount)
                x_scaled[i, :, :] += random_amount
            else:
                random_amount = np.random.uniform(1 - amount, 1 + amount)
                x_scaled[i, :, :] *= random_amount

    return _fit_data_to_dtype(x_scaled, X.dtype), y_scaled


@jit(nopython=True, nogil=True, cache=True, fastmath=True, parallel=True)
def augmentation_contrast(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    max_amount: float = 0.1,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Changes the contrast of an image by a random amount, seperately for each channel.
    Input should be (height, width, channels) or (channels, height, width).
    
    Parameters
    ----------
    X : np.ndarray
        The image to change the contrast of.

    y : np.ndarray, optional
        The label to change the contrast of. If None, no label is returned, default: None.

    chance : float, optional
        The chance of changing the contrast, default: 0.2.

    max_amount : float, optional
        The max amount to change the contrast by, default: 0.1.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The image with changed contrast and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_contrast = X.astype(np.float32)
    y_contrast = y

    amount = np.random.rand() * max_amount

    channels = X.shape[2] if channel_last else X.shape[0]
    mean_pixel = np.array([0.0] * channels, dtype=np.float32)

    # Numba workaround
    if channel_last:
        for i in prange(channels):
            mean_pixel[i] = np.mean(x_contrast[:, :, i])
    else:
        for i in prange(channels):
            mean_pixel[i] = np.mean(x_contrast[i])

    for i in prange(channels):
        x_contrast[:, :, i] = (x_contrast[:, :, i] - mean_pixel[i]) * (1 + amount) + mean_pixel[i]

    return _fit_data_to_dtype(x_contrast, X.dtype), y_contrast


@jit(nopython=True, nogil=True, cache=True, fastmath=True, parallel=True)
def augmentation_drop_pixel(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    drop_probability: float = 0.01,
    drop_value: float = 0.0,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Drops random pixels from an image. Input should be (height, width, channels) or (channels, height, width).
    Only drops pixels from features, not labels.
    
    Parameters
    ----------
    X : np.ndarray
        The image to drop a pixel from.

    y : np.ndarray, optional
        The label to drop a pixel from. If None, no label is returned, default: None.

    chance : float, optional
        The chance of dropping a pixel, default: 0.2.

    drop_probability : float, optional
        The probability of dropping a pixel, default: 0.05.

    drop_value : float, optional
        The value to drop the pixel to, default: 0.0.

    apply_to_y : bool, optional
        Whether to apply the drop to the label, default: False.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The image with the dropped pixels and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_dropped = X.copy()
    y_dropped = y

    mask = np.random.random(size=x_dropped.shape)

    # Agreed. This looks terrible. But it's the only way to get numba to parallelize this.
    if channel_last:
        for col in prange(X.shape[0]):
            for row in prange(X.shape[1]):
                for channel in prange(X.shape[2]):
                    if mask[col, row, channel] <= drop_probability:
                        x_dropped[col, row, channel] = drop_value

    else:
        for channel in prange(X.shape[0]):
            for col in prange(X.shape[1]):
                for row in prange(X.shape[2]):
                    if mask[channel, col, row] <= drop_probability:
                        x_dropped[channel, col, row] = drop_value

    return x_dropped, y_dropped


@jit(nopython=True, nogil=True, cache=True, fastmath=True)
def augmentation_drop_channel(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    drop_probability: float = 0.1,
    drop_value: float = 0.0,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Drops a random channel from an image. Input should be (height, width, channels) or (channels, height, width).
    A maximum of one channel will be dropped.
    
    Parameters
    ----------
    X : np.ndarray
        The image to drop a channel from.

    y : np.ndarray, optional
        The label to drop a channel from. If None, no label is returned, default: None.

    chance : float, optional
        The chance of dropping a channel, default: 0.2.

    drop_probability : float, optional
        The probability of dropping a channel, default: 0.1.

    drop_value : float, optional
        The value to drop the channel to, default: 0.0.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The image with the dropped channel and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_dropped = X.copy()
    y_dropped = y

    channels = X.shape[2] if channel_last else X.shape[0]

    drop_a_channel = False
    for _ in range(channels):
        if np.random.rand() < drop_probability:
            drop_a_channel = True
            break

    if not drop_a_channel:
        return X, y

    channel_to_drop = np.random.randint(0, channels)

    if channel_last:
        x_dropped[:, :, channel_to_drop] = drop_value
    else:
        x_dropped[channel_to_drop, :, :] = drop_value

    return x_dropped, y_dropped


@jit(nopython=True, nogil=True, cache=True, fastmath=True, parallel=True)
def augmentation_blur(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    intensity: float = 1.0,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Blurs an image at random. Input should be (height, width, channels) or (channels, height, width).
    
    Parameters
    ----------
    X : np.ndarray
        The image to potentially blur.

    y : np.ndarray, optional
        The label is ignored, default: None.

    chance : float, optional
        The chance of blurring a pixel, default: 0.2.

    intensity : float, optional
        The intensity of the blur, from 0.0 to 1.0, default: 1.0.

    apply_to_y : bool, optional
        Whether to blur the label as well, default: False.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The blurred image and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_blurred = X.astype(np.float32)
    y_blurred = y

    offsets, weights = _simple_blur_kernel_2d_3x3()
    channels = X.shape[2] if channel_last else X.shape[0]

    if channel_last:
        for channel in prange(channels):
            x_blurred[:, :, channel] = convolve_array_simple(x_blurred[:, :, channel], offsets, weights, intensity)
    else:
        for channel in prange(channels):
            x_blurred[channel, :, :] = convolve_array_simple(x_blurred[channel, :, :], offsets, weights, intensity)

    x_blurred = _fit_data_to_dtype(x_blurred, X.dtype)

    return x_blurred, y_blurred


@jit(nopython=True, nogil=True, cache=True, fastmath=True)
def augmentation_blur_xy(
    X: np.ndarray,
    y: np.ndarray,
    chance: float = 0.2,
    intensity: float = 1.0,
    channel_last: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Blurs an image at random. Input should be (height, width, channels) or (channels, height, width).
    The label is blurred by the same amount.
    
    Parameters
    ----------
    X : np.ndarray
        The image to potentially blur.

    y : np.ndarray, optional
        The label to potentially blur. If None, no label is returned, default: None.

    chance : float, optional
        The chance of blurring a pixel, default: 0.2.

    intensity : float, optional
        The intensity of the blur, from 0.0 to 1.0, default: 1.0.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        The blurred image and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_blurred, _ = augmentation_blur(X, None, chance, intensity, channel_last)
    y_blurred, _ = augmentation_blur(y, None, chance, intensity, channel_last)

    return x_blurred, y_blurred


@jit(nopython=True, nogil=True, cache=True, fastmath=True, parallel=True)
def augmentation_sharpen(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    intensity: float = 1.0,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Sharpens an image at random. Input should be (height, width, channels) or (channels, height, width).

    Parameters
    ----------
    X : np.ndarray
        The image to potentially sharpen.

    y : np.ndarray, optional
        The label will be ignored. If None, no label is returned, default: None.

    chance : float, optional
        The chance of sharpening a pixel, default: 0.2.

    intensity : float, optional
        The intensity of the sharpening, from 0.0 to 1.0, default: 1.0.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The sharpened image and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_sharpened = X.astype(np.float32)
    y_sharpened = y

    offsets, weights = _simple_unsharp_kernel_2d_3x3()
    channels = X.shape[2] if channel_last else X.shape[0]

    if channel_last:
        for channel in prange(channels):
            x_sharpened[:, :, channel] = convolve_array_simple(x_sharpened[:, :, channel], offsets, weights, intensity)
    else:
        for channel in prange(channels):
            x_sharpened[channel, :, :] = convolve_array_simple(x_sharpened[channel, :, :], offsets, weights, intensity)

    x_sharpened = _fit_data_to_dtype(x_sharpened, X.dtype)

    return x_sharpened, y_sharpened



@jit(nopython=True, nogil=True, cache=True, fastmath=True)
def augmentation_sharpen_xy(
    X: np.ndarray,
    y: np.ndarray,
    chance: float = 0.2,
    intensity: float = 1.0,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Sharpens an image at random. Input should be (height, width, channels) or (channels, height, width).
    The label is sharpened by the same amount.

    Parameters
    ----------
    X : np.ndarray
        The image to potentially sharpen.

    y : np.ndarray, optional
        The label to potentially sharpen. If None, no label is returned, default: None.

    chance : float, optional
        The chance of sharpening a pixel, default: 0.2.

    intensity : float, optional
        The intensity of the sharpening, from 0.0 to 1.0, default: 1.0.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        The sharpened image and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_sharpened, _ = augmentation_sharpen(X, None, chance, intensity, channel_last)
    y_sharpened, _ = augmentation_sharpen(y, None, chance, intensity, channel_last)

    return x_sharpened, y_sharpened


@jit(nopython=True, nogil=True, cache=True, fastmath=True)
def augmentation_misalign(
    X: np.ndarray,
    y: Optional[np.ndarray],
    chance: float = 0.2,
    max_offset: float = 0.5,
    channel_last: bool = True,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Misaligns one channel in the image at random.
    input should be (height, width, channels) or (channels, height, width).

    Parameters
    ----------
    X : np.ndarray
        The image to potentially misalign the channels of.

    y : np.ndarray
        The label to potentially misalign the channels of. If None, no label is returned.

    chance : float, optional
        The chance of misaligning the channels of a pixel. Default: 0.2.

    max_offset : float, optional
        The maximum offset to misalign the channels by. Default: 0.5.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels). Default: True.

    Returns
    -------
    Tuple[np.ndarray, Optional[np.ndarray]]
        The misaligned image and optionally the unmodified label.
    """
    if np.random.rand() > chance:
        return X, y

    x_misaligned = X.astype(np.float32)
    y_misaligned = y.astype(np.float32) if y is not None else None

    offsets, weights = _simple_shift_kernel_2d(
        min(np.random.rand(), max_offset),
        min(np.random.rand(), max_offset),
    )

    channels = X.shape[2] if channel_last else X.shape[0]
    channel_to_adjust = np.random.randint(0, channels)

    if channel_last:
        x_misaligned[:, :, channel_to_adjust] = convolve_array_simple(x_misaligned[:, :, channel_to_adjust], offsets, weights)
    else:
        x_misaligned[channel_to_adjust, :, :] = convolve_array_simple(x_misaligned[channel_to_adjust, :, :], offsets, weights)

    x_misaligned = _fit_data_to_dtype(x_misaligned, X.dtype)
    y_misaligned = _fit_data_to_dtype(y_misaligned, y.dtype) if y is not None else None

    return x_misaligned, y_misaligned


@jit(nopython=True, nogil=True, cache=True, fastmath=True, parallel=True)
def augmentation_cutmix(
    X_target: np.ndarray,
    y_target: np.ndarray,
    X_source: np.ndarray,
    y_source: np.ndarray,
    chance: float = 0.2,
    min_size: float = 0.333,
    max_size: float = 0.666,
    label_mix: int = 0,
    feather: bool = False,
    feather_dist: int = 3,
    channel_last: bool = True,
) -> Tuple[np.ndarray, np.ndarray,]:
    """
    Cutmixes two images.
    Input should be (height, width, channels) or (channels, height, width).

    Parameters
    ----------
    X_target : np.ndarray
        The image to transfer the cutmix to.

    y_target : np.ndarray
        The label to transfer the cutmix to.

    X_source : np.ndarray
        The image to cutmix from.

    y_source : np.ndarray
        The label to cutmix from.

    chance : float, optional
        The chance of cutmixing a pixel, default: 0.2.

    min_size : float, optional
        The minimum size of the patch to cutmix. In percentage of the image width, default: 0.333.

    max_size : float, optional
        The maximum size of the patch to cutmix. In percentage of the image width, default: 0.666.

    label_mix : int, optional
        The method to mix the labels by, default: 0.
        0 - The labels will be mixed by the weights.
        1 - The target label will be used.
        2 - The source label will be used.
        3 - The max of the labels will be used.
        4 - The min of the labels will be used.
        5 - The max of the image with the highest weight will be used.
        6 - The min of the image with the highest weight will be used.
        7 - The sum of the labels will be used.

    feather : bool, optional
        Whether to feather the edges of the cutmix, default: False.

    feather_dist : int, optional
        The distance to feather the edges of the cutmix in pixels, default: 3.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        The cutmixed image and label.
    """
    if np.random.rand() > chance:
        return X_target, y_target

    x_mixed = X_target.astype(np.float32)
    y_mixed = y_target.astype(np.float32)

    if channel_last:
        height, width, channels_x = x_mixed.shape
    else:
        channels_x, height, width = x_mixed.shape

    channels_y = y_mixed.shape[2] if channel_last else y_mixed.shape[0]

    patch_height = np.random.randint(int(height * min_size), int(height * max_size))
    patch_width = np.random.randint(int(width * min_size), int(width * max_size))

    if feather:
        patch_height += feather_dist * 2
        patch_width += feather_dist * 2

        patch_height = min(patch_height, height)
        patch_width = min(patch_width, width)

    x0 = np.random.randint(0, width - patch_width)
    y0 = np.random.randint(0, height - patch_height)
    x1 = x0 + patch_width
    y1 = y0 + patch_height

    if feather:
        bbox = np.array([x0, x1, y0, y1])
        feather_weight_target = _feather_box_2d(x_mixed, bbox, feather_dist)
        feather_weight_source = 1 - feather_weight_target

        x0 = max(0, x0 - feather_dist)
        x1 = min(x1 + 1 + feather_dist, x_mixed.shape[1])
        y0 = max(0, y0 - feather_dist)
        y1 = min(y1 + 1 + feather_dist, x_mixed.shape[0])

        if channel_last: # Reshape and tile instead of slicing, because of Numba.
            for col in prange(y0, y1):
                for row in prange(x0, x1):
                    for channel_x in prange(channels_x):
                        x_mixed[col, row, channel_x] = (
                            x_mixed[col, row, channel_x] * feather_weight_target[col, row][0]
                            + X_source[col, row, channel_x] * feather_weight_source[col, row][0]
                        )

                    for channel_y in prange(channels_y):
                        if label_mix == 0:
                            y_mixed[col, row, channel_y] = (
                                y_mixed[col, row, channel_y] * feather_weight_target[col, row][0]
                                + y_source[col, row, channel_y] * feather_weight_source[col, row][0]
                            )
                        elif label_mix == 1:
                            y_mixed[col, row, channel_y] = y_mixed[col, row, channel_y]
                        elif label_mix == 2:
                            y_mixed[col, row, channel_y] = y_source[col, row, channel_y]
                        elif label_mix == 3:
                            y_mixed[col, row, channel_y] = max(
                                y_mixed[col, row, channel_y], y_source[col, row, channel_y]
                            )
                        elif label_mix == 4:
                            y_mixed[col, row, channel_y] = min(
                                y_mixed[col, row, channel_y], y_source[col, row, channel_y]
                            )
                        elif label_mix == 5:
                            if feather_weight_target[col, row][0] > feather_weight_source[col, row][0]:
                                y_mixed[col, row, channel_y] = y_mixed[col, row, channel_y]
                            else:
                                y_mixed[col, row, channel_y] = y_source[col, row, channel_y]
                        elif label_mix == 6:
                            if feather_weight_target[col, row][0] < feather_weight_source[col, row][0]:
                                y_mixed[col, row, channel_y] = y_mixed[col, row, channel_y]
                            else:
                                y_mixed[col, row, channel_y] = y_source[col, row, channel_y]
                        elif label_mix == 7:
                            y_mixed[col, row, channel_y] = (
                                y_mixed[col, row, channel_y] + y_source[col, row, channel_y]
                            )
        else:
            for col in prange(y0, y1):
                for row in prange(x0, x1):
                    for channel_x in prange(channels_x):
                        x_mixed[channel_x, col, row] = (
                            x_mixed[channel_x, col, row] * feather_weight_target[col, row][0]
                            + X_source[channel_x, col, row] * feather_weight_source[col, row][0]
                        )

                    for channel_y in prange(channels_y):
                        if label_mix == 0:
                            y_mixed[channel_y, col, row] = (
                                y_mixed[channel_y, col, row] * feather_weight_target[col, row][0]
                                + y_source[channel_y, col, row] * feather_weight_source[col, row][0]
                            )
                        elif label_mix == 1:
                            y_mixed[channel_y, col, row] = y_mixed[channel_y, col, row]
                        elif label_mix == 2:
                            y_mixed[channel_y, col, row] = y_source[channel_y, col, row]
                        elif label_mix == 3:
                            y_mixed[channel_y, col, row] = max(
                                y_mixed[channel_y, col, row], y_source[channel_y, col, row]
                            )
                        elif label_mix == 4:
                            y_mixed[channel_y, col, row] = min(
                                y_mixed[channel_y, col, row], y_source[channel_y, col, row]
                            )
                        elif label_mix == 5:
                            if feather_weight_target[col, row][0] > feather_weight_source[col, row][0]:
                                y_mixed[channel_y, col, row] = y_mixed[channel_y, col, row]
                            else:
                                y_mixed[channel_y, col, row] = y_source[channel_y, col, row]
                        elif label_mix == 6:
                            if feather_weight_target[col, row][0] < feather_weight_source[col, row][0]:
                                y_mixed[channel_y, col, row] = y_mixed[channel_y, col, row]
                            else:
                                y_mixed[channel_y, col, row] = y_source[channel_y, col, row]
                        elif label_mix == 7:
                            y_mixed[channel_y, col, row] = (
                                y_mixed[channel_y, col, row] + y_source[channel_y, col, row]
                            )

    else:
        if channel_last:
            x_mixed[y0:y1, x0:x1, :] = X_source[y0:y1, x0:x1, :]
            y_mixed[y0:y1, x0:x1, :] = y_source[y0:y1, x0:x1, :]

        else:
            x_mixed[:, y0:y1, x0:x1] = X_source[:, y0:y1, x0:x1]
            y_mixed[:, y0:y1, x0:x1] = y_source[:, y0:y1, x0:x1]

    x_mixed = _fit_data_to_dtype(x_mixed, X_target.dtype)
    y_mixed = _fit_data_to_dtype(y_mixed, y_target.dtype)

    return x_mixed, y_mixed


@jit(nopython=True, nogil=True, cache=True, fastmath=True, parallel=True)
def augmentation_mixup(
    X_target: np.ndarray,
    y_target: np.ndarray,
    X_source: np.ndarray,
    y_source: np.ndarray,
    min_size: float = 0.333,
    max_size: float = 0.666,
    label_mix: int = 0,
    chance: float = 0.2,
    channel_last: bool = True, # pylint: disable=unused-argument
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Mixups two images at random. This works by doing a linear intepolation between
    two images and then adding a random weight to each image.

    Mixup involves taking two images and blending them together by randomly interpolating
    their pixel values. More specifically, suppose we have two images x and x' with their
    corresponding labels y and y'. To generate a new training example, mixup takes a
    weighted sum of x and x', such that the resulting image x^* = λx + (1-λ)x',
    where λ is a randomly chosen interpolation coefficient. The label for the new image
    is also a weighted sum of y and y' based on the same interpolation coefficient.

    input should be (height, width, channels) or (channels, height, width).

    Parameters
    ----------
    X_target : np.ndarray
        The image to transfer to.

    y_target : np.ndarray
        The label to transfer to.

    X_source : np.ndarray
        The image to transfer from.

    y_source : np.ndarray
        The label to transfer from.

    min_size : float, optional
        The minimum mixup coefficient, default: 0.333.

    max_size : float, optional
        The maximum mixup coefficient, default: 0.666.

    label_mix : int, optional
        If 0, the labels will be mixed by the weights. If 1, the target label will be used. If 2, 
        the source label will be used. If 3, the max of the labels will be used. If 4, the min 
        of the labels will be used. If 5, the max of the image with the highest weight will be used. 
        If 6, the min of the image with the highest weight will be used. If 7, the sum of the labels 
        will be used, default: 0.

    chance : float, optional
        The chance of mixuping a pixel, default: 0.2.

    channel_last : bool, optional
        Whether the image is (channels, height, width) or (height, width, channels), default: True.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        The mixed up image and label.
    """
    if np.random.rand() > chance:
        return X_target, y_target

    x_mixed_target = X_target.astype(np.float32)
    y_mixed_target = y_target.astype(np.float32)

    x_mixed_source = X_source.astype(np.float32)
    y_mixed_source = y_source.astype(np.float32)

    mixup_coeff = np.float32(
        min(np.random.uniform(min_size, max_size + 0.001), 1.0),
    )

    x_mixed_target = x_mixed_target * mixup_coeff + x_mixed_source * (np.float32(1.0) - mixup_coeff)

    if label_mix == 0:
        y_mixed_target = y_mixed_target * mixup_coeff + y_mixed_source * (np.float32(1.0) - mixup_coeff)
    elif label_mix == 1:
        y_mixed_target = y_mixed_target # pylint: disable=self-assigning-variable
    elif label_mix == 2:
        y_mixed_target = y_mixed_source
    elif label_mix == 3:
        y_mixed_target = np.maximum(y_mixed_target, y_mixed_source)
    elif label_mix == 4:
        y_mixed_target = np.minimum(y_mixed_target, y_mixed_source)
    elif label_mix == 5:
        y_mixed_target = y_mixed_target if mixup_coeff >= 0.5 else y_mixed_source
    elif label_mix == 6:
        y_mixed_target = y_mixed_target if mixup_coeff >= 0.5 else y_mixed_source
    elif label_mix == 7:
        y_mixed_target = y_mixed_target + y_mixed_source

    x_mixed_target = _fit_data_to_dtype(x_mixed_target, X_target.dtype)
    y_mixed_target = _fit_data_to_dtype(y_mixed_target, y_target.dtype)

    return x_mixed_target, y_mixed_target
