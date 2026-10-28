import os
import sys
import json
import time
import threading
import urllib.request
import urllib.error
import gc
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration
PROXY_URL = os.environ.get("PROXY_URL", "http://14a93721ee7fb:8c22cf1655@154.6.39.142:12323")
SYNC_URL = os.environ.get("SYNC_URL", "https://all-creator.bio.co.ua/flow/sync_cookies.php")
SECRET_KEY = os.environ.get("SYNC_SECRET", "FLOW_ULTRA_AUTO_SYNC_2026_SECRET_KEY")
FLOW_URL = os.environ.get("FLOW_URL", "https://flow.google.com/project/ae3718da-d85b-4133-bef9-bd999fa677fc")
PROFILE_DIR = os.environ.get("PROFILE_DIR", "/app/chrome_profile")
PORT = int(os.environ.get("PORT", 8080))
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL", 600))  # 10 minutes

# Parse proxy components for Playwright
proxy_parts = PROXY_URL.replace("http://", "").replace("https://", "").split("@")
if len(proxy_parts) == 2:
    creds, host_port = proxy_parts
    p_user, p_pass = creds.split(":")
    p_server = f"http://{host_port}"
else:
    p_server = PROXY_URL
    p_user, p_pass = None, None

service_state = {
    "service": "Flow Ultra Render CloudKeeper (Playwright Persistent)",
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
                "device_name": "Render-Playwright-24-7",
                "cookies": cookies_list
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
            log(f"Push to server response: {res.get('status')} - v{res.get('version')}")
            return res.get("version")
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
        # Silence default request access logs
        return

# ============================================================
# PLAYWRIGHT PERSISTENT BROWSER ENGINE (Exact Zomro VPS Replica)
# ============================================================
def run_playwright_autonomous():
    global service_state
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright not installed in this environment. Falling back to HTTP Keepalive mode...")
        run_http_fallback()
        return

    log("Starting Playwright 24/7 Persistent Browser Engine...")
    service_state["mode"] = "playwright_persistent"

    os.makedirs(PROFILE_DIR, exist_ok=True)

    while True:
        try:
            # 1. Fetch authoritative cookies from hosting
            raw_cookies, server_version = fetch_cookies_from_server()
            if not raw_cookies:
                log("No cookies received from hosting. Retrying in 60s...")
                time.sleep(60)
                continue

            service_state["last_sync_version"] = server_version
            known_tokens = {
                c.get("name"): c.get("value")
                for c in raw_cookies
                if c.get("name") in ["__Secure-1PSIDTS", "__Secure-1PSIDRTS", "__Secure-3PSIDTS", "__Secure-3PSIDRTS"]
            }

            # Convert to Playwright format
            pw_cookies = []
            for c in raw_cookies:
                cname = c.get("name")
                cval = c.get("value")
                if not cname or not cval:
                    continue
                same_site = c.get("sameSite", "Lax")
                if same_site == "no_restriction":
                    same_site = "None"
                elif same_site not in ["Strict", "Lax", "None"]:
                    same_site = "Lax"

                pw_cookies.append({
                    "name": cname,
                    "value": cval,
                    "domain": c.get("domain", ".google.com"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", True),
                    "httpOnly": c.get("httpOnly", False),
                    "sameSite": same_site
                })

            log(f"Launching persistent Chromium via US proxy ({p_server}) into {FLOW_URL}...")

            with sync_playwright() as p:
                proxy_config = {"server": p_server}
                if p_user and p_pass:
                    proxy_config["username"] = p_user
                    proxy_config["password"] = p_pass

                context = p.chromium.launch_persistent_context(
                    user_data_dir=PROFILE_DIR,
                    headless=True,
                    proxy=proxy_config,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1400, "height": 900},
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-background-networking",
                        "--disable-default-apps",
                        "--disable-extensions",
                        "--mute-audio",
                        "--no-first-run"
                    ]
                )

                # Route abort heavy static media (png, jpg, mp4) to conserve memory & bandwidth
                def block_media(route):
                    req = route.request
                    if req.resource_type in ["image", "media", "font"]:
                        route.abort()
                    else:
                        route.continue_()

                page = context.pages[0] if context.pages else context.new_page()
                page.route("**/*", block_media)

                # Inject cookies into persistent profile
                context.add_cookies(pw_cookies)

                log(f"Navigating to Flow Project URL: {FLOW_URL}...")
                try:
                    page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    log(f"Initial navigation load warning: {e}")

                time.sleep(10)

                current_url = page.url
                page_title = page.title()

                # If landed on /about, try to click entry button
                if "about" in current_url:
                    log("Landed on /about. Attempting auto-click into studio...")
                    try:
                        create_btn = page.locator("button:has-text('Создать'), a:has-text('Создать'), button:has-text('Create'), a:has-text('Create')").first
                        if create_btn and create_btn.is_visible():
                            create_btn.click()
                            time.sleep(8)
                            current_url = page.url
                            page_title = page.title()
                            log(f"After click: URL={current_url} | Title={page_title}")
                    except Exception as ce:
                        log(f"Auto-click warning: {ce}")

                is_valid = "about" not in current_url and "accounts.google" not in current_url

                service_state["last_check_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                service_state["last_page_url"] = current_url
                service_state["page_title"] = page_title
                service_state["session_valid"] = is_valid

                log(f"Project loaded. URL: {current_url} | Title: {page_title} | Valid: {is_valid}")

                # Active maintenance loop
                cycle_count = 0
                while True:
                    time.sleep(CHECK_INTERVAL_SECONDS)
                    cycle_count += 1

                    try:
                        # 1. Gentle JavaScript pulse to trigger Angular background worker
                        page.evaluate("() => document.title")
                    except Exception as e:
                        log(f"Pulse error: {e}")

                    # 2. Check cookies in active browser context
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

                    # 3. Detect if Google rotated any rolling session tokens
                    changed_keys = [k for k, v in live_tokens.items() if known_tokens.get(k) != v]

                    if changed_keys and is_valid:
                        log(f"TOKENS ROTATED BY GOOGLE ({', '.join(changed_keys)})! Syncing to server...")
                        
                        # Format all cookies for hosting
                        updated_list = []
                        for lc in live_cookies:
                            updated_list.append({
                                "domain": lc.get("domain", ".google.com"),
                                "expirationDate": lc.get("expires", time.time() + 31536000),
                                "hostOnly": False,
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
                            known_tokens.update(live_tokens)
                            service_state["rotated_count"] += 1
                            service_state["last_rotated_tokens"] = changed_keys
                            service_state["last_sync_version"] = new_ver
                            log(f"Server updated to v{new_ver} successfully.")
                    else:
                        log(f"Keepalive check OK (Cycle #{cycle_count}) - Active on {current_url}")

                    # 4. Hourly gentle interaction to trigger Google's token renewal
                    if cycle_count % 6 == 0:
                        log("Hourly scheduled keepalive interaction in project...")
                        try:
                            page.evaluate("() => window.scrollTo(0, 100)")
                            time.sleep(1)
                            page.evaluate("() => window.scrollTo(0, 0)")
                        except Exception as re_err:
                            log(f"Interaction warning: {re_err}")
                        gc.collect()

                    # 5. Prevent memory buildup: refresh context every 24 hours
                    if cycle_count >= 144:
                        log("24-hour cycle reached. Restarting browser context cleanly...")
                        break

                context.close()
                log("Browser context closed. Starting fresh cycle...")

        except Exception as loop_err:
            log(f"Playwright cycle encountered error: {loop_err}")
            service_state["error"] = str(loop_err)
            time.sleep(30)

# ============================================================
# HTTP FALLBACK ENGINE
# ============================================================
def run_http_fallback():
    global service_state
    log("Running in HTTP Keepalive Fallback Mode...")
    service_state["mode"] = "http_fallback"

    proxy_handler = urllib.request.ProxyHandler({"http": PROXY_URL, "https": PROXY_URL})
    opener = urllib.request.build_opener(proxy_handler)

    while True:
        try:
            cookies, ver = fetch_cookies_from_server()
            if cookies:
                cookie_hdr = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "name" in c and "value" in c])
                req = urllib.request.Request(
                    FLOW_URL,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Cookie": cookie_hdr
                    }
                )
                with opener.open(req, timeout=20) as r:
                    service_state["last_check_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    service_state["last_page_url"] = r.geturl()
                    service_state["session_valid"] = "about" not in r.geturl() and "accounts" not in r.geturl()
                    log(f"HTTP Keepalive Ping: {r.status} -> {r.geturl()}")
        except Exception as e:
            log(f"HTTP Fallback error: {e}")
            service_state["error"] = str(e)

        time.sleep(CHECK_INTERVAL_SECONDS)

# ============================================================
# MAIN ENTRYPOINT
# ============================================================
if __name__ == "__main__":
    log(f"Starting Flow Ultra CloudKeeper Web Server on port {PORT}...")

    # Start autonomous worker thread
    t = threading.Thread(target=run_playwright_autonomous, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", PORT), HealthRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopping server...")
        server.server_close()
