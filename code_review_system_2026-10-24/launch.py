"""Launch the website locally or on the current Windows Wi-Fi network."""

import argparse
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn


LOCAL_HOST = "127.0.0.1"
PORTS = range(8000, 8011)
SERVICE = "code-review-system"


def is_website(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{LOCAL_HOST}:{port}/api/health", timeout=1
        ) as response:
            payload = json.loads(response.read(4096))
            return response.status == 200 and payload.get("service") == SERVICE
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def is_available(host: str, port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def open_when_ready(port: int) -> None:
    for _ in range(50):
        if is_website(port):
            webbrowser.open(f"http://{LOCAL_HOST}:{port}/")
            return
        time.sleep(0.2)


def wlan_address() -> str | None:
    """Return the current Wi-Fi IPv4 address, excluding VPN interfaces."""
    if os.name != "nt":
        return None
    command = (
        "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
        "Where-Object { $_.InterfaceAlias -in @('WLAN', 'Wi-Fi') -and "
        "$_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '169.254.*' } | "
        "Select-Object -First 1 -ExpandProperty IPAddress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        address = result.stdout.strip()
        if result.returncode == 0 and address:
            return str(ipaddress.IPv4Address(address))
    except (OSError, subprocess.TimeoutExpired, ipaddress.AddressValueError):
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the Code Review System website")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    parser.add_argument("--mobile", action="store_true", help="Allow same-Wi-Fi access with a password")
    args = parser.parse_args()

    host = wlan_address() if args.mobile else LOCAL_HOST
    if host is None:
        print("未找到 WLAN 的 IPv4 地址。请先让电脑连接 Wi-Fi，再重新启动。", flush=True)
        return 1

    if not args.mobile:
        for port in PORTS:
            if is_website(port):
                url = f"http://{host}:{port}/"
                print(f"The Code Review System is already running: {url}", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return 0

    port = next((candidate for candidate in PORTS if is_available(host, candidate)), None)
    if port is None:
        print("Ports 8000-8010 are occupied on this address. Close an unused server and retry.", flush=True)
        return 1

    url = f"http://{host}:{port}/"
    if args.mobile:
        password = secrets.token_hex(8)
        os.environ["CODE_REVIEW_LAN_PASSWORD"] = password
        print("手机和电脑连接同一 Wi-Fi 后，在手机浏览器打开：", flush=True)
        print(f"  {url}", flush=True)
        print("登录用户名：review", flush=True)
        print(f"登录密码：{password}", flush=True)
    else:
        os.environ.pop("CODE_REVIEW_LAN_PASSWORD", None)
        print(f"Website: {url}", flush=True)
        print(f"API docs: {url}docs", flush=True)
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()

    print("关闭此窗口或按 Ctrl+C 即可停止服务。", flush=True)
    uvicorn.run("app.main:app", host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
