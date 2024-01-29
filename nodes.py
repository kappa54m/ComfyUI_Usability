import folder_paths

from PIL import Image, ImageSequence, ImageOps
import numpy as np
import torch

import os
import os.path as osp
from pathlib import Path
import hashlib


class KLoadImageDedup:
    @classmethod
    def INPUT_TYPES(s):
        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        return {
            "required": {
                "image": (sorted(files), {
                            "image_upload_dedup": True
                        }),
            },
            "optional": {
                "overwrite_option": (['no_overwrite', 'input_filename', 'last_rename'], ),
            },
        }

    CATEGORY = "image"

    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"
    def load_image(self, image, overwrite_option=None):
        image_path = Path(folder_paths.get_annotated_filepath(image))
        image_fn = image_path.name
        im = Image.open(str(image_path))

        output_image, output_mask = self.__do_load(image_path, pil_im=im)

        return (output_image, output_mask)

    def __detect_duplicate(self, fp1, fp2):
        def do_hash(fp):
            m = hashlib.sha256()
            with open(fp, 'rb') as f:
                m.update(f.read())
            return m.digest().hex()
        h1 = do_hash(fp1)
        h2 = do_hash(fp2)
        return h1 == h2

    def __do_load(self, img_path, pil_im=None):
        """
            Reference implementation: nodes.LoadImage.load_image
            https://github.com/comfyanonymous/ComfyUI/blob/7f4725f6b3f72dd8bdb60dae5dd2c3e943263bcf/nodes.py#L1454
        """
        img_path = Path(img_path)
        if pil_im is not None:
            im_original = pil_im
        else:
            im_original = Image.open(str(img_path))
        output_imgs = []
        output_masks = []
        for im_single in ImageSequence.Iterator(im_original):
            im_single = ImageOps.exif_transpose(im_single)
            if im_single.mode == 'I':
                im_single = im_single.point(lambda i: i * (1.0 / 255))
            a = np.array(im_single.convert("RGB")).astype(np.float32) / 255.0
            a = torch.from_numpy(a)[None,]
            if 'A' in im_single.getbands():
                mask = np.array(im_single.getchannel('A')).astype(np.float32) / 255.0
                mask = 1.0 - torch.from_numpy(mask)
            else:
                mask = torch.zeros((64, 64), dtype=torch.float32, device='cpu')
            output_imgs.append(a)
            output_masks.append(mask.unsqueeze(0))

        if len(output_imgs) > 1:
            output_img = torch.cat(output_imgs, dim=0)
            output_mask = torch.cat(output_masks, dim=0)
        else:
            output_img = output_imgs[0]
            output_mask = output_masks[0]

        return (output_img, output_mask)

    @classmethod
    def IS_CHANGED(self, image):
        image_path = Path(folder_paths.get_annotated_filepath(image))
        m = hashlib.sha256()
        with open(image_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(self, image):
        if not folder_paths.exists_annotated_filepath(image):
            return "Invalid input image: '{}'".format(image)
        return True


# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {
    "LoadImageDedup": KLoadImageDedup,
}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageDedup": "Load Image Dedup",
}
