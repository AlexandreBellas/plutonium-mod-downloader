# Plutonium manual mod downloader

Download a Plutonium T6 (BO2) server mod by hand when the in-game download keeps failing even after several retries.

Pure Python stdlib, no dependencies.

MIT licensed. See [LICENSE](LICENSE).

## Quick start (tl;dr section)

A few super straightforward examples for you to hit the ground running. These commands assume you don't have the full mod downloaded or just have a partial version of it.

The commands will manually download the files; then it's about you moving the files to the correct location (ie. `/path/to/Plutonium/storage/t6/mods`).

### Dummy server example

```bash
# All files
sudo python main.py --mod mods/YOUR_MOD_FOLDER_NAME --capture
# Or: just one file (eg. mod.ff)
sudo python main.py --mod mods/YOUR_MOD_FOLDER_NAME --capture mod.ff

# >> then launch BO2 and join any game from that given server <<
```

Note that `YOUR_MOD_FOLDER_NAME` in the `mods/YOUR_MOD_FOLDER_NAME` template refers to the automatically created folder within `/path/to/Plutonium/storage/t6/mods`. If it's unclear, proceed reading towards section [How it words](#how-it-works).

### Real server: ADN zombies server

```bash
# All files
sudo python main.py --mod mods/ADN-Server-Zombies --capture
# Or: one file
sudo python main.py --mod mods/ADN-Server-Zombies --capture mod.ipak

# then launch BO2 and join any ADN server
```

### Real server: BX7 server

```bash
sudo python main.py --mod mods/BX7_MOD --capture # mod.ff

# then launch BO2 and join any BX7 server
```

## How it works

The mod downloads over plain HTTP, but gated servers put a one-time token in the URL that the client never saves. Capture mode reads that token off the wire as you connect, then downloads the files itself.

## Usage — capture mode (recommended)

Prerequisites:

- Linux: `sudo` + `tcpdump`.
- Windows: run the terminal as Administrator + install Wireshark (includes `tshark` and Npcap).

1. Run it from your `/path/to/Plutonium/storage/t6` folder:

```bash
sudo python main.py --mod mods/YOUR_MOD_FOLDER_NAME --capture   # Windows: drop sudo, run as Administrator
```

Note that `YOUR_MOD_FOLDER_NAME` refers to the automatically created folder name within `/path/to/Plutonium/storage/t6/mods`. Every server with mods will have their own specific name.

2. Launch BO2 and connect to the server. **Capture fires only when you connect to a server.**
3. Once Plutonium starts downloading a file, the command will capture the necessary information and start the manual downloading.

It grabs the host, port, and token, then downloads the **whole mod** (via the server's directory listing). Pass filenames to fetch only a subset:

```bash
sudo python main.py --mod mods/YOUR_MOD_FOLDER_NAME --capture mod.ff   # just one file
```

## Usage — manual mode

Pass the server's `--base` and `--token` yourself:

```bash
python main.py --mod mods/YOUR_MOD_FOLDER_NAME --base http://1.2.3.4:8081 --token [TOKEN]            # whole mod
python main.py --mod mods/YOUR_MOD_FOLDER_NAME --base http://1.2.3.4:8081 --token [TOKEN] mod.ff     # specific file(s)
```

Omit `--base` to auto-detect the IP from Plutonium's public list. Files land in `<out>/mods/<name>/`; run from your `storage/t6` folder or pass `--out`.

## Config

| Flag | Default | Meaning |
| --- | --- | --- |
| `--mod` | — (required) | Mod path, e.g. `mods/ADN-Server-Zombies` |
| `--capture` | off | Sniff host/port/token/files from a live join (needs admin + tcpdump/tshark) |
| `--capture-timeout` | `180` | Seconds to wait for the join while capturing |
| `--iface` | auto | Capture interface (`any` on Linux; tshark's default on Windows) |
| `--token` | empty | Per-session download token (capture fills this in) |
| `--port` | `8081` | FastDL port, used with auto-detected IP (manual mode) |
| `--base` | auto | Full `sv_wwwBaseURL`; skips IP auto-detection |
| `--out` | current dir | Folder that receives `mods/<name>/` |
| `--timeout` | `30` | Per-request timeout (s) |
| `--retries` | `4` | Retries per file |
| positional | — | Exact file names to fetch (a subset); omit to download the whole mod |

With no filenames given, it downloads the whole mod from the server's directory listing. If listing is blocked, it falls back to the files seen during capture, else to `mod.ff`, `mod.iwd`, `mod.all.sabl`, `mod.all.sabs`, `mod.json`.

## Install the mod

Copy the downloaded `mods/<name>/` into `/path/to/Plutonium/storage/t6/mods`, then you're good to go.
