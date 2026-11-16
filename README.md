# plutonium-mod-downloader

Download a Plutonium T6 (BO2) server mod by hand when the in-game FastDL fails. Pure Python stdlib, no dependencies.

MIT licensed. See [LICENSE](LICENSE).

## How it works

The client downloads mods over plain HTTP from the server's `sv_wwwBaseURL`. This script hits that same URL. It finds the server's current IP from Plutonium's public server list, then fetches the mod files, showing live progress.

## Setup

```bash
cp .env.example .env   # then fill in MOD and TOKEN
```

## Usage

```bash
python main.py            # fetch default T6 mod files
python main.py mod.ff     # fetch specific file(s)
```

Files land in `<out>/mods/<name>/`. Run it from your `storage/t6` folder, or set `OUT`.

## The token

Mods behind a gated host need a per-session token: the `/rb.../` segment the client puts in the request path. It changes every time you join, so capture a fresh one each run.

Join a server, then capture the request:

```bash
sudo tcpdump -i any -n -l -A -s0 'tcp dst port 8081 and tcp[((tcp[12]&0xf0)>>2):4] = 0x47455420' | sed 's/[^[:print:]]//g'
```

Copy the token from the `GET /<token>/mods/...` line into `TOKEN` in `.env`, or pass `--token`.

## Config

Set in `.env` or override with a flag. Flags win.

| Key / flag | Default | Meaning |
| --- | --- | --- |
| `MOD` / `--mod` | — (required) | Mod path, e.g. `mods/ADN-Server-Zombies` |
| `TOKEN` / `--token` | empty | Per-session download token |
| `PORT` / `--port` | `8081` | FastDL port, used with auto-detected IP |
| `BASE` / `--base` | auto | Full `sv_wwwBaseURL`; skips IP auto-detection |
| `OUT` / `--out` | current dir | Folder that receives `mods/<name>/` |
| `--timeout` | `30` | Per-request timeout (s) |
| `--retries` | `4` | Retries per file |
| positional | — | Exact file names; skips listing and defaults |

When no files are given, it reads the server's folder listing; if that's blocked, it falls back to `mod.ff`, `mod.iwd`, `mod.all.sabl`, `mod.all.sabs`, `mod.json`.

## Install the mod

Copy the downloaded `mods/<name>/` into `%LOCALAPPDATA%\Plutonium\storage\t6\mods\`. On Linux (Wine/Proton), that path is inside the game's prefix.

## Example (ADN zombies server)

```bash
# .env: MOD=mods/ADN-Server-Zombies, TOKEN=<token from tcpdump>
python main.py mod.ff
```
