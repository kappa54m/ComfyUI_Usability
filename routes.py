from .common import update_watchlist, get_imagemagick_exe

from server import PromptServer
import folder_paths

from aiohttp import web

import os
import os.path as osp
from pathlib import Path
import subprocess
import shutil
import hashlib
import re
import traceback
import json


routes = PromptServer.instance.routes
magick_exe = get_imagemagick_exe()


@routes.post('/kap/upload/image-dedup')
async def upload_image_dedup_endpoint(req):
    post = await req.post()
    return image_upload_dedup(post)


@routes.post('/kap/upload/update-preview')
async def update_preview_endpoint(req):
    post = await req.post()

    img_fp = post.get('image_path')
    success = osp.isfile(osp.expanduser(img_fp))
    if not success:
        print("'{}' is not a valid image file. Failed to update preview.".format(img_fp))
    else:
        preview_gen_d = generate_preview(img_fp, expanduser=True)
        success = preview_gen_d['success']

    if not success:
        return web.Response(status=400)
    else:
        return web.json_response({
            'preview_filename': preview_gen_d['preview_filename'],
            'preview_filepath': preview_gen_d['preview_filepath'],
            'preview_image_type': "temp",
        })


@routes.post('/kap/upload/update-watchlist')
async def update_watchlist_endpoint(req):
    post = await req.post()

    img_fps = json.loads(post.get("all_image_paths"))

    # Update watchlist
    watchlist = []
    temp_dir = folder_paths.get_temp_directory()
    successful_file_indices = []
    for ifp, fp in enumerate(img_fps):
        if not osp.isfile(osp.expanduser(fp)):
            print("update_preview - invalid file: '{}'".format(fp))
            continue

        # Generate preview file
        preview_gen_d = generate_preview(fp, expanduser=True)
        if not preview_gen_d['success']:
            print("Failed to generate preview for '{}'".format(fp))
            continue

        def on_modified(_evt, fp=fp):
            print("'{}' modified".format(fp))
            _preview_gen_d = generate_preview(fp, expanduser=True)
            if not _preview_gen_d['success']:
                print("Failed to generate preview for '{}'".format(fp))
            else:
                signal_update_preview(fp, _preview_gen_d['preview_filename'])

        watchlist.append({
            'path': fp,
            'on_modified': on_modified,
            'extra': {
                'preview_name': preview_gen_d['preview_filename'],
                'preview_path': preview_gen_d['preview_filepath'],
            }
        })
        successful_file_indices.append(ifp)

    update_watchlist(watchlist, expanduser=True)

    preview_names_for_resp = []
    for ifp, fp in enumerate(img_fps):
        if ifp not in successful_file_indices:
            preview_names_for_resp.append("")
        else:
            preview_names_for_resp.append([w['extra']['preview_name'] for w in watchlist if w['path'] == fp][0])
    return web.json_response({
        "success": [i in successful_file_indices for i in range(len(img_fps))],
        "preview_names": preview_names_for_resp,
        "preview_images_type": "temp",
        "watchlist_size": len(watchlist),
    })


def generate_preview(fp, expanduser=True):
    """
    Generates preview image inside [ComfyUI]/temp/ of the image `fp` points to.
    """
    fp_real = osp.expanduser(fp) if expanduser else fp
    preview_fn_noext = "preview_" + hashlib.md5(fp.encode('utf-8')).hexdigest()
    ext = osp.splitext(fp)[1][1:].lower()
    need_conversion = False
    if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        preview_fn = preview_fn_noext + "." + ext
    elif ext in ('psd', 'xcf'):
        preview_fn = preview_fn_noext + ".png"
        need_conversion = True
    else:
        print("Unrecognized image format: {}".format(fp))
        preview_fn = None

    if not preview_fn:
        return {'success': False}

    temp_dir = folder_paths.get_temp_directory()
    preview_fp = osp.join(temp_dir, preview_fn)

    os.makedirs(temp_dir, exist_ok=True)
    success = True
    if not need_conversion:
        if osp.isdir(preview_fp):
            shutil.rmtree(preview_fp)
        shutil.copy(fp_real, preview_fp)
    else:
        try:
            print("Converting '{}' to png..".format(fp))
            return_code = subprocess.call([magick_exe, str(fp_real), preview_fp])
            success = return_code == 0
        except subprocess.CalledProcessError:
            print("Unable to convert image to png: '{}':".format(fp))
            traceback.print_exc()
            success = False

    if success:
        print("Preview for '{}' generated at '{}'".format(fp, preview_fp))

    return {
        'success': success,
        'preview_filename': preview_fn,
        'preview_filepath': preview_fp,
    }


def signal_update_preview(image_fp, preview_filename):
    """
        Message to javascript to update preview image to the new one (that should have been generated on the
        server via generate_preview prior.

        `image_fp` must be the exact string received from the JS side.
    """
    preview_path = Path(folder_paths.get_temp_directory(), preview_filename)
    if not preview_path.is_file():
        print("Preview file does not exist: '{}'".format(preview_path))
        return False

    d = {
        "path": image_fp,
        "preview_filename": preview_filename,
        "preview_type": "temp"
    }

    PromptServer.instance.send_sync("kap-update-preview", d)

    return True

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

