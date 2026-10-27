import os
import sys
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration
PROXY_URL = os.environ.get("PROXY_URL", "http://14a93721ee7fb:8c22cf1655@154.6.39.142:12323")
SYNC_URL = os.environ.get("SYNC_URL", "https://all-creator.bio.co.ua/flow/sync_cookies.php")
SECRET_KEY = os.environ.get("SYNC_SECRET", "FLOW_ULTRA_AUTO_SYNC_2026_SECRET_KEY")
CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL", 600))  # 10 minutes

last_status = {
    "status": "initializing",
    "last_check_time": None,
    "last_http_code": None,
    "rotated_count": 0,
    "version": 0
}

def perform_keepalive():
    global last_status
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting keepalive check via proxy {PROXY_URL.split('@')[-1]}...")
    
    # 1. Fetch current cookies from hosting
    try:
        req_fetch = urllib.request.Request(
            SYNC_URL,
            data=json.dumps({"secret": SECRET_KEY, "action": "get_cookies"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_fetch, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            cookies = data.get("cookies", [])
            print(f"Loaded {len(cookies)} cookies from server.")
    except Exception as e:
        print(f"Error fetching cookies from server: {e}")
        last_status["status"] = "error_fetching_cookies"
        last_status["error"] = str(e)
        return last_status

    if not cookies:
        print("No cookies found on server!")
        last_status["status"] = "no_cookies"
        return last_status

    # Build cookie map and header
    cookies_map = {c["name"]: c for c in cookies if "name" in c and "value" in c}
    cookie_hdr = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "name" in c and "value" in c])

    # 2. Ping Google Flow via residential proxy
    proxy_handler = urllib.request.ProxyHandler({"http": PROXY_URL, "https": PROXY_URL})
    opener = urllib.request.build_opener(proxy_handler)

    req_google = urllib.request.Request(
        "https://flow.google.com/",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Cookie": cookie_hdr,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }
    )

    try:
        with opener.open(req_google, timeout=20) as r:
            http_code = r.status
            final_url = r.geturl()
            set_cookies = r.headers.get_all("Set-Cookie", [])
            print(f"Google response: HTTP {http_code}, Set-Cookie headers: {len(set_cookies)}")
    except urllib.error.HTTPError as he:
        http_code = he.code
        final_url = he.url
        set_cookies = he.headers.get_all("Set-Cookie", [])
        print(f"Google HTTPError: {he.code}")
    except Exception as e:
        print(f"Error connecting to Google via proxy: {e}")
        last_status["status"] = "proxy_connect_error"
        last_status["error"] = str(e)
        return last_status

    # 3. Parse rotated Set-Cookie
    rotated_names = []
    for sc in set_cookies:
        pair = sc.split(";")[0].strip()
        if "=" in pair:
            cname, cval = pair.split("=", 1)
            cname = cname.strip()
            cval = cval.strip()
            if cname in cookies_map:
                if cookies_map[cname]["value"] != cval:
                    cookies_map[cname]["value"] = cval
                    rotated_names.append(cname)
            else:
                cookies_map[cname] = {
                    "domain": ".google.com",
                    "expirationDate": time.time() + 31536000,
                    "hostOnly": False,
                    "httpOnly": True,
                    "name": cname,
                    "path": "/",
                    "sameSite": "no_restriction",
                    "secure": True,
                    "session": False,
                    "storeId": None,
                    "value": cval
                }
                rotated_names.append(cname)

    # 4. If cookies were rotated, push back to server
    if rotated_names:
        print(f"Tokens rotated ({len(rotated_names)}: {', '.join(rotated_names)}). Pushing to server...")
        try:
            req_push = urllib.request.Request(
                SYNC_URL,
                data=json.dumps({
                    "secret": SECRET_KEY,
                    "action": "sync",
                    "email": "vps_autokeeper@all-creator.bio.co.ua",
                    "device_name": "Render-CloudKeeper",
                    "cookies": list(cookies_map.values())
                }).encode(),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req_push, timeout=15) as push_resp:
                push_res = json.loads(push_resp.read().decode())
                print(f"Push response: {push_res}")
        except Exception as e:
            print(f"Error pushing updated cookies to server: {e}")
    else:
        print("No tokens rotated in this cycle. Session remains active.")

    last_status = {
        "status": "success",
        "last_check_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_http_code": http_code,
        "final_url": final_url,
        "rotated_count": len(rotated_names),
        "rotated_tokens": rotated_names
    }
    return last_status

def background_loop():
    time.sleep(5)  # initial delay
    while True:
        try:
            perform_keepalive()
        except Exception as e:
            print(f"Unhandled loop error: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/health"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            resp = {
                "service": "Flow Ultra Render CloudKeeper",
                "uptime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": last_status
            }
            self.wfile.write(json.dumps(resp, indent=2, ensure_ascii=False).encode())
        elif self.path == "/keepalive":
            result = perform_keepalive()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2, ensure_ascii=False).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        # Silence default request logs
        return

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Flow CloudKeeper Web Server on port {port}...")
    
    # Start background worker thread
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", port), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
        server.server_close()
