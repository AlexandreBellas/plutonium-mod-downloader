# plutonium-mod-downloader

Download a Plutonium T6 (BO2) server mod by hand when the in-game FastDL fails. Pure Python stdlib, no dependencies.

MIT licensed. See [LICENSE](LICENSE).

## How it works

The mod downloads over plain HTTP, but gated servers put a one-time token in the URL that the client never saves. Capture mode reads that token off the wire as you connect, then downloads the files itself.

## Setup

```bash
cp .env.example .env   # then set MOD
```

## Usage — capture mode (recommended)

Prerequisites:
- Linux: `sudo` + `tcpdump`.
- Windows: run the terminal as Administrator + install Wireshark (includes `tshark` and Npcap).

1. Run it from your `storage/t6` folder:

```bash
sudo python main.py --capture          # Windows: python main.py --capture (as Administrator)
```

2. Launch BO2 and connect to the server. **Capture fires only when you connect to a server, not when you open the game.**
3. If the mod is already installed, delete one of its files first so the client re-downloads.

It grabs the host, port, and token, then downloads the **whole mod** (via the server's directory listing). Pass filenames to fetch only a subset:

```bash
sudo python main.py --capture mod.ff           # just one file
```

## Usage — manual mode

With a known `BASE`/`TOKEN`:

```bash
python main.py            # default T6 mod files
python main.py mod.ff     # specific file(s)
```

Files land in `<out>/mods/<name>/`. Run from your `storage/t6` folder, or set `OUT`.

## Config

Set in `.env` or override with a flag. Flags win.

| Key / flag | Default | Meaning |
| --- | --- | --- |
| `MOD` / `--mod` | — (required) | Mod path, e.g. `mods/ADN-Server-Zombies` |
| `--capture` | off | Sniff host/port/token/files from a live join (needs admin + tcpdump/tshark) |
| `--capture-timeout` | `180` | Seconds to wait for the join while capturing |
| `--iface` | auto | Capture interface (`any` on Linux; tshark's default on Windows) |
| `TOKEN` / `--token` | empty | Per-session download token (capture fills this in) |
| `PORT` / `--port` | `8081` | FastDL port, used with auto-detected IP (manual mode) |
| `BASE` / `--base` | auto | Full `sv_wwwBaseURL`; skips IP auto-detection |
| `OUT` / `--out` | current dir | Folder that receives `mods/<name>/` |
| `--timeout` | `30` | Per-request timeout (s) |
| `--retries` | `4` | Retries per file |
| positional | — | Exact file names to fetch (a subset); omit to download the whole mod |

With no filenames given, it downloads the whole mod from the server's directory listing. If listing is blocked, it falls back to the files seen during capture, else to `mod.ff`, `mod.iwd`, `mod.all.sabl`, `mod.all.sabs`, `mod.json`.

## Install the mod

Copy the downloaded `mods/<name>/` into `%LOCALAPPDATA%\Plutonium\storage\t6\mods\`. On Linux (Wine/Proton), that path is inside the game's prefix.

## Example (ADN zombies server)

```bash
# .env: MOD=mods/ADN-Server-Zombies
cd /path/to/Plutonium/storage/t6
sudo python main.py --capture
# then launch BO2 and join any ADN server
```
