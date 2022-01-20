## Usage
```
usage: backman.py [-h] [--no-confirm] [--no-sync] [--interactive] [--mirror] [--delete] [--map MAP]

Simple python wrapper for rsync to allow ease of many paths or an interactive experience with confirmation dialogs.

options:
  -h, --help     show this help message and exit
  --no-confirm   Skip any confirmation dialogs
  --no-sync      Skip the initial sync src -> dst
  --interactive  Only update certain file paths based on user choice
  --mirror       Sync src -> dst, then dst -> src
  --delete       Delete files on remote not on source (after sync, unless also --no-sync)
  --map MAP      Files to sync together (Default: filesMap.json)
```

## Examples
```bash
./backman.py --interactive --map filesMap-real.json
```
Loads file path mapping from filesMap-real.json and provides an interactive console for management:

Output:
```
File map to choose from:
0  ~/Documents/ backSrv ~/Documents/
1  ~/Downloads/ backSrv ~/Downloads/
2  /srv/http/test/ backSrv ~/test-www/
3  /srv/http/test/ backSrv2 ~/test=www/
Input id (or 'q' to quit): 
```

## JSON File Mapping
Each file path mapping can have one source and multiple destinations.

### Example JSON to sync local files to backSrv
Also syncs local http server to two backSrvs (backSrv1, backSrv2)
```JSON
[{
        "host": "",
        "dirs": [
                 {"src": "~/Documents/", "dests": [{"host": "backSrv", "dest": "~/Documents/"}]},
                 {"src": "~/Downloads/", "dests": [{"host": "backSrv", "dest": "~/Downloads/"}]},
                 {"src": "/srv/http/test/", "dests": [{"host": "backSrv", "dest": "~/test-www/"},{"host": "backSrv2", "dest": "~/test-www/"}]}
                ]
}]
```
