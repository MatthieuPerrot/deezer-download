#!/usr/bin/env python3

import sys
import os
import re
import argparse
import colorama
from pathlib import Path
from typing_extensions import TypedDict
from configparser import ConfigParser

from deezer import Deezer, TrackFormats
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.settings import load as loadSettings
from deemix.utils import formatListener

# TODO : backlog
# - reimplement image cover : usefull ?
# - app using docker

class LogListenerData:
   n_tracks: int = 0
   idx: int = 1
   identified_tracks: set = set()
   n_new_tracks: int = 0
   n_not_identified_tracks: int = 0

logListenerData = LogListenerData()

class LogListener:
    @classmethod
    def init(cls, data={}):
        cls.data = data

    @classmethod
    def send(cls, key, value=None):
        log = formatListener(key, value)
        log = re.sub(r'^\[.*?\]\s*', '', log, 1) # remove playlist_id prefix
        if key == "downloadInfo":
            state = value['state']
            if state not in ["alreadyDownloaded", "downloaded", "downloadWarn"]:
                return
            title = value['data']['title']
            artist = value['data']['artist']
            print(f"{cls.data.idx}/{cls.data.n_tracks}: ", end="")
            if state == "alreadyDownloaded":
                print(colorama.Style.DIM + log + colorama.Style.RESET_ALL)
            elif state == "downloaded":
                print(colorama.Fore.GREEN + log + colorama.Style.RESET_ALL)
                cls.data.n_new_tracks += 1
            cls.data.idx += 1
        elif key == "downloadWarn":
            print(colorama.Fore.YELLOW + log + colorama.Style.RESET_ALL)
        elif key == "updateQueue":
            if value.get('failed'):
                print(f"{cls.data.idx}/{cls.data.n_tracks}: ", end="")
                print(colorama.Fore.RED + log + colorama.Style.RESET_ALL)
                cls.data.idx += 1
                cls.data.n_not_identified_tracks += 1
            elif value.get('downloaded'):
                cls.data.identified_tracks.add(os.path.basename(value['downloadPath']))


if not sys.platform.startswith('linux'):
    print('Only Linux is supported.')
    sys.exit(1)

# Gestion de la configuration
config = ConfigParser()

if os.environ.get('DEV'):
    print("Starting in development mode.")
    config_path = os.path.join(os.getcwd(), 'settings.ini')
else:
    config_folder = os.path.join(os.path.expanduser("~"), '.config', 'deezer-download')
    os.makedirs(config_folder, exist_ok=True)
    config_path = os.path.join(config_folder, 'settings.ini')

if not os.path.exists(config_path):
    print(f"Could not find config file ({config_path}).")
    sys.exit(1)

print(f"Loading {config_path}")
config.read(config_path)

# Surcharge via variables d'environnement
if "DEEZER_FLAC_QUALITY" in os.environ:
    config["deezer"]["flac_quality"] = os.environ["DEEZER_FLAC_QUALITY"]
if "DEEZER_COOKIE_ARL" in os.environ:
    config["deezer"]["cookie_arl"] = os.environ["DEEZER_COOKIE_ARL"]

# Validation de flac_quality
if "flac_quality" not in config['deezer'] or config['deezer']['flac_quality'].lower() not in ('true', 'false'):
    print("flac_quality must be set to True or False in settings.ini")
    sys.exit(1)

def test_deezer_login():
    """Vérifie la connexion à Deezer."""
    dz = Deezer()
    arl = config['deezer'].get('cookie_arl', '')
    if not arl:
        print(colorama.Fore.RED + "Error: cookie_arl not set in config" + colorama.Style.RESET_ALL)
        sys.exit(1)
    if dz.login_via_arl(arl):
        print(colorama.Fore.GREEN + "Deezer login successful" + colorama.Style.RESET_ALL)
    else:
        print(colorama.Fore.RED + "Deezer login failed" + colorama.Style.RESET_ALL)
        sys.exit(1)
    return dz

def main():
    colorama.init()
    description = """
    check      Verify Deezer login.
    download   Download favorites or playlists.
    """

    parser = argparse.ArgumentParser(prog='deezer-download', formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = parser.add_subparsers(title='command', description=description, dest='command')
    sp.add_parser('check')
    download = sp.add_parser('download')
    download.add_argument('--playlist', type=str, help="Playlist ID", dest='playlist_id')
    download.add_argument("--sync", action="store_true", help="Sync playlist", dest='sync')
    #download.add_argument('--album-cover', action='store_true', help='Download album covers.') # useful ?

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialisation de Deezer et Deemix
    dz = test_deezer_login()

    if args.command == 'check':
        return
    elif args.command == 'download':
        settings = loadSettings(Path('./config') if os.path.exists('./config') else None)
        settings['downloadLocation'] = config['deezer'].get('music_dir', './music')
        settings['localArtworkSize'] = 800
        settings['embeddedArtworkSize'] = 800
        settings['maxBitrate'] = TrackFormats.FLAC if config['deezer'].getboolean('flac_quality') else TrackFormats.MP3_128
        os.makedirs(settings['downloadLocation'], exist_ok=True)

        # Déterminer la source des pistes
        user_id = config['deezer'].get('user_id', '')
        if not user_id:
            print(colorama.Fore.RED + "Error: user_id not set in config" + colorama.Style.RESET_ALL)
            sys.exit(1)
        if args.playlist_id:
            if not args.playlist_id.isnumeric():
                config_key = f"{args.playlist_id}_playlist_id"
                playlist_id = config['deezer'].get(config_key, args.playlist_id)
            else:
                playlist_id = args.playlist_id
            url = f"https://deezer.com/playlist/{playlist_id}"
        else:
            url = f"https://deezer.com/user/{user_id}/loved"

        # Create download object
        plugins = {}
        listener = LogListener()
        try:
            download_object = generateDownloadObject(dz, url, settings['maxBitrate'], plugins, listener)
        except Exception as e:
            print(colorama.Fore.RED + f"Error generating download object: {e}" + colorama.Style.RESET_ALL)
            sys.exit(1)

        playlist_name = str(download_object.title)
        files_already_downloaded = set(os.listdir(Path(settings['downloadLocation']) / f'{playlist_name}'))

        # Download tracks
        print(f"\nSync playlist: {playlist_name}\n")
        logListenerData.n_tracks = len(download_object.collection['tracks'])
        listener.init(logListenerData)
        downloader = Downloader(dz, download_object, settings, listener)
        downloader.start()
 
        # Résumé
        print("\nSummary:")
        print(f" - {colorama.Style.DIM}{len(logListenerData.identified_tracks)}{colorama.Style.RESET_ALL} tracks identified")
        print(f" - {colorama.Fore.GREEN}{logListenerData.n_new_tracks}{colorama.Style.RESET_ALL} new tracks downloaded")
        #print(f" - {colorama.Fore.GREEN}{len(identified_album_covers)}{colorama.Style.RESET_ALL} album covers identified")
        print(f" - {colorama.Fore.RED}{logListenerData.n_not_identified_tracks}{colorama.Style.RESET_ALL} not found")

        # Synchronisation
        delta_tracks = files_already_downloaded - logListenerData.identified_tracks
        #delta_album_covers = files_already_downloaded - set(identified_album_covers.keys()) if args.album_cover else set()
        delta_tracks = [f for f in delta_tracks if f.endswith(('.mp3', '.flac'))]
        #delta_album_covers = [f for f in delta_album_covers if f.endswith('.jpg')]

        if not args.sync:
            if delta_tracks:
                print(colorama.Fore.YELLOW + f"Warning: {len(delta_tracks)} tracks in dest dir not identified" + colorama.Style.RESET_ALL)
            #if delta_album_covers:
            #    print(colorama.Fore.YELLOW + f"Warning: {len(delta_album_covers)} covers in dest dir not identified" + colorama.Style.RESET_ALL)
            return

        if delta_tracks:
            print("\nRemoving extra tracks:")
            for i, file in enumerate(delta_tracks, 1):
                print(f"{i}/{len(delta_tracks)}: {file}")
                os.remove(os.path.join(settings['downloadLocation'], f"{playlist_name}", file))
            print(colorama.Fore.GREEN + f"{len(delta_tracks)} deleted successfully" + colorama.Style.RESET_ALL)

        #if delta_album_covers:
        #    print("\nRemoving extra covers:")
        #    for i, file in enumerate(delta_album_covers, 1):
        #        print(f"{i}/{len(delta_album_covers)}: {file}")
        #        os.remove(os.path.join(settings['downloadLocation'], file))
        #    print(colorama.Fore.GREEN + f"{len(delta_album_covers)} deleted successfully" + colorama.Style.RESET_ALL)

if __name__ == "__main__":
    main()
