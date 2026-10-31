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
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL", 600))  # 10 minutes
WORKER_ID = os.environ.get("WORKER_ID", "Render-ZomroEngine-24-7")
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Render.com")

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

# ----------------- LOCAL PROXY BRIDGE -----------------
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

# ----------------- COOKIE SYNC & COORDINATION -----------------
def send_heartbeat(is_valid=True, current_url="https://flow.google.com/"):
    try:
        req = urllib.request.Request(
            SYNC_URL,
            data=json.dumps({
                "secret": SECRET_KEY,
                "action": "heartbeat",
                "worker_id": WORKER_ID,
                "platform": PLATFORM_NAME,
                "session_valid": is_valid,
                "page_url": current_url,
                "version": service_state.get("last_sync_version", 0)
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("can_rotate", True), data.get("role", "master")
    except Exception as e:
        log(f"Heartbeat warning: {e}")
        return True, "master"

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
# PLAYWRIGHT PERSISTENT BROWSER ENGINE
# ============================================================
CLEAN_WHITELIST_NAMES = [
    '_ga', 'NID', 'OSID', '__Secure-OSID', 'SID', '__Secure-1PSID', '__Secure-3PSID',
    'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID',
    '__Secure-1PSIDTS', '__Secure-3PSIDTS', '_ga_X2GNH8R5NS', 'SIDCC', '__Secure-1PSIDCC', '__Secure-3PSIDCC'
]

def build_playwright_cookies(raw_cookies):
    pw_cookies = []
    for c in raw_cookies:
        cname = c.get("name")
        cval = c.get("value")
        if not cname or not cval: continue
        if cname not in CLEAN_WHITELIST_NAMES: continue
        
        same_site = c.get("sameSite", "Lax")
        if same_site == "no_restriction": same_site = "None"
        elif same_site not in ["Strict", "Lax", "None"]: same_site = "Lax"

        is_host = c.get("hostOnly") or cname in ["OSID", "__Secure-OSID"]
        target_domain = "flow.google.com" if is_host else c.get("domain", ".google.com")
        if "accounts.google" in target_domain: continue

        entry = {
            "name": cname,
            "value": cval,
            "domain": target_domain,
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": same_site
        }
        pw_cookies.append(entry)
    return pw_cookies

def navigate_flow_with_retry(page, url=FLOW_URL, max_retries=3):
    for attempt in range(max_retries):
        try:
            log(f"Navigation attempt {attempt+1}/{max_retries} to {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            cur = page.url
            if cur.startswith("http") and cur != "about:blank":
                log(f"Navigation successful. URL: {cur}")
                return cur
        except Exception as e:
            log(f"Navigation attempt {attempt+1} warning: {e}")
            time.sleep(4)
    return page.url

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

            pw_cookies = build_playwright_cookies(raw_cookies)
            log(f"Launching persistent Chromium via local bridge into {FLOW_URL}...")

            storage_state_file = "/app/storage_state.json" if os.path.exists("/app/storage_state.json") else ("storage_state.json" if os.path.exists("storage_state.json") else None)

            with sync_playwright() as p:
                context_kwargs = {
                    "user_data_dir": PROFILE_DIR,
                    "headless": True,
                    "proxy": {"server": f"http://127.0.0.1:{LOCAL_BRIDGE_PORT}"},
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "viewport": {"width": 1400, "height": 900},
                    "args": [
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-features=DeviceBoundSessions",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--disable-default-apps"
                    ]
                }
                
                context = p.chromium.launch_persistent_context(**context_kwargs)

                # Inject storage state if available, or cookies
                if storage_state_file:
                    try:
                        with open(storage_state_file, 'r', encoding='utf-8') as sf:
                            st_data = json.load(sf)
                            origins = st_data.get("origins", [])
                            # Note: persistent context doesn't directly import origins from file, but we can set cookies
                            log(f"Loaded storage_state file with {len(st_data.get('cookies', []))} cookies")
                    except Exception as sfe:
                        log(f"Storage state read warning: {sfe}")

                page = context.pages[0] if context.pages else context.new_page()
                context.add_cookies(pw_cookies)

                current_url = navigate_flow_with_retry(page, FLOW_URL, max_retries=3)
                try:
                    page_title = page.title()
                except Exception:
                    page_title = "Google Flow"

                if "flow.google.com/about" in current_url:
                    log("Landed on /about. Attempting auto-click into studio...")
                    try:
                        create_btn = page.locator("button:has-text('Создать'), a:has-text('Создать'), button:has-text('Create')").first
                        if create_btn and create_btn.is_visible():
                            create_btn.click()
                            page.wait_for_timeout(8000)
                            current_url = page.url
                            try: page_title = page.title()
                            except Exception: page_title = "Google Flow"
                    except Exception as ce:
                        log(f"Auto-click warning: {ce}")

                if "accountchooser" in current_url:
                    log("Landed on accountchooser. Attempting auto-click account item...")
                    try:
                        acc_item = page.locator("[data-identifier], [data-email], [data-profileidentifier], li[role='link'], div[role='link'], ul li div[role='button']").first
                        if acc_item and acc_item.is_visible():
                            acc_item.click()
                            page.wait_for_timeout(8000)
                            current_url = page.url
                            try: page_title = page.title()
                            except Exception: pass
                    except Exception as ace:
                        log(f"Account chooser auto-click warning: {ace}")

                is_explicit_logout = "accounts.google" in current_url or "CookieMismatch" in current_url or "signin" in current_url
                is_valid = not is_explicit_logout and "flow.google.com/about" not in current_url

                if current_url.startswith("http") and current_url != "about:blank":
                    service_state["last_page_url"] = current_url
                    service_state["page_title"] = page_title
                    service_state["session_valid"] = is_valid
                else:
                    service_state["session_valid"] = True
                    log(f"Initial navigation URL is {current_url}. Marking session valid based on verified cookies.")

                service_state["last_check_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                log(f"Flow loaded. URL: {service_state['last_page_url']} | Title: {service_state['page_title']} | Valid: {service_state['session_valid']}")

                can_rot, my_role = send_heartbeat(service_state["session_valid"], service_state.get("last_page_url") or FLOW_URL)
                service_state["role"] = my_role

                # Periodic loop (every 10 minutes)
                while True:
                    time.sleep(CHECK_INTERVAL_SECONDS)

                    # 1. Check if newer cookies appeared on central server
                    new_cookies, new_ver = fetch_cookies_from_server()
                    if new_ver and new_ver > service_state.get("last_sync_version", 0):
                        log(f"Found newer cookies on server (v{new_ver} > v{service_state.get('last_sync_version')}). Injecting...")
                        pw_c = build_playwright_cookies(new_cookies)
                        try:
                            context.add_cookies(pw_c)
                            service_state["last_sync_version"] = new_ver
                        except Exception as ce:
                            log(f"Cookie re-injection warning: {ce}")

                    can_rot, my_role = send_heartbeat(service_state.get("session_valid", True), service_state.get("last_page_url", FLOW_URL))
                    service_state["role"] = my_role
                    if not can_rot:
                        log(f"[CLUSTER] Standby mode active. Master lease owned by another keeper. Standing by...")
                        continue

                    log("[KEEPALIVE] Periodic navigation to Flow to rotate tokens...")
                    cur_url = navigate_flow_with_retry(page, FLOW_URL, max_retries=2)

                    if "flow.google.com/about" in cur_url:
                        try:
                            btn = page.locator("button:has-text('Создать'), a:has-text('Создать'), button:has-text('Create')").first
                            if btn and btn.is_visible():
                                btn.click()
                                page.wait_for_timeout(6000)
                                cur_url = page.url
                        except Exception as be:
                            log(f"Button click error: {be}")

                    if "accountchooser" in cur_url:
                        try:
                            acc_item = page.locator("[data-identifier], [data-email], [data-profileidentifier], li[role='link'], div[role='link'], ul li div[role='button']").first
                            if acc_item and acc_item.is_visible():
                                acc_item.click()
                                page.wait_for_timeout(8000)
                                cur_url = page.url
                        except Exception as ace:
                            log(f"Account chooser click error: {ace}")

                    is_explicit_logout = "accounts.google" in cur_url or "signin" in cur_url or "CookieMismatch" in cur_url
                    if is_explicit_logout:
                        log(f"Explicit logout detected at {cur_url}! Breaking to re-initialize browser context with fresh cookies from server...")
                        service_state["session_valid"] = False
                        service_state["last_page_url"] = cur_url
                        # DO NOT overwrite server cookies with broken ones!
                        break

                    if cur_url.startswith("http") and cur_url != "about:blank":
                        service_state["last_page_url"] = cur_url
                        try: service_state["page_title"] = page.title()
                        except Exception: pass
                        service_state["session_valid"] = True
                    else:
                        log(f"Navigation transient state: {cur_url}. Retaining session_valid=True")

                    service_state["last_check_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

                    live_cookies = context.cookies()
                    live_tokens = {
                        c.get("name"): c.get("value")
                        for c in live_cookies
                        if c.get("name") in ["__Secure-1PSIDTS", "__Secure-1PSIDRTS", "__Secure-3PSIDTS", "__Secure-3PSIDRTS"]
                    }

                    changed_keys = [k for k, v in live_tokens.items() if known_tokens.get(k) != v]
                    # CRITICAL GUARD: Only push if session is completely valid AND has core Google Auth cookies AND not on accounts.google
                    has_sid = any(c.get("name") in ("SID", "SSID") for c in live_cookies)
                    if changed_keys and service_state["session_valid"] and has_sid and "accounts.google" not in cur_url:
                        log(f"TOKENS ROTATED BY GOOGLE ({', '.join(changed_keys)})! Syncing to server...")
                        updated_list = []
                        now_ts = time.time()
                        for lc in live_cookies:
                            cname = lc.get("name")
                            if cname not in CLEAN_WHITELIST_NAMES:
                                continue
                            dom_raw = lc.get("domain", "")
                            if "accounts.google" in dom_raw:
                                continue
                            is_host_only = cname in ("OSID", "__Secure-OSID")
                            target_dom = "flow.google.com" if is_host_only else ".google.com"
                            exp = float(lc.get("expires") or 0)
                            if exp <= 0:
                                exp = now_ts + 31536000
                            updated_list.append({
                                "domain": target_dom,
                                "expirationDate": exp,
                                "hostOnly": is_host_only,
                                "httpOnly": bool(lc.get("httpOnly", True)),
                                "name": cname,
                                "path": lc.get("path", "/"),
                                "sameSite": "no_restriction" if lc.get("sameSite") in ("None", "no_restriction") else "lax",
                                "secure": bool(lc.get("secure", True)),
                                "session": False,
                                "storeId": None,
                                "value": lc.get("value")
                            })
                        if len(updated_list) >= 10:
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
