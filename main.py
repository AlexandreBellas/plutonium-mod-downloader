#!/usr/bin/env python3
"""Download a Plutonium T6 mod straight from a server's FastDL (sv_wwwBaseURL)."""

import argparse
import json
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

DEFAULT_FILES = ["mod.ff", "mod.iwd", "mod.all.sabl", "mod.all.sabs", "mod.json"]
SERVERS_API = "https://plutonium.pw/api/servers"
USER_AGENT = "Mozilla/5.0"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def load_env(path: Path) -> dict[str, str]:
    """Read simple KEY=value lines from a .env file next to the script (no external deps)."""
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def open_url(url: str, timeout: float, method: str = "GET"):
    return urlopen(Request(url, method=method, headers={"User-Agent": USER_AGENT}), timeout=timeout)


def find_server_ip(mod: str, timeout: float) -> str | None:
    """Look up the current IP of a server running `mod` in Plutonium's public server list."""
    with open_url(SERVERS_API, timeout) as response:
        servers = json.load(response)
    ips = [s["ip"] for s in servers if f"\\{mod}\\" in f"\\{s.get('codInfo', '')}\\"]
    if not ips:
        return None
    ip = max(set(ips), key=ips.count)
    print(f"Found {ips.count(ip)} server(s) running {mod} on {ip}")
    return ip


def list_folder(url: str, timeout: float, depth: int = 0) -> list[str]:
    """Return file URLs from an HTTP directory listing, recursing into subfolders."""
    try:
        with open_url(url, timeout) as response:
            if "html" not in response.headers.get("Content-Type", ""):
                return []
            parser = LinkParser()
            parser.feed(response.read().decode("utf-8", "replace"))
    except (HTTPError, URLError, TimeoutError):
        return []

    files = []
    for href in parser.links:
        target = urljoin(url, href)
        if not target.startswith(url) or target == url or "?" in href:
            continue
        if target.endswith("/"):
            if depth < 5:
                files += list_folder(target, timeout, depth + 1)
        else:
            files.append(target)
    return files


def format_bytes(count: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            return f"{count:.1f} {unit}" if unit != "B" else f"{count:.0f} B"
        count /= 1024
    return ""


def show_progress(name: str, done: int, size: int, started: float) -> None:
    elapsed = time.monotonic() - started
    speed = done / elapsed if elapsed > 0.5 else 0
    rate = f"{format_bytes(speed)}/s" if speed else "--/s"
    if size:
        filled = done * 30 // size
        bar = "#" * filled + "-" * (30 - filled)
        eta = f"{int((size - done) / speed) // 60}:{int((size - done) / speed) % 60:02d}" if speed else "--:--"
        line = f"{name} [{bar}] {done * 100 // size:3d}% {format_bytes(done)}/{format_bytes(size)} {rate} ETA {eta}"
    else:
        line = f"{name} {format_bytes(done)} {rate} (size unknown)"
    print(f"\r  get   {line}\033[K", end="", flush=True)


def download(url: str, dest: Path, timeout: float, retries: int) -> bool:
    for attempt in range(1, retries + 1):
        try:
            print(f"  conn  {url}", end="", flush=True)
            with open_url(url, timeout) as response:
                size = int(response.headers.get("Content-Length") or 0)
                if dest.exists() and size and dest.stat().st_size == size:
                    print(f"\r  skip  {dest} (already complete)\033[K")
                    return True
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".part")
                done, started, last_update = 0, time.monotonic(), 0.0
                show_progress(dest.name, done, size, started)
                with tmp.open("wb") as fh:
                    while chunk := response.read1(1 << 16):
                        fh.write(chunk)
                        done += len(chunk)
                        if time.monotonic() - last_update > 0.2:
                            show_progress(dest.name, done, size, started)
                            last_update = time.monotonic()
                show_progress(dest.name, done, size, started)
                tmp.replace(dest)
                print(f"\n  ok    {dest} ({format_bytes(done)} in {time.monotonic() - started:.1f}s)")
                return True
        except HTTPError as e:
            print(f"\r  fail  {url}: HTTP {e.code}\033[K")
            return False
        except (URLError, TimeoutError, ConnectionError) as e:
            print(f"\r  retry {attempt}/{retries} {url}: {e}\033[K")
            time.sleep(2 * attempt)
    return False


def main() -> int:
    env = load_env(Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=env.get("BASE"), help="Server sv_wwwBaseURL (default: http://<auto IP>:<port>)")
    parser.add_argument("--port", type=int, default=int(env.get("PORT", 8081)), help="FastDL port, used with auto IP")
    parser.add_argument("--mod", default=env.get("MOD"), help="Mod path / fs_game, e.g. mods/ADN-Server-Zombies")
    parser.add_argument("--token", default=env.get("TOKEN", ""), help="Per-session download token from the request path")
    parser.add_argument("--out", type=Path, default=Path(env.get("OUT", Path.cwd())), help="Folder to receive mods/<name>/")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("files", nargs="*", help="File names to fetch (skips listing / defaults)")
    args = parser.parse_args()

    if not args.mod:
        print("No mod set; pass --mod mods/<name> or set MOD in .env")
        return 1

    if not args.base:
        ip = find_server_ip(args.mod, args.timeout)
        if not ip:
            print(f"No online server is running {args.mod}; pass --base explicitly")
            return 1
        args.base = f"http://{ip}:{args.port}"

    prefix = f"{quote(args.token.strip('/'))}/" if args.token.strip("/") else ""
    mod_url = f"{args.base.rstrip('/')}/{prefix}{quote(args.mod.strip('/'))}/"
    print(f"Mod URL: {mod_url}")

    if args.files:
        urls = [urljoin(mod_url, quote(name)) for name in args.files]
    else:
        urls = list_folder(mod_url, args.timeout)
        if urls:
            print(f"Directory listing found: {len(urls)} file(s)")
        else:
            print("No directory listing, trying default T6 mod files")
            urls = [urljoin(mod_url, name) for name in DEFAULT_FILES]

    base_path = urlparse(mod_url).path
    results = []
    for url in urls:
        relative = unquote(urlparse(url).path[len(base_path):])
        results.append(download(url, args.out / args.mod / relative, args.timeout, args.retries))

    print(f"\n{sum(results)}/{len(results)} file(s) downloaded into {args.out / args.mod}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
