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


def update_watchlist(new_watchlist: typing.List[typing.Dict]):
    with watchdog_mutex:
        for fp, d in watchdog_d.items():
            assert d['observer'] is watchdog_observer
            d['observer'].unschedule_all()

        watchdog_d.clear()
        for w_info in new_watchlist:
            filepath = w_info['path']
            if osp.isfile(filepath):
                o = watchdog_observer
                h = Handler()
                h.on_modified = w_info.get('on_modified', lambda e: None)
                h.on_created = w_info.get('on_modified', lambda e: None)
                h.on_modified = w_info.get('on_modified', lambda e: None)
                w = o.schedule(h, path=str(filepath))
                if not o.is_alive():
                    o.start()
                d = {
                    'observer': o,
                    'watcher': w,
                }
                watchdog_d[str(filepath)] = d
            else:
                print("Invalid file: '{}'; will not be added to watchlist.".format(filepath))
        print("Updated watchlist watching {} files".format(len(watchdog_d)))


def get_imagemagick_exe():
    if platform == 'win32':
        return 'magick'
    else: #if platform in ('linux', 'linux2', 'darwin'):
        return 'convert'

