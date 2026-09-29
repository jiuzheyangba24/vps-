#!/usr/bin/env python3
import base64
import html
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("WG_MONITOR_HOST", "0.0.0.0")
PORT = int(os.environ.get("WG_MONITOR_PORT", "8787"))
USERNAME = os.environ.get("WG_MONITOR_USER", "admin")
PASSWORD = os.environ.get("WG_MONITOR_PASSWORD", "change-me")
WG_INTERFACE = os.environ.get("WG_MONITOR_INTERFACE", "wg0")
XRAY_CONFIG = os.environ.get("XRAY_CONFIG", "/etc/xray/config.json")
XRAY_API = os.environ.get("XRAY_API", "127.0.0.1:10085")

previous = {}
last_sample_at = None
xray_previous = {}
sample_lock = threading.Lock()


def client_name(allowed_ips):
    ip = allowed_ips.split(",", 1)[0].split("/", 1)[0]
    last = ip.rsplit(".", 1)[-1] if "." in ip else "?"
    return "我的设备" if ip == "10.66.66.2" else f"朋友 {last}"


def read_peers():
    result = subprocess.run(
        ["wg", "show", WG_INTERFACE, "dump"],
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    )
    lines = [line.split("\t") for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 1:
        return []

    now = time.monotonic()
    global last_sample_at
    elapsed = now - last_sample_at if last_sample_at else 0
    last_sample_at = now
    peers = []
    for fields in lines[1:]:
        if len(fields) < 8:
            continue
        public_key, _psk, endpoint, allowed_ips, handshake, rx, tx, keepalive = fields[0:8]
        rx_bytes, tx_bytes = int(rx), int(tx)
        old = previous.get(public_key)
        rx_rate = tx_rate = 0
        if old and elapsed > 0 and rx_bytes >= old[0] and tx_bytes >= old[1]:
            rx_rate = (rx_bytes - old[0]) / elapsed
            tx_rate = (tx_bytes - old[1]) / elapsed
        previous[public_key] = (rx_bytes, tx_bytes)
        peers.append({
            "name": client_name(allowed_ips),
            "allowed_ips": allowed_ips,
            "endpoint": endpoint or "-",
            "latest_handshake": int(handshake),
            "received": rx_bytes,
            "sent": tx_bytes,
            "receive_rate": round(rx_rate, 1),
            "send_rate": round(tx_rate, 1),
        })
    return peers


def read_xray_users():
    with open(XRAY_CONFIG, encoding="utf-8") as config_file:
        config = json.load(config_file)
    names = sorted({
        client["email"]
        for inbound in config.get("inbounds", [])
        if inbound.get("protocol") == "vless"
        for client in inbound.get("settings", {}).get("clients", [])
        if client.get("email")
    })
    result = subprocess.run(
        ["xray", "api", "statsquery", "-s", XRAY_API, "-pattern", "user>>>", "-timeout", "3"],
        check=True, capture_output=True, text=True, timeout=5,
    )
    stats = {}
    for item in json.loads(result.stdout).get("stat", []):
        parts = item["name"].split(">>>")
        if len(parts) == 4 and parts[0] == "user" and parts[2] == "traffic":
            stats[(parts[1], parts[3])] = int(item["value"])

    now = time.monotonic()
    users = []
    with sample_lock:
        for name in names:
            upload = stats.get((name, "uplink"), 0)
            download = stats.get((name, "downlink"), 0)
            old = xray_previous.get(name)
            upload_rate = download_rate = 0
            if old:
                elapsed = now - old[2]
                if elapsed > 0 and upload >= old[0] and download >= old[1]:
                    upload_rate = (upload - old[0]) / elapsed
                    download_rate = (download - old[1]) / elapsed
            xray_previous[name] = (upload, download, now)
            users.append({
                "name": name, "uploaded": upload, "downloaded": download,
                "upload_rate": round(upload_rate, 1),
                "download_rate": round(download_rate, 1),
            })
    return users


INDEX = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>服务器流量监控</title>
<style>
:root{font-family:Inter,"Microsoft YaHei",sans-serif;color:#17212b;background:#f4f7f8}*{box-sizing:border-box}
body{margin:0}.top{background:#173f43;color:#fff;padding:26px 6vw 30px}.top h1{margin:0 0 7px;font-size:26px}.top p{margin:0;color:#c7e4df}.wrap{max-width:1180px;margin:0 auto;padding:24px 6vw 48px}.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;color:#5c6b70}.status{display:flex;align-items:center;gap:8px}.dot{width:9px;height:9px;border-radius:50%;background:#1eb980}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}.card{background:#fff;border:1px solid #dce6e7;border-radius:8px;padding:19px;box-shadow:0 4px 14px #173f4312}.card h2{font-size:17px;margin:0 0 8px}.ip{font:12px ui-monospace,monospace;color:#718084;margin-bottom:16px}.row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid #edf1f1}.label{color:#657579;font-size:13px}.value{font-weight:650;color:#17212b;text-align:right}.rate{color:#14856e}.muted{color:#8a989a;font-size:12px;margin-top:14px}.error{background:#fff1ee;color:#9b3426;padding:14px;border-radius:6px;display:none;margin-bottom:16px}.section-title{font-size:18px;margin:26px 0 12px}.section-note{color:#657579;font-size:13px;margin:0 0 14px}
@media(max-width:560px){.top{padding:22px 20px}.wrap{padding:20px}.bar{align-items:flex-start;gap:10px;flex-direction:column}}
</style></head><body><header class="top"><h1>服务器流量监控</h1><p>每 5 秒刷新 · 分别统计两种连接方式</p></header>
<main class="wrap"><div class="bar"><div class="status"><span class="dot"></span><span id="updated">正在读取...</span></div></div><div id="error" class="error"></div><h2 class="section-title">VLESS REALITY</h2><p class="section-note">从开启统计后开始累计；Xray 重启后计数清零。仅统计流量，不显示在线状态。</p><section id="xray-cards" class="cards"></section><h2 class="section-title">WireGuard</h2><p class="section-note">旧连接的数据单独统计，WireGuard 重启后计数清零。</p><section id="cards" class="cards"></section></main>
<script>
const $=s=>document.querySelector(s);const fmt=n=>{if(n<1024)return n.toFixed(0)+' B';let u=['KB','MB','GB','TB'],i=-1;do{n/=1024;i++}while(n>=1024&&i<u.length-1);return n.toFixed(n>=100?0:1)+' '+u[i]};
const rate=n=>fmt(n)+'/s';const ago=t=>{if(!t)return '从未握手';let s=Math.max(0,Math.floor(Date.now()/1000-t));return s<60?s+' 秒前':s<3600?Math.floor(s/60)+' 分钟前':Math.floor(s/3600)+' 小时前'};
const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){try{let r=await fetch('/api/stats',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);let d=await r.json();$('#error').style.display=d.warnings?.length?'block':'none';$('#error').textContent=(d.warnings||[]).join('；');$('#updated').textContent='刚刚更新';$('#xray-cards').innerHTML=d.xray_users.map(p=>`<article class="card"><h2>${escapeHtml(p.name)}</h2><div class="ip">VLESS REALITY</div><div class="row"><span class="label">实时下载</span><span class="value rate">${rate(p.download_rate)}</span></div><div class="row"><span class="label">实时上传</span><span class="value rate">${rate(p.upload_rate)}</span></div><div class="row"><span class="label">累计下载</span><span class="value">${fmt(p.downloaded)}</span></div><div class="row"><span class="label">累计上传</span><span class="value">${fmt(p.uploaded)}</span></div></article>`).join('')||'<div class="card">暂无 VLESS 用户数据</div>';$('#cards').innerHTML=d.peers.map(p=>`<article class="card"><h2>${escapeHtml(p.name)}</h2><div class="ip">${escapeHtml(p.allowed_ips)}</div><div class="row"><span class="label">实时下载</span><span class="value rate">${rate(p.send_rate)}</span></div><div class="row"><span class="label">实时上传</span><span class="value rate">${rate(p.receive_rate)}</span></div><div class="row"><span class="label">累计下载</span><span class="value">${fmt(p.sent)}</span></div><div class="row"><span class="label">累计上传</span><span class="value">${fmt(p.received)}</span></div><div class="muted">最近握手：${ago(p.latest_handshake)}</div></article>`).join('')||'<div class="card">暂无 Peer</div>'}catch(e){$('#error').textContent='读取失败：'+e.message;$('#error').style.display='block';$('#updated').textContent='连接异常'}}load();setInterval(load,5000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def authenticate(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header[6:]).decode("utf-8")
            user, password = raw.split(":", 1)
            return user == USERNAME and password == PASSWORD
        except (ValueError, UnicodeDecodeError, base64.binascii.Error):
            return False

    def unauthorized(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="WireGuard Monitor"')
        self.end_headers()

    def do_GET(self):
        if not self.authenticate():
            self.unauthorized()
            return
        try:
            if self.path == "/":
                body = INDEX.encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif self.path == "/api/stats":
                payload = {"peers": [], "xray_users": [], "warnings": []}
                for field, reader, label in (("peers", read_peers, "WireGuard"), ("xray_users", read_xray_users, "Xray")):
                    try:
                        payload[field] = reader()
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        payload["warnings"].append(f"{label} 数据暂不可用：{exc}")
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_error(500, html.escape(str(exc)))

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} - {fmt % args}")


if __name__ == "__main__":
    if PASSWORD == "change-me":
        raise SystemExit("Set WG_MONITOR_PASSWORD before starting")
    print(f"Traffic monitor listening on {HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
