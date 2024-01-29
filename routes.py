from server import PromptServer
import folder_paths

from aiohttp import web

import os
import os.path as osp
from pathlib import Path
import hashlib
import re


routes = PromptServer.instance.routes


@routes.post('/kap/upload/image-dedup')
async def upload_image_dedup(req):
    post = await req.post()
    return image_upload_dedup(post)


# Based on https://github.com/comfyanonymous/ComfyUI/blob/7f4725f6b3f72dd8bdb60dae5dd2c3e943263bcf/server.py
def image_upload_dedup(post, image_save_function=None):
    def get_dir_by_type(dir_type):
        if dir_type is None:
            dir_type = "input"

        if dir_type == "input":
            type_dir = folder_paths.get_input_directory()
        elif dir_type == "temp":
            type_dir = folder_paths.get_temp_directory()
        elif dir_type == "output":
            type_dir = folder_paths.get_output_directory()

        return type_dir, dir_type

    def compute_hash(fp):
        m = hashlib.md5()
        with open(fp, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                m.update(f.read())
        return m.digest().hex()
    
    def find_uploaded_images_samename(image_path, upload_dir):
        image_path, upload_dir = map(Path, [image_path, upload_dir])
        samename_fns = []
        for p in upload_dir.iterdir():
            if p.suffix != image_path.suffix:
                continue
            if not p.stem.startswith(image_path.stem):
                continue
            if p.name == image_path.name or \
                    re.match(r"^ \([1-9]\d*\)$", p.stem[len(image_path.stem):]):
                print("Append {}".format(p.name))
                samename_fns.append(p.name)

        def sort_fun(v):
            if v == image_path.name:
                return 0
            else:
                m = re.match(r"^ \(([1-9]\d*)\)$", osp.splitext(v)[0][len(image_path.stem):])
                return int(m.group(1))

        samename_fns = sorted(samename_fns, key=sort_fun)
        return {
            'original': Path(upload_dir, image_path.name) if image_path.name in samename_fns else None,
            'last_rename': samename_fns[-1] if 
                ((len(samename_fns) > 1 and image_path.name in samename_fns) or
                 (len(samename_fns) > 0 and image_path.name not in samename_fns)) else None
        }

    image = post.get("image")  # File object
    overwrite_option = post.get("overwrite") # {no_overwrite, input_filename, last_rename}
    if overwrite_option not in ['no_overwrite', 'input_filename', 'last_rename']:
        ovewrite_option = 'no_overwrite'

    image_upload_type = post.get("type")
    upload_dir, image_upload_type = get_dir_by_type(image_upload_type)

    if image and image.file:
        filename = image.filename
        if not filename:
            return web.Response(status=400)

        subfolder = post.get("subfolder", "")
        full_output_folder = os.path.join(upload_dir, os.path.normpath(subfolder))
        filepath = os.path.abspath(os.path.join(full_output_folder, filename))

        if os.path.commonpath((upload_dir, filepath)) != upload_dir:
            return web.Response(status=400)

        if not os.path.exists(full_output_folder):
            os.makedirs(full_output_folder)

        # Dedup
        do_write = True
        overwrite = False
        image_read = None  # Input image may be read during dedup process in which case contents will be copied to this var
        if overwrite_option == 'input_filename':
            do_write = True
            overwrite = True
            print("(Over)write original input filename: '{}'".format(filename))
        else:
            d = find_uploaded_images_samename(filepath, upload_dir)
            if overwrite_option == 'last_rename':
                do_write = True
                overwrite = True
                if d['last_rename']:
                    filename = d['last_rename']
                    print("Overwrite last rename: '{}'".format(d['last_rename']))
                else:
                    print("(Over)write original: '{}' because no renames exist.".format(filename))
            elif overwrite_option == 'no_overwrite':
                overwrite = False

                # Compute hash of input image (h)
                temppath = Path(folder_paths.get_temp_directory(), "uploadedup" + osp.splitext(filename)[1])
                os.makedirs(temppath.parent, exist_ok=True)
                with open(temppath, 'wb') as f:
                    image_read = bytes(image.file.read())
                    f.write(image_read)
                h = compute_hash(temppath)

                do_write = True
                if d['original']:
                    h_samename = compute_hash(d['original'])
                    if h == h_samename:
                        do_write = False
                        print("Found duplicate: '{}'".format(d['original']))
                if do_write and d['last_rename']:
                    h_last = compute_hash(d['last_rename'])
                    if h == h_last:
                        filename = d['last_rename'].name
                        do_write = False
                        print("Found duplicate: '{}'".format(d['last_rename']))
                if do_write:
                    print("No duplicate of '{}' found.".format(filename))

            # Set this value again since 'filename' may have changed
            filepath = os.path.join(full_output_folder, filename)

        # Rename input image file if needed (no overwrite)
        if do_write and not overwrite:
            i = 1
            split = os.path.splitext(filename)
            while os.path.exists(filepath):
                filename = f"{split[0]} ({i}){split[1]}"
                filepath = os.path.join(full_output_folder, filename)
                i += 1

        # Write input image
        if do_write:
            if image_save_function is not None:
                image_save_function(image, post, filepath)
            else:
                with open(filepath, "wb") as f:
                    f.write(image_read if image_read is not None else image.file.read())

        return web.json_response({"name" : filename, "subfolder": subfolder, "type": image_upload_type})
    else:
        return web.Response(status=400)

