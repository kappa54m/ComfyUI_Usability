import torch
from PIL import Image, ImageSequence, ImageOps
import numpy as np

from threading import Lock
import os
import os.path as osp
from pathlib import Path
import sys
from sys import platform
import typing


watchdog_mutex = Lock()

with watchdog_mutex:
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    
        class Handler(FileSystemEventHandler):
            pass
    
        using_watchdog = True
    except ImportError:
        using_watchdog = False
        Handler = None
        print("Failed to import watchdog modules. Automatic image previews disabled.")


    watchdog_d = {}
    if using_watchdog:
        watchdog_observer = Observer()
    else:
        watchdog_observer = None


def get_watchlist():
    with watchdog_mutex:
        return list(watchdog_d.keys())


def update_watchlist(new_watchlist: typing.List[typing.Dict], expanduser=True):
    with watchdog_mutex:
        for fp, d in watchdog_d.items():
            assert d['observer'] is watchdog_observer
            d['observer'].unschedule_all()

        watchdog_d.clear()
        for w_info in new_watchlist:
            filepath = w_info['path']
            fp_real = str(osp.expanduser(filepath) if expanduser else filepath)
            if osp.isfile(fp_real):
                o = watchdog_observer
                h = Handler()
                h.on_modified = w_info.get('on_modified', lambda e: None)
                h.on_created = w_info.get('on_modified', lambda e: None)
                h.on_modified = w_info.get('on_modified', lambda e: None)
                w = o.schedule(h, path=fp_real)
                if not o.is_alive():
                    o.start()
                d = {
                    'observer': o,
                    'watcher': w,
                    'filepath_given': filepath,
                }
                watchdog_d[fp_real] = d
            else:
                print("Invalid file: '{}'; will not be added to watchlist.".format(filepath))
        print("Updated watchlist watching {} file(s)".format(len(watchdog_d)))


def get_imagemagick_exe():
    if platform == 'win32':
        return 'magick'
    else: #if platform in ('linux', 'linux2', 'darwin'):
        return 'convert'


def load_image_comfy(img_path, pil_im=None):
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

