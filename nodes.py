from .common import load_image_comfy
import folder_paths

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
                            "kap_load_image_dedup": True
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
        output_image, output_mask = load_image_comfy(image_path)
        return (output_image, output_mask)

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


class KLoadImageByPath:
    @classmethod
    def INPUT_TYPES(clazz):
        return {
            "required": {
                "image": ("STRING", {
                            "default": "/path/to/image.psd",
                            "kap_load_image_by_path": True,
                        }),
            },
            "optional": {
            },
            "hidden": {
                "id": "UNIQUE_ID"
            },
        }

    CATEGORY = "image"

    RETURN_TYPES = ("IMAGE", "MASK")

    FUNCTION = "load_image"
    def load_image(self, image, overwrite_option=None, id=None):
        image_path = Path(folder_paths.get_annotated_filepath(image))
        output_image, output_mask = load_image_comfy(image_path)
        return (output_image, output_mask)

    @classmethod
    def IS_CHANGED(self, image):
        image_path = Path(image)
        m = hashlib.sha256()
        with open(image_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(self, image):
        if not osp.isfile(image):
            return "Invalid input image: '{}'".format(image)
        return True


# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {
    "LoadImageDedup": KLoadImageDedup,
    "LoadImageByPath": KLoadImageByPath,
}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageDedup": "Load Image Dedup",
    "LoadImageByPath": "Load Image By Path",
}
