from abc import ABCMeta, abstractmethod
from typing import Tuple, Callable, Any, Optional, List
import matplotlib.pyplot as plt
import numpy as np

from receptivefield.common import estimate_rf_from_gradients
from receptivefield.logging import get_logger
from receptivefield.plotting import plot_receptive_grid, plot_gradient_field
from receptivefield.types import (
    ImageShape,
    GridPoint,
    GridShape,
    ReceptiveFieldDescription,
    Size,
    FeatureMapDescription,
)

_logger = get_logger()


class ReceptiveField(metaclass=ABCMeta):
    def __init__(self, model_func: Callable[[Any], Any]) -> None:

        self._model_func: Callable[[Any], Any] = model_func
        self._gradient_function: Callable = None
        self._input_shape: GridShape = None
        self._output_shapes: List[GridShape] = None
        self._rf_params: List[ReceptiveFieldDescription] = None
        self._built: bool = False

    @property
    def feature_maps_desc(self) -> List[FeatureMapDescription]:
        """Return description of all feature maps"""
        self._check()
        return [
            FeatureMapDescription(size=Size(size.w, size.h), rf=rf)
            for size, rf in zip(self._output_shapes, self._rf_params)
        ]

    @property
    def input_shape(self) -> ImageShape:
        """Return input shape of the feature extractor"""
        self._check()
        return ImageShape(
            w=self._input_shape.w, h=self._input_shape.h, c=self._input_shape.c
        )

    @property
    def output_shapes(self) -> List[Size]:
        """Return a list of sizes of selected features maps"""
        self._check()
        return [Size(w=size.w, h=size.h) for size in self._output_shapes]

    @property
    def num_feature_maps(self) -> int:
        """Returns number of features maps"""
        self._check()
        return len(self._output_shapes)

    def _build_gradient_func(self, *args, **kwargs) -> None:
        """
        Build gradient function and collect the input shape of the image
        and feature map shapes.

        :param args: a list of arguments which depend on the API
        :param kwargs: keywords which depend on the API
        """
        gradient_function, input_shape, output_shapes = self._prepare_gradient_func(
            *args, **kwargs
        )

        self._built = True
        self._gradient_function = gradient_function
        self._input_shape = input_shape
        self._output_shapes = output_shapes

    @abstractmethod
    def _prepare_gradient_func(
        self, *args, **kwargs
    ) -> Tuple[Callable, GridShape, List[GridShape]]:
        """
        Computes gradient function and additional parameters. Note
        that the receptive field parameters like stride or size, do not
        depend on input image shape. However, if the RF of original network
        is bigger than input_shape this method will fail. Hence it is
        recommended to increase the input shape.

        The arguments args, and kwargs must be compatible with args in `compute`
        and `_build_gradient_func` functions.

        :param args: a list of arguments which depend on the API
        :param kwargs: keywords which depend on the API

        :returns
            gradient_function: a function which returns gradient w.r.t. to
                the input image. The usage of the gradient function may depend
                on the API.
            input_shape: a shape of the input image tensor
            output_shape: a shapes of the output feature map tensors
        """
        pass

    @abstractmethod
    def _get_gradient_from_grid_points(
        self, points: List[GridPoint], intensity: float = 1.0
    ) -> List[np.ndarray]:
        """
        Computes gradient at input image generated by
        point-like perturbation at output grid location given by
        @point coordinates.

        :param points: source coordinate of the backpropagated gradient for each
            feature map.
        :param intensity: scale of the gradient, default = 1
        :return gradient maps for each feature map
        """
        pass

    def _get_gradient_activation_at_map_center(
        self, center_offsets: List[GridPoint], intensity: float = 1
    ) -> List[np.ndarray]:
        points = []
        for fm in range(self.num_feature_maps):
            output_shape = self._output_shapes[fm]
            center_offset = center_offsets[fm]

            _logger.debug(
                f"Computing receptive field for feature map [{fm}] at center "
                f"({output_shape.w//2}, {output_shape.h//2}) "
                f"with offset {center_offset}"
            )

            # compute grid center
            w = output_shape.w
            h = output_shape.h
            cx = w // 2 - 1 if w % 2 == 0 else w // 2
            cy = h // 2 - 1 if h % 2 == 0 else h // 2

            cx += center_offset.x
            cy += center_offset.y
            points.append(GridPoint(x=cx, y=cy))
        return self._get_gradient_from_grid_points(points=points, intensity=intensity)

    def _check(self):
        if not self._built:
            raise Exception("Receptive field not computed. Run compute function.")

    def compute(self, *args, **kwargs) -> List[FeatureMapDescription]:
        """
        Compute ReceptiveFieldDescription of given model for image of
        shape input_shape [H, W, C]. If receptive field of the network
        is bigger thant input_shape this method will raise exception.
        In order to solve with problem try to increase input_shape.

        :param args: a list of arguments which depend on the API
        :param kwargs: keywords which depend on the API

        :return a list of estimated FeatureMapDescription for each feature
            map.
        """
        # define gradient function
        self._build_gradient_func(*args, **kwargs)

        # receptive field at map center
        rf_grads00 = self._get_gradient_activation_at_map_center(
            center_offsets=[GridPoint(0, 0)] * self.num_feature_maps
        )
        rfs_at00 = estimate_rf_from_gradients(rf_grads00)

        # receptive field at map center with offset (1, 1)
        rf_grads11 = self._get_gradient_activation_at_map_center(
            center_offsets=[GridPoint(1, 1)] * self.num_feature_maps
        )
        rfs_at11 = estimate_rf_from_gradients(rf_grads11)

        # receptive field at feature map grid start x=0, y=0
        rf_grads_point00 = self._get_gradient_from_grid_points(
            points=[GridPoint(0, 0)] * self.num_feature_maps
        )
        rfs_at_point00 = estimate_rf_from_gradients(rf_grads_point00)

        self._rf_params = []

        for fm, (rf_at_point00, rf_at00, rf_at11) in enumerate(
            zip(rfs_at_point00, rfs_at00, rfs_at11)
        ):
            # compute position of the first anchor, center point of rect
            x0 = rf_at_point00.w - rf_at00.w / 2
            y0 = rf_at_point00.h - rf_at00.h / 2

            # compute feature map/input image offsets
            dx = rf_at11.x - rf_at00.x
            dy = rf_at11.y - rf_at00.y

            # compute receptive field size
            size = Size(rf_at00.w, rf_at00.h)

            rf_params = ReceptiveFieldDescription(
                offset=(x0, y0), stride=(dx, dy), size=size
            )

            _logger.info(
                f"Estimated receptive field for feature map [{fm}]: {rf_params}"
            )
            self._rf_params.append(rf_params)

        return self.feature_maps_desc

    def plot_gradients_at(
        self,
        points: List[GridPoint],
        image: Optional[np.ndarray] = None,
        layout: Optional[Tuple[int, int]] = None,
        figsize: Optional[Tuple[int, int]] = None,
    ) -> None:
        """
        Plot gradient map generated by certain `point` at feature map.

        :param points: a list of  GridPoint on feature maps.
        :param image: (optional) image of shape [W, H, 3]
        :param layout: (optional) a matplotlib subplot layout given by
            tuple of form (num_rows, num_cols). If None the layout is set
            to (num_feature_maps, 1).
        :param figsize: (optional) a matplotlib figsize. If None the default
            figure is used.
        """

        if layout is None:
            layout = (self.num_feature_maps, 1)
        if figsize is not None:
            plt.figure(figsize=figsize)

        receptive_field_grads = self._get_gradient_from_grid_points(
            points=[GridPoint(*point) for point in points]
        )

        for fm in range(self.num_feature_maps):
            axis = plt.subplot(layout[0], layout[1], fm + 1)
            plot_gradient_field(
                receptive_field_grad=receptive_field_grads[fm], image=image, axis=axis
            )

    def plot_gradient_at(
        self,
        fm_id: int,
        point: GridPoint,
        image: Optional[np.ndarray] = None,
        **plot_params,
    ) -> None:
        """
        Plot gradient map generated by certain `point` at selected feature map.

        :param fm_id: an index of feature map for which gradient map
            will be plotted.
        :param point: a GridPoint on feature map selected by fm_id.
        :param image: (optional) image of shape [W, H, 3]
        :param plot_params: (optional) additional plot parameters:
            figsize: tuple of int (5, 5)
            axis: a matplotlib axis object as returned by e.g. plt.subplot
                function. If not None then provided axis is used for
                visualizations otherwise default figure is created, with
                optional figsize.
        """
        points = [GridPoint(0, 0)] * self.num_feature_maps
        points[fm_id] = GridPoint(*point)
        receptive_field_grads = self._get_gradient_from_grid_points(points=points)

        plot_gradient_field(
            receptive_field_grad=receptive_field_grads[fm_id],
            image=image,
            **plot_params,
        )

    def plot_rf_grid(
        self,
        fm_id: int,
        custom_image: Optional[np.ndarray] = None,
        plot_naive_rf: bool = False,
        **plot_params,
    ) -> None:
        """
        Visualize receptive field grid for selected feature map.

        :param fm_id: an index of feature map for which gradient map
            will be plotted.
        :param custom_image: (optional) image of shape [W, H, 3]
        :param plot_naive_rf: plot naive version of the receptive field. Naive
            version of RF does not take strides, and offsets into considerations,
            it is a simple linear mapping from N points in feature map to pixels
            in the image.
        :param plot_params: (optional) additional plot parameters:
            figsize: tuple of int (5, 5)
            axis: a matplotlib axis object as returned by e.g. plt.subplot
                function. If not None then provided axis is used for
                visualizations otherwise default figure is created, with
                optional figsize.
        """
        plot_receptive_grid(
            input_shape=self._input_shape,
            output_shape=self._output_shapes[fm_id],
            rf_params=self._rf_params[fm_id],
            custom_image=custom_image,
            plot_naive_rf=plot_naive_rf,
            **plot_params,
        )

    def plot_rf_grids(
        self,
        custom_image: Optional[np.ndarray] = None,
        plot_naive_rf: bool = False,
        layout: Optional[Tuple[int, int]] = None,
        figsize: Optional[Tuple[int, int]] = None,
    ) -> None:
        """
        Visualize receptive field grid for selected feature map.

        :param custom_image: (optional) image of shape [W, H, 3]
        :param plot_naive_rf: plot naive version of the receptive field. Naive
            version of RF does not take strides, and offsets into considerations,
            it is a simple linear mapping from N points in feature map to pixels
            in the image.
        :param layout: (optional) a matplotlib subplot layout given by
            tuple of form (num_rows, num_cols). If None the layout is set
            to (num_feature_maps, 1).
        :param figsize: (optional) a matplotlib figsize. If None the default
            figure is used.
        """

        if layout is None:
            layout = (self.num_feature_maps, 1)
        if figsize is not None:
            plt.figure(figsize=figsize)

        for fm in range(self.num_feature_maps):
            axis = plt.subplot(layout[0], layout[1], fm + 1)
            self.plot_rf_grid(
                fm_id=fm,
                custom_image=custom_image,
                plot_naive_rf=plot_naive_rf,
                axis=axis,
            )