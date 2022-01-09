#!/usr/bin/env python3
# A simple wrapper that makes it easy to debug Proton apps
# using GDB.
#
# Dependent on ProtonTricks which is GPLv3.
# Hence this script is licensed under GPLv3.

import argparse
import logging
import os
import sys
import string
import subprocess
import time
import urllib.request
from protontricks import *
from pathlib import Path

logger = logging.getLogger("protongdb")

def enable_logging(info=False):
    level = logging.INFO if info else logging.WARNING
    logging.basicConfig(
        stream=sys.stderr, level=level,
        format="%(name)s (%(levelname)s): %(message)s")

def normalize_path(path):
    if not path:
        return ""
    return path.replace('\\', '/')

def get_launch_executable(appid, appinfo)   :
    app_infos = []
    for app in appinfo:
        if app["appinfo"]["appid"] == appid:
            launch_infos = app["appinfo"]["config"]["launch"]
            for launch_info in launch_infos.values():
                if not ("config" in launch_info and "oslist" in launch_info["config"]) or ("windows" in launch_info["config"]["oslist"]):
                    beta_key = None
                    if "config" in launch_info:
                        beta_key = launch_info["config"].get("betakey")
                    arguments = launch_info.get("arguments")
                    arguments = arguments.split() if arguments else []
                    app_infos.append((launch_info.get("description"), normalize_path(launch_info.get("workingdir")), normalize_path(launch_info["executable"]), beta_key, arguments))
    return app_infos

def prepend_args(x, y, delim):
    return (y + delim + x) if y else x

def append_args(x, y, delim):
    return (x + delim + y) if y else x

def list_to_space_str(lst):
    return ' '.join(lst)

def list_to_space_str_prefix(lst, prefix):
    return " " + list_to_space_str(lst) if lst else ""

def safe_cast(val, to_type, default=None):
    try:
        return to_type(val)
    except (ValueError, TypeError):
        return default

def main(args=None):
    parser = argparse.ArgumentParser(
        description="Wrapper for debugging Steam Play/Proton games with GDB.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="print debug information")

    parser.add_argument("appid", type=int, nargs="?", default=None)
    parser.add_argument("app_args", nargs=argparse.REMAINDER)

    args = parser.parse_args(args)

    enable_logging(args.verbose)

    appid = args.appid
    user_app_args = args.app_args

    if not appid:
        parser.print_help()
        return

    steam_path, steam_root = find_steam_path()
    steam_lib_paths = get_steam_lib_paths(steam_path)

    if not steam_lib_paths:
        logger.error("Could not find Steam lib paths.")
        return

    steam_apps = get_steam_apps(steam_root, steam_path, steam_lib_paths)
    if not steam_apps:
        logger.error("Could not find Steam apps.")
        return

    game_app = None
    for steam_app in steam_apps:
        if steam_app.appid == appid:
            game_app = steam_app

    if not game_app:
        logger.error(f"Cannot find game with appid: {appid}")
        return

    if not game_app.prefix_path:
        logger.error(f"Cannot find prefix for appid: {appid}")
        return

    proton_app = find_proton_app(steam_path, steam_apps, appid)

    if not proton_app:
        logger.error(f"Cannot find a Proton app for appid: {appid}")
        return

    appinfo_path = steam_path / "appcache" / "appinfo.vdf"
    appinfo = get_appinfo_sections(appinfo_path)
    if not appinfo:
        logger.error(f"Cannot find appinfo at {appinfo_path}")
        return

    app_infos = get_launch_executable(appid, appinfo)
    if not app_infos:
        logger.error(f"Cannot find launch executable from {appinfo_path}")
        return

    # Let the user pick an app configuration, if we only have one,
    # just use that.
    if len(app_infos) == 1:
        _, working_dir, launch_executable, beta_key, app_config_args = app_infos[0]
    else:
        for x in range(0, len(app_infos)):
            description, working_dir, launch_executable, beta_key, app_config_args = app_infos[x]
            beta_key = None
            beta_str = ""
            if beta_key:
                beta_str = f" | Beta: {beta_key} |"
            print(f"[{x}] {description} ({launch_executable}{list_to_space_str_prefix(app_config_args, ' ')}){beta_str}")
        config_idx = safe_cast(input(f"Select a game configuration to run: "), int)
        print(config_idx)
        if config_idx == None or config_idx not in range(0, len(app_infos)):
            logger.error("Invalid app configuration.")
            return
        _, working_dir, launch_executable, beta_key, app_config_args = app_infos[config_idx]
            
    # Dump wine-reload in /tmp so we can source
    # it from the gdb script.
    urllib.request.urlretrieve(
        "https://gist.githubusercontent.com/rbernon/cdbdc1b0e892f91e7449fcf3dda80bb7/raw/d8cf549bf751d99ed0fe515e36f99ff5c01b7287/WineReload.py",
        "/tmp/winereload.py"
    )

    gdb_commands = [
        "set confirm off",
        "set pagination off",
        "handle SIGUSR1 noprint nostop",
        "handle SIGSYS noprint nostop",
        "source /tmp/winereload.py",
    ]

    with open('/tmp/.protongdb_args', 'w') as f:
        for command in gdb_commands:
            f.write(f"{command}\n")

    executable_path = game_app.install_path / launch_executable
    working_dir = game_app.install_path / working_dir if working_dir else game_app.install_path
    app_args = app_config_args + user_app_args

    print(f"Proton: {proton_app.name} ({proton_app.appid})")
    print(f"App: {game_app.name} ({game_app.appid})")
    print(f"Using install dir: {game_app.install_path}")
    print(f"Using Proton prefix: {game_app.prefix_path}")
    print("--------------------------------------------")
    print(f"Using working dir: {working_dir}")
    print(f"Using launch executable: {executable_path}")
    print(f"Using arguments: {list_to_space_str(app_args)}")
    print("--------------------------------------------")
    print("When you experience a crash, run 'wine-reload' before trying to get a backtrace.")
    confirm = input("This all look good? Ready to start debugging? [Y/n] ").upper()
    if len(confirm) > 0 and confirm[0] == 'N':
        return

    env_vars = dict(os.environ)
    env_vars["PATH"] = append_args(f"{proton_app.install_path}/files/bin", env_vars.get("PATH"), ":")
    env_vars.setdefault("WINEDEBUG", "-all")
    env_vars["WINEDLLPATH"] = prepend_args(f"{proton_app.install_path}/files/lib64/wine:{proton_app.install_path}/files/lib/wine", env_vars.get("WINEDLLPATH"), ":")
    env_vars.setdefault("LD_LIBRARY_PATH", append_args(f"{proton_app.install_path}/files/lib64/:{proton_app.install_path}/files/lib/:{game_app.install_path}", env_vars.get("LD_LIBRARY_PATH"), ":"))
    env_vars.setdefault("WINEPREFIX", str(game_app.prefix_path))
    env_vars.setdefault("WINEESYNC", "1")
    env_vars.setdefault("WINEFSYNC", "1")
    env_vars.setdefault("SteamGameId", str(appid))
    env_vars.setdefault("SteamAppId", str(appid))
    env_vars["WINEDLLOVERRIDES"] = append_args("steam.exe=b;dotnetfx35.exe=b;dxvk_config=n;d3d11=n;d3d10=n;d3d10core=n;d3d10_1=n;d3d9=n;dxgi=n", env_vars.get("WINEDLLOVERRIDES"), ";")
    env_vars.setdefault("STEAM_COMPAT_CLIENT_INSTALL_PATH", steam_path)
    env_vars.setdefault("WINE_LARGE_ADDRESS_AWARE", "1")
    env_vars["GST_PLUGIN_SYSTEM_PATH_1_0"] = prepend_args(f"{proton_app.install_path}/files/lib64/gstreamer-1.0:{proton_app.install_path}/files/lib/gstreamer-1.0", env_vars.get("GST_PLUGIN_SYSTEM_PATH_1_0"), ":")
    env_vars.setdefault("WINE_GST_REGISTRY_DIR", f"{game_app.prefix_path}/gstreamer-1.0/")

    subprocess.Popen([f"{proton_app.install_path}/files/bin/wine", "steam.exe", str(executable_path)] + app_args, stdin=subprocess.DEVNULL, close_fds=True, cwd=str(working_dir), env=env_vars)

    # Bit of a hack, to do this properly we'd need to extract the child process'
    # PID from steam.exe somehow, and this is good enough for now assuming Wine
    # abnd steam.exe are actually working.
    process_name = os.path.basename(launch_executable)[:15]
    pid = None
    # Timeout after 3 seconds of trying to find the pid.
    timeout = time.time() + 3
    while not pid and time.time() < timeout:
        try:
            pid = int(subprocess.check_output(["pidof", process_name]))
        except subprocess.CalledProcessError:
            pid = None

    if not pid:
        logger.error(f"Couldn't find pid to attach for {process_name}")
        return

    subprocess.call(["gdb", "-x", "/tmp/.protongdb_args", "-p", str(pid)])
    subprocess.call(["kill", "-9", str(pid)])
    os.remove("/tmp/.protongdb_args")

if __name__ == "__main__":
    main()
