import os
import sys
import json
import time
import socket
import base64
import threading
import urllib.request
from playwright.sync_api import sync_playwright

FLOW_URL = "https://flow.google.com/"
SYNC_URL = os.environ.get("SYNC_URL", "https://all-creator.bio.co.ua/flow/sync_cookies.php")
SYNC_SECRET = os.environ.get("SYNC_SECRET", "FLOW_ULTRA_AUTO_SYNC_2026_SECRET_KEY")

PROXY_HOST = os.environ.get("PROXY_HOST", "154.6.39.142")
PROXY_PORT = int(os.environ.get("PROXY_PORT", 12323))
PROXY_USER = os.environ.get("PROXY_USER", "14a93721ee7fb")
PROXY_PASS = os.environ.get("PROXY_PASS", "8c22cf1655")
LOCAL_BRIDGE_PORT = 8895
AUTH_HEADER = base64.b64encode(f"{PROXY_USER}:{PROXY_PASS}".encode()).decode()

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# ----------------- PROXY BRIDGE -----------------
def handle_client(client_socket):
    try:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = client_socket.recv(4096)
            if not chunk: break
            data += chunk
        if not data:
            client_socket.close()
            return
        header_part, rest = data.split(b"\r\n\r\n", 1)
        lines = header_part.split(b"\r\n")
        req_line = lines[0]
        new_lines = [req_line, f"Proxy-Authorization: Basic {AUTH_HEADER}".encode()]
        for line in lines[1:]:
            if not line.lower().startswith(b"proxy-authorization"):
                new_lines.append(line)
        new_request = b"\r\n".join(new_lines) + b"\r\n\r\n" + rest
        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream.connect((PROXY_HOST, PROXY_PORT))
        upstream.sendall(new_request)
        def pipe(src, dst):
            try:
                while True:
                    buf = src.recv(32768)
                    if not buf: break
                    dst.sendall(buf)
            except: pass
            finally:
                try: src.close()
                except: pass
                try: dst.close()
                except: pass
        threading.Thread(target=pipe, args=(client_socket, upstream), daemon=True).start()
        threading.Thread(target=pipe, args=(upstream, client_socket), daemon=True).start()
    except:
        try: client_socket.close()
        except: pass

def start_local_bridge(port=LOCAL_BRIDGE_PORT):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", port))
        server.listen(128)
        log(f"[BRIDGE] Local proxy bridge running on 127.0.0.1:{port} -> {PROXY_HOST}:{PROXY_PORT}")
        while True:
            conn, _ = server.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
    except Exception as e:
        log(f"[BRIDGE] Notice: {e}")

threading.Thread(target=start_local_bridge, daemon=True).start()
time.sleep(1)

# ----------------- COOKIE PULL / PUSH -----------------
def fetch_cookies():
    try:
        req = urllib.request.Request(
            SYNC_URL,
            data=json.dumps({"secret": SYNC_SECRET, "action": "get_cookies"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("cookies", []), data.get("version", 0)
    except Exception as e:
        log(f"Error fetching cookies: {e}")
        return [], 0

def push_cookies(cookies_list):
    try:
        req = urllib.request.Request(
            SYNC_URL,
            data=json.dumps({
                "secret": SYNC_SECRET,
                "action": "sync",
                "email": "vps_autokeeper@all-creator.bio.co.ua",
                "device_name": "GitHub-Actions-CloudCron",
                "cookies": cookies_list
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
            log(f"[AUTO-SYNC] Successfully pushed to server! Version: v{res.get('version')}")
            return res.get("version")
    except Exception as e:
        log(f"[AUTO-SYNC] Error pushing cookies: {e}")
        return None

def main():
    log("=== STARTING GITHUB ACTIONS FLOW KEEPER JOB ===")
    raw_cookies, version = fetch_cookies()
    if not raw_cookies:
        log("No cookies received from server. Aborting.")
        sys.exit(1)

    log(f"Fetched {len(raw_cookies)} cookies (version v{version}) from hosting.")

    pw_cookies = []
    for c in raw_cookies:
        cname = c.get("name")
        cval = c.get("value")
        if not cname or not cval: continue
        same_site = c.get("sameSite", "Lax")
        if same_site == "no_restriction": same_site = "None"
        elif same_site not in ["Strict", "Lax", "None"]: same_site = "Lax"

        pw_cookies.append({
            "name": cname,
            "value": cval,
            "domain": c.get("domain", ".google.com"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": same_site
        })

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={"server": f"http://127.0.0.1:{LOCAL_BRIDGE_PORT}"},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900}
        )
        ctx.add_cookies(pw_cookies)
        page = ctx.new_page()

        log(f"Navigating to Flow: {FLOW_URL}...")
        try:
            page.goto(FLOW_URL, wait_until="commit", timeout=35000)
            page.wait_for_timeout(8000)
        except Exception as e:
            log(f"Navigation notice: {e}")

        cur_url = page.url
        cur_title = page.title()
        log(f"Landed on: URL={cur_url} | Title={cur_title}")

        if "about" in cur_url:
            log("Landed on /about. Attempting entry click...")
            try:
                btn = page.locator("button:has-text('Создать'), a:has-text('Создать'), button:has-text('Create')").first
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(8000)
                    log(f"After click: URL={page.url} | Title={page.title()}")
            except Exception as ce:
                log(f"Click notice: {ce}")

        # Extract live rotated cookies
        live_c = ctx.cookies()
        if any(c.get("name") in ("SID", "SSID") for c in live_c):
            formatted = []
            for c in live_c:
                is_host_only = c.get("name") in ("OSID", "__Secure-OSID")
                dom = "flow.google.com" if is_host_only else c.get("domain", ".google.com")
                formatted.append({
                    "domain": dom,
                    "expirationDate": c.get("expires", time.time() + 31536000),
                    "hostOnly": is_host_only,
                    "httpOnly": c.get("httpOnly", True),
                    "name": c.get("name"),
                    "path": c.get("path", "/"),
                    "sameSite": "no_restriction" if c.get("sameSite") == "None" else "lax",
                    "secure": c.get("secure", True),
                    "session": False,
                    "storeId": None,
                    "value": c.get("value")
                })
            new_v = push_cookies(formatted)
            log(f"Keepalive job finished successfully! New version: v{new_v}")
        else:
            log("No auth tokens found in cookies!")

        browser.close()

if __name__ == "__main__":
    main()
