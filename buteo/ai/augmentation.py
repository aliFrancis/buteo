"""
This module contains functions for augmenting images that are
suited to remote sensing imagery.
"""
# Standard library
import sys; sys.path.append("../../")
from typing import Optional, List, Callable

import numpy as np
import buteo as beo

from buteo.ai.augmentation_funcs import (
    augmentation_rotation,
    augmentation_mirror,
    augmentation_channel_scale,
    augmentation_noise,
    augmentation_contrast,
    augmentation_blur,
    augmentation_blur_xy,
    augmentation_sharpen,
    augmentation_sharpen_xy,
    augmentation_drop_pixel,
    augmentation_drop_channel,
    augmentation_misalign,
    augmentation_cutmix,
    augmentation_mixup,
)


class AugmentationDataset():
    """
    A dataset that applies augmentations to the data.

    The following augmentations are supported:
        - rotation (chance)
        - mirror (chance)
        - channel_scale (chance, additive(bool), max_value(float[0,1]))
        - noise (chance, additive(bool), max_value(float[0,1]))
        - contrast (chance, max_value(float[0,1]))
        - drop_pixel (chance, drop_probability(float[0,1]), drop_value(float))
        - drop_channel (chance, drop_probability(float[0,1]), drop_value(float))
        - blur (chance, intensity(float[0,1]=1.0))
        - blur_xy (chance, intensity(float[0,1]=1.0))
        - sharpen (chance, intensity(float[0,1]=1.0))
        - sharpen_xy (chance, intensity(float[0,1]=1.0))
        - cutmix (chance, min_size(float[0, 1]), max_size(float[0, 1]))
        - mixup (chance, min_size(float[0, 1]), max_size(float[0, 1]), label_mix(int))

    Parameters
    ----------
    X : np.ndarray
        The data to augment.

    y : np.ndarray
        The labels for the data.

    augmentations : list, optional
        The augmentations to apply.

    callback : callable, optional
        A callback to apply to the data after augmentation.

    input_is_channel_last : bool, default: True
        Whether the data is in channel last format.

    output_is_channel_last : bool, default: False
        Whether the output should be in channel last format.

    Returns
    -------
    AugmentationDataset
        A dataset yielding batches of augmented data. For Pytorch,
        convert the batches to tensors before ingestion.

    Example
    -------
    >>> def callback(x, y):
    ...     return (
    ...         torch.from_numpy(x).float(),
    ...         torch.from_numpy(y).float(),
    ...     )
    ...
    >>> dataset = AugmentationDataset(
    ...     x_train,
    ...     y_train,
    ...     callback=callback,
    ...     input_is_channel_last=True,
    ...     output_is_channel_last=False,
    ...     augmentations=[
    ...         { "name": "rotation", "chance": 0.2},
    ...         { "name": "mirror", "chance": 0.2 },
    ...         { "name": "noise", "chance": 0.2 },
    ...         { "name": "cutmix", "chance": 0.2 },
    ...     ],
    ... )
    >>>
    >>> from torch.utils.data import DataLoader
    >>> dataloader = DataLoader(dataset, batch_size=32, shuffle=True)
    """
    def __init__(
        self,
        X: np.ndarray,
        y: np.ndarray,
        augmentations: Optional[List] = None,
        callback: Callable = None,
        input_is_channel_last: bool = True,
        output_is_channel_last: bool = False,
    ):
        # Convert data format if necessary
        if input_is_channel_last:
            self.x_train = beo.channel_last_to_first(X)
            self.y_train = beo.channel_last_to_first(y)
        else:
            self.x_train = X
            self.y_train = y

        # Set augmentations and callback
        self.augmentations = augmentations or []
        self.callback = callback
        self.channel_last = False
        self.output_is_channel_last = output_is_channel_last

    def __len__(self):
        return len(self.x_train)

    def __getitem__(self, index):
        x = self.x_train[index]
        y = self.y_train[index]

        # Apply augmentations
        for aug in self.augmentations:
            aug_name = aug["name"]
            func = None

            # Mapping augmentation names to their respective functions
            if aug_name == "rotation":
                func = augmentation_rotation
            elif aug_name == "mirror":
                func = augmentation_mirror
            elif aug_name == "channel_scale":
                func = augmentation_channel_scale
            elif aug_name == "noise":
                func = augmentation_noise
            elif aug_name == "contrast":
                func = augmentation_contrast
            elif aug_name == "drop_pixel":
                func = augmentation_drop_pixel
            elif aug_name == "drop_channel":
                func = augmentation_drop_channel
            elif aug_name == "blur":
                func = augmentation_blur
            elif aug_name == "blur_xy":
                func = augmentation_blur_xy
            elif aug_name == "sharpen":
                func = augmentation_sharpen
            elif aug_name == "sharpen_xy":
                func = augmentation_sharpen_xy
            elif aug_name == "misalign":
                func = augmentation_misalign
            elif aug_name == "cutmix":
                func = augmentation_cutmix
            elif aug_name == "mixup":
                func = augmentation_mixup

            if func is None:
                raise ValueError(f"Augmentation {aug['name']} not supported.")

            channel_last = self.channel_last
            kwargs = {key: value for key, value in aug.items() if key != "name"}

            # Apply cutmix and mixup augmentations
            if aug_name in ["cutmix", "mixup"]:
                idx_source = np.random.randint(len(self.x_train))
                xx = self.x_train[idx_source]
                yy = self.y_train[idx_source]

                x, y = func(x, y, xx, yy, channel_last=channel_last, **kwargs)
            else:
                x, y = func(x, y, channel_last=channel_last, **kwargs)

        # Apply callback if specified
        if self.callback is not None:
            x, y = self.callback(x, y)

        # Convert output format if necessary
        if self.output_is_channel_last:
            x = beo.channel_first_to_last(x)
            y = beo.channel_first_to_last(y)

        return x, y


class Dataset():
    """
    A dataset that does not apply any augmentations to the data.
    Allows a callback to be passed and can convert between
    channel formats.

    Parameters
    ----------
    X : np.ndarray
        The data to augment.

    y : np.ndarray
        The labels for the data.

    callback : callable, optional
        A callback to apply to the data after augmentation.

    input_is_channel_last : bool, default: True
        Whether the data is in channel last format.

    output_is_channel_last : bool, default: False
        Whether the output should be in channel last format.

    Returns
    -------
    Dataset
        A dataset yielding batches of data. For Pytorch,
        convert the batches to tensors before ingestion.
    """
    def __init__(self,
        X: np.ndarray,
        y: np.ndarray,
        callback: Callable = None,
        input_is_channel_last: bool = True,
        output_is_channel_last: bool = False,
    ):
        # Convert input format if necessary
        if input_is_channel_last:
            self.x_train = beo.channel_last_to_first(X)
            self.y_train = beo.channel_last_to_first(y)
        else:
            self.x_train = X
            self.y_train = y

        self.callback = callback
        self.channel_last = False
        self.output_is_channel_last = output_is_channel_last

    def __len__(self):
        return len(self.x_train)

    def __getitem__(self, index):
        x = self.x_train[index]
        y = self.y_train[index]

        # Apply callback if specified
        if self.callback is not None:
            x, y = self.callback(x, y)

        # Convert output format if necessary
        if self.output_is_channel_last:
            x = beo.channel_first_to_last(x)
            y = beo.channel_first_to_last(y)

        return x, y
