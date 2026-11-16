#!/usr/bin/env python3
"""Download a Plutonium T6 mod straight from a server's FastDL (sv_wwwBaseURL)."""

import argparse
import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
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
    return urlopen(
        Request(url, method=method, headers={"User-Agent": USER_AGENT}), timeout=timeout
    )


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
        eta = (
            f"{int((size - done) / speed) // 60}:{int((size - done) / speed) % 60:02d}"
            if speed
            else "--:--"
        )
        line = f"{name} [{bar}] {done * 100 // size:3d}% {format_bytes(done)}/{format_bytes(size)} {rate} ETA {eta}"
    else:
        line = f"{name} {format_bytes(done)} {rate} (size unknown)"
    print(f"\r  get   {line}\033[K", end="", flush=True)


def download(url: str, dest: Path, timeout: float, retries: int) -> int:
    """Download `url` to `dest`. Returns 0 on success, the HTTP status on an HTTP error, else -1."""
    for attempt in range(1, retries + 1):
        try:
            print(f"  conn  {url}", end="", flush=True)
            with open_url(url, timeout) as response:
                size = int(response.headers.get("Content-Length") or 0)
                if dest.exists() and size and dest.stat().st_size == size:
                    print(f"\r  skip  {dest} (already complete)\033[K")
                    return 0
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
                print(
                    f"\n  ok    {dest} ({format_bytes(done)} in {time.monotonic() - started:.1f}s)"
                )
                return 0
        except HTTPError as e:
            print(f"\r  fail  {url}: HTTP {e.code}\033[K")
            return e.code
        except (URLError, TimeoutError, ConnectionError) as e:
            print(f"\r  retry {attempt}/{retries} {url}: {e}\033[K")
            time.sleep(2 * attempt)
    return -1


def is_admin() -> bool:
    """True when the process can capture packets (root on POSIX, elevated on Windows)."""
    if os.name == "nt":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except (AttributeError, OSError):
            return False
    return os.geteuid() == 0


def match_host(line: bytes) -> tuple[str, int] | None:
    """Parse the destination `> <ip>.<port>:` from a tcpdump header line."""
    m = re.search(rb"> (\d+\.\d+\.\d+\.\d+)\.(\d+):", line)
    return (m.group(1).decode(), int(m.group(2))) if m else None


def match_get(line: bytes, mod: str) -> tuple[str, str] | None:
    """Parse (token, relative_file) from a `GET /<token>/<mod>/<file>` payload line."""
    m = re.search(rb"GET /(\S+?/)?" + re.escape(mod.encode()) + rb"/(\S+)", line)
    if not m:
        return None
    token = (m.group(1) or b"").decode("ascii", "replace").strip("/")
    return token, m.group(2).decode("ascii", "replace").rstrip("/")


def parse_fields(line: bytes, mod: str) -> tuple[str, str, str] | None:
    """Parse (base_url, token, file) from a tshark `uri<TAB>ip.dst<TAB>tcp.dstport` line."""
    parts = line.decode("ascii", "replace").rstrip().split("\t")
    if len(parts) < 3 or not all(parts[:3]):
        return None
    uri, ip, port = parts[0], parts[1], parts[2]
    hit = match_get(b"GET " + uri.encode(), mod)
    return (f"http://{ip}:{port}", hit[0], hit[1]) if hit else None


def _reader(stream, lines: queue.Queue) -> None:
    for line in iter(stream.readline, b""):
        lines.put(line)
    lines.put(None)


def capture_download(mod: str, timeout: float, iface: str | None) -> tuple[str, str, list[str]] | None:
    """Sniff the client's connect attempt and return (base_url, token, files) for `mod`."""
    if not is_admin():
        print("Capture needs packet access: re-run with sudo (Linux) or as Administrator (Windows)")
        return None
    exe = shutil.which("tcpdump") or shutil.which("tshark")
    if not exe:
        print("Install tcpdump (Linux) or tshark/Wireshark (Windows), or pass --base/--token/files manually")
        return None

    use_tshark = "tshark" in Path(exe).name.lower()
    if iface is None:
        iface = None if os.name == "nt" else "any"
    if use_tshark:
        flt = f'http.request.method=="GET" && http.request.uri contains "{mod}"'
        cmd = [exe, "-l", "-Q", "-T", "fields", "-e", "http.request.uri", "-e", "ip.dst", "-e", "tcp.dstport", "-Y", flt]
        if iface:
            cmd = [exe, "-i", iface, *cmd[1:]]
    else:
        bpf = "tcp[((tcp[12]&0xf0)>>2):4] = 0x47455420"  # TCP payload starts with "GET "
        cmd = [exe, "-i", iface or "any", "-n", "-l", "-A", "-s0", bpf]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, lines), daemon=True).start()

    print(f"Listening for a download of {mod}. Connect to the server now...")
    base, token, files = None, "", []
    last_host, deadline, idle_until = None, time.monotonic() + timeout, None
    try:
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1.0)
            except queue.Empty:
                if idle_until and time.monotonic() > idle_until:
                    break
                continue
            if line is None:
                break
            if use_tshark:
                hit = parse_fields(line, mod)
                if not hit:
                    continue
                base, token, rel = base or hit[0], token or hit[1], hit[2]
            else:
                host = match_host(line)
                if host:
                    last_host = host
                got = match_get(line, mod)
                if not got or not last_host:
                    continue
                base = base or f"http://{last_host[0]}:{last_host[1]}"
                token, rel = token or got[0], got[1]
            if rel not in files:
                files.append(rel)
                print(f"  + {rel}")
            idle_until = time.monotonic() + 5
    finally:
        proc.terminate()

    if not base or not files:
        print("Captured nothing. Make sure you connected while a download was needed (delete a mod file first).")
        return None
    return base, token, files


def main() -> int:
    env = load_env(Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=env.get("BASE"),
        help="Server sv_wwwBaseURL (default: http://<auto IP>:<port>)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(env.get("PORT", 8081)),
        help="FastDL port, used with auto IP",
    )
    parser.add_argument(
        "--mod",
        default=env.get("MOD"),
        help="Mod path / fs_game, e.g. mods/ADN-Server-Zombies",
    )
    parser.add_argument(
        "--token",
        default=env.get("TOKEN", ""),
        help="Per-session download token from the request path",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(env.get("OUT", Path.cwd())),
        help="Folder to receive mods/<name>/",
    )
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Sniff host/port/token/files from a live join (needs sudo)",
    )
    parser.add_argument(
        "--capture-timeout",
        type=float,
        default=180,
        help="Seconds to wait for the join while capturing",
    )
    parser.add_argument(
        "--iface",
        default=None,
        help="Capture interface (default: 'any' on Linux, tshark's default on Windows)",
    )
    parser.add_argument(
        "files", nargs="*", help="File names to fetch (skips listing / defaults)"
    )
    args = parser.parse_args()

    if not args.mod:
        print("No mod set; pass --mod mods/<name> or set MOD in .env")
        return 1

    captured_files: list[str] = []
    if args.capture:
        captured = capture_download(args.mod, args.capture_timeout, args.iface)
        if not captured:
            return 1
        args.base, args.token, captured_files = captured

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
        listed = list_folder(mod_url, args.timeout)
        if listed:
            print(f"Directory listing found: {len(listed)} file(s)")
            urls = listed
        elif captured_files:
            print(f"No directory listing, using {len(captured_files)} captured file(s)")
            urls = [urljoin(mod_url, quote(name)) for name in captured_files]
        else:
            print("No directory listing, trying default T6 mod files")
            urls = [urljoin(mod_url, name) for name in DEFAULT_FILES]

    base_path = urlparse(mod_url).path
    statuses = []
    for url in urls:
        relative = unquote(urlparse(url).path[len(base_path) :])
        statuses.append(
            download(url, args.out / args.mod / relative, args.timeout, args.retries)
        )

    ok = sum(1 for status in statuses if status == 0)
    print(f"\n{ok}/{len(statuses)} file(s) downloaded into {args.out / args.mod}")
    if 403 in statuses and not args.token.strip("/"):
        print(
            "Got HTTP 403 with no token set — this server gates downloads per session. "
            "Re-run with --capture (or set TOKEN from a capture) to get a valid token."
        )
    return 0 if ok == len(statuses) else 1


if __name__ == "__main__":
    sys.exit(main())
