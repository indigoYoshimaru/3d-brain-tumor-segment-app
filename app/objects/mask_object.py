class MaskVisual:

    def __init__(self, mask, opac_pk, smooth_pk):
        self.mask = mask
        # pickers
        self.opacity_pk = opac_pk
        self.smoothness_pk = smooth_pk
        # cb
        # self.mask_label_cb = label_cb

    def get_visual(self):
        return self.mask, self.opacity_pk, self.smoothness_pk

    def set_visual(self, mask, opac_pk, smooth_pk):
        self.mask = mask
        # pickers
        self.opacity_pk = opac_pk
        self.smoothness_pk = smooth_pk
