# Description
A minimalist app to download and sync mp3 locally, on top of deemix module


# Usage (playlist name/id links are defined in settings.ini)
```bash
$ ./scripts/deezer-download.py download --playlist bob --sync
```


# Example of config file
```bash
$ cat `~/.config/deezer-download/settings.ini`  
```

```ini
;;; base config

[deezer]
; replace COOKIE_ARL with a valid arl cookie value
; login manually using your web browser and take the arl cookie
cookie_arl = COOKIE_ARL

; download flac files (if False mp3 is used)
flac_quality = False

; user id : replace USER_ID with a valid user id
user_id = USER_ID

; playlist ids : replace PLAYLIST_ID with a valid playlist id
bob_playlist_id = PLAYLIST_ID

; output music directory
music_dir = ~/Musique/deezer/
```
