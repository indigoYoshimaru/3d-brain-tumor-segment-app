import vtk
from utils.config import *
from objects.nii_object import *
from handlers.vtk_handler import *
from vtk.util import numpy_support
from matplotlib.cm import get_cmap
import numpy as np

class FileReader:
    def __init__(self):
        self._renderer = None

    def read_mask(self, file_name, mask_type):
        mask = NiiObject()
        mask.file = file_name
        mask.reader = read_volume(mask.file)
        mask.extent = mask.reader.GetDataExtent()
        n_labels = int(mask.reader.GetOutput().GetScalarRange()[1])

        for label_idx in range(n_labels):
            mask.labels.append(
                NiiLabel(MASK_COLORS.get(mask_type)[label_idx], MASK_OPACITY, MASK_SMOOTHNESS))
            mask.labels[label_idx].extractor = create_mask_extractor(mask)
            add_surface_rendering(mask, label_idx, label_idx + 1)
            self._renderer.AddActor(mask.labels[label_idx].actor)
        # remap labels
        # for item in mask.labels:
        #     if not item.actor:
        #         mask.labels.remove(item)
        del mask.labels[2]
        print(len(mask.labels))

        return mask

    def read_brain(self, file_name):
        brain = NiiObject()
        brain.file = file_name
        brain.reader = read_volume(brain.file)
        brain.labels.append(
            NiiLabel(BRAIN_COLORS[0], BRAIN_OPACITY, BRAIN_SMOOTHNESS))
        brain.labels[0].extractor = create_brain_extractor(brain)
        brain.extent = brain.reader.GetDataExtent()

        scalar_range = brain.reader.GetOutput().GetScalarRange()
        bw_lut = vtk.vtkLookupTable()
        bw_lut.SetTableRange(scalar_range)
        
        if not BRAIN_CMAP:
            bw_lut.SetSaturationRange(0, 0)
            bw_lut.SetHueRange(0, 0)
            bw_lut.SetValueRange(0, 2)

        else: 
            cmap = get_cmap(BRAIN_CMAP)
            ctable = cmap(np.linspace(0, 1, 200))*255
            ctable = ctable.astype(np.uint8)
            bw_lut.SetTable(numpy_support.numpy_to_vtk(ctable))
       
        bw_lut.Build()
        view_colors = vtk.vtkImageMapToColors()
        view_colors.SetInputConnection(brain.reader.GetOutputPort())
        view_colors.SetLookupTable(bw_lut)
        view_colors.Update()
        brain.image_mapper = view_colors
        brain.scalar_range = scalar_range
        return brain

    def setup_slice(self, brain):
        x = brain.extent[1]
        y = brain.extent[3]
        z = brain.extent[5]

        axial = vtk.vtkImageActor()
        axial_prop = vtk.vtkImageProperty()
        axial_prop.SetOpacity(1)
        axial.SetProperty(axial_prop)
        axial.GetMapper().SetInputConnection(brain.image_mapper.GetOutputPort())
        axial.SetDisplayExtent(0, x, 0, y, int(z/2), int(z/2))
        axial.InterpolateOn()
        axial.ForceOpaqueOn()

        coronal = vtk.vtkImageActor()
        cor_prop = vtk.vtkImageProperty()
        cor_prop.SetOpacity(1)
        coronal.SetProperty(cor_prop)
        coronal.GetMapper().SetInputConnection(brain.image_mapper.GetOutputPort())
        coronal.SetDisplayExtent(0, x, int(y/2), int(y/2), 0, z)
        coronal.InterpolateOn()
        coronal.ForceOpaqueOn()

        sagittal = vtk.vtkImageActor()
        sag_prop = vtk.vtkImageProperty()
        sag_prop.SetOpacity(1)
        sagittal.SetProperty(sag_prop)
        sagittal.GetMapper().SetInputConnection(brain.image_mapper.GetOutputPort())
        sagittal.SetDisplayExtent(int(x/2), int(x/2), 0, y, 0, z)
        sagittal.InterpolateOn()
        sagittal.ForceOpaqueOn()

        self._renderer.AddActor(axial)
        self._renderer.AddActor(coronal)
        self._renderer.AddActor(sagittal)

        return [axial, coronal, sagittal]

    @property
    def renderer(self):
        return self._renderer

    @renderer.setter
    def renderer(self, rend):
        self._renderer = rend
