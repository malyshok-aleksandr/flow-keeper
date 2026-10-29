import os
import sys
import json
import time
import socket
import base64
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration
SYNC_URL = os.environ.get("SYNC_URL", "https://all-creator.bio.co.ua/flow/sync_cookies.php")
SECRET_KEY = os.environ.get("SYNC_SECRET", "FLOW_ULTRA_AUTO_SYNC_2026_SECRET_KEY")
FLOW_URL = os.environ.get("FLOW_URL", "https://flow.google.com/")
PROFILE_DIR = os.environ.get("PROFILE_DIR", "/app/chrome_profile")
PORT = int(os.environ.get("PORT", 8080))
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL", 900))  # 15 minutes (Zomro pattern)

PROXY_HOST = os.environ.get("PROXY_HOST", "154.6.39.142")
PROXY_PORT = int(os.environ.get("PROXY_PORT", 12323))
PROXY_USER = os.environ.get("PROXY_USER", "14a93721ee7fb")
PROXY_PASS = os.environ.get("PROXY_PASS", "8c22cf1655")
LOCAL_BRIDGE_PORT = 8899
AUTH_HEADER = base64.b64encode(f"{PROXY_USER}:{PROXY_PASS}".encode()).decode()

service_state = {
    "service": "Flow Ultra Render CloudKeeper (Zomro Engine 24/7)",
    "mode": "initializing",
    "uptime_start": time.strftime("%Y-%m-%d %H:%M:%S"),
    "last_check_time": None,
    "last_page_url": None,
    "page_title": None,
    "session_valid": False,
    "rotated_count": 0,
    "last_rotated_tokens": [],
    "last_sync_version": None,
    "error": None
}

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# ----------------- LOCAL PROXY BRIDGE (Exact Zomro VPS implementation) -----------------
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
        log(f"[BRIDGE] Error: {e}")

threading.Thread(target=start_local_bridge, daemon=True).start()
time.sleep(1)

# ----------------- COOKIE SYNC -----------------
def fetch_cookies_from_server():
    try:
        req = urllib.request.Request(
            SYNC_URL,
            data=json.dumps({"secret": SECRET_KEY, "action": "get_cookies"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("cookies", []), data.get("version", 0)
    except Exception as e:
        log(f"Error fetching cookies from server: {e}")
        return [], 0

def push_cookies_to_server(cookies_list):
    try:
        req = urllib.request.Request(
            SYNC_URL,
            data=json.dumps({
                "secret": SECRET_KEY,
                "action": "sync",
                "email": "vps_autokeeper@all-creator.bio.co.ua",
                "device_name": "Render-ZomroEngine-24-7",
                "cookies": cookies_list
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
            ver = res.get("version")
            log(f"Push to server response: {res.get('status')} - v{ver}")
            return ver
    except Exception as e:
        log(f"Error pushing updated cookies to server: {e}")
        return None

# ============================================================
# HTTP STATUS / HEALTHCHECK SERVER (Required by Render)
# ============================================================
class HealthRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/health", "/status"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            resp = {
                "status": "online",
                "current_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "details": service_state
            }
            self.wfile.write(json.dumps(resp, indent=2, ensure_ascii=False).encode())
        elif self.path == "/keepalive":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "acknowledged",
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "session_valid": service_state.get("session_valid", False),
                "last_url": service_state.get("last_page_url")
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        return

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthRequestHandler)
    log(f"Health status server listening on port {PORT}")
    server.serve_forever()

# ============================================================
# PLAYWRIGHT PERSISTENT BROWSER ENGINE (Exact Zomro VPS Replica)
# ============================================================
def run_playwright_autonomous():
    global service_state
    from playwright.sync_api import sync_playwright

    log("Starting Playwright 24/7 Persistent Chromium Engine...")
    service_state["mode"] = "playwright_persistent"
    os.makedirs(PROFILE_DIR, exist_ok=True)

    while True:
        try:
            raw_cookies, server_version = fetch_cookies_from_server()
            if not raw_cookies:
                log("No cookies received from hosting. Retrying in 30s...")
                time.sleep(30)
                continue

            service_state["last_sync_version"] = server_version
            known_tokens = {
                c.get("name"): c.get("value")
                for c in raw_cookies
                if c.get("name") in ["__Secure-1PSIDTS", "__Secure-1PSIDRTS", "__Secure-3PSIDTS", "__Secure-3PSIDRTS"]
            }

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

            log(f"Launching persistent Chromium via local bridge into {FLOW_URL}...")

            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=PROFILE_DIR,
                    headless=True,
                    proxy={"server": f"http://127.0.0.1:{LOCAL_BRIDGE_PORT}"},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1400, "height": 900},
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--disable-default-apps"
                    ]
                )

                page = context.pages[0] if context.pages else context.new_page()
                context.add_cookies(pw_cookies)

                log(f"Navigating to Flow: {FLOW_URL}...")
                try:
                    page.goto(FLOW_URL, wait_until="commit", timeout=30000)
                    page.wait_for_timeout(8000)
                except Exception as e:
                    log(f"Initial navigation load warning: {e}")

                current_url = page.url
                page_title = page.title()

                if "about" in current_url:
                    log("Landed on /about. Attempting auto-click into studio...")
                    try:
                        create_btn = page.locator("button:has-text('Создать'), a:has-text('Создать'), button:has-text('Create')").first
                        if create_btn and create_btn.is_visible():
                            create_btn.click()
                            page.wait_for_timeout(8000)
                            current_url = page.url
                            page_title = page.title()
                    except Exception as ce:
                        log(f"Auto-click warning: {ce}")

                is_valid = "about" not in current_url and "accounts.google" not in current_url
                service_state["last_check_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                service_state["last_page_url"] = current_url
                service_state["page_title"] = page_title
                service_state["session_valid"] = is_valid

                log(f"Flow loaded. URL: {current_url} | Title: {page_title} | Valid: {is_valid}")

                # Initial sync (только если URL валиден и авторизован)
                live_c = context.cookies()
                if any(c.get("name") in ("SID", "SSID") for c in live_c) and is_valid:
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
                    push_cookies_to_server(formatted)

                # Periodic loop (every 15 minutes)
                while True:
                    time.sleep(CHECK_INTERVAL_SECONDS)
                    try:
                        log("[KEEPALIVE] Periodic navigation to Flow to rotate tokens...")
                        page.goto(FLOW_URL, wait_until="commit", timeout=35000)
                        page.wait_for_timeout(8000)
                        if "about" in page.url:
                            btn = page.locator("button:has-text('Создать'), a:has-text('Создать'), button:has-text('Create')").first
                            if btn.is_visible():
                                btn.click()
                                page.wait_for_timeout(8000)
                    except Exception as e:
                        log(f"Navigation error: {e}")

                    live_cookies = context.cookies()
                    live_tokens = {
                        c.get("name"): c.get("value")
                        for c in live_cookies
                        if c.get("name") in ["__Secure-1PSIDTS", "__Secure-1PSIDRTS", "__Secure-3PSIDTS", "__Secure-3PSIDRTS"]
                    }
                    current_url = page.url
                    page_title = page.title()
                    is_valid = "about" not in current_url and "accounts.google" not in current_url

                    service_state["last_check_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    service_state["last_page_url"] = current_url
                    service_state["page_title"] = page_title
                    service_state["session_valid"] = is_valid

                    changed_keys = [k for k, v in live_tokens.items() if known_tokens.get(k) != v]
                    if changed_keys and is_valid:
                        log(f"TOKENS ROTATED BY GOOGLE ({', '.join(changed_keys)})! Syncing to server...")
                        updated_list = []
                        for lc in live_cookies:
                            is_host_only = lc.get("name") in ("OSID", "__Secure-OSID")
                            dom = "flow.google.com" if is_host_only else lc.get("domain", ".google.com")
                            updated_list.append({
                                "domain": dom,
                                "expirationDate": lc.get("expires", time.time() + 31536000),
                                "hostOnly": is_host_only,
                                "httpOnly": lc.get("httpOnly", True),
                                "name": lc.get("name"),
                                "path": lc.get("path", "/"),
                                "sameSite": "no_restriction" if lc.get("sameSite") == "None" else "lax",
                                "secure": lc.get("secure", True),
                                "session": False,
                                "storeId": None,
                                "value": lc.get("value")
                            })
                        new_ver = push_cookies_to_server(updated_list)
                        if new_ver:
                            service_state["rotated_count"] += 1
                            service_state["last_sync_version"] = new_ver
                            service_state["last_rotated_tokens"] = changed_keys
                            known_tokens = live_tokens

        except Exception as e:
            log(f"Autonomous engine error: {e}")
            service_state["error"] = str(e)
            time.sleep(20)

if __name__ == "__main__":
    t_http = threading.Thread(target=run_http_server, daemon=True)
    t_http.start()
    run_playwright_autonomous()
