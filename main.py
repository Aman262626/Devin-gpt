# -*- coding: utf-8 -*-
import os
import json
import time
import uuid
import threading
import random
import logging
import base64
import webview
from datetime import datetime
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =================================================================
# 1. Core Configuration
# =================================================================
CONFIG = {
    "PROJECT_NAME": "Ximagine Pro - Video Generation Engine",
    "VERSION": "2.2.0 (Chimera Synthesis)",
    "PORT": 9527,
    "API_KEY": "1",
    "API_BASE": "https://api.ximagine.io/aimodels/api/v1",
    "ORIGIN_URL": "https://ximagine.io",
    "UPLOAD_URL": "https://upload.aiquickdraw.com/upload",
    "IMGBB_API_KEY": "",
    "DATA_FILE": "ximagine_data.json",
    # Auth token used ONLY for upload attempts, NOT for generation
    "AUTH_TOKEN": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpblR5cGUiOiJsb2dpbiIsImxvZ2luSWQiOiJ4aW1hZ2luZS5pby11c2VyLTc2MjkzNCIsInJuU3RyIjoiUE9GbHBJRm1vOTlyalBLd2RRT1pac3hSRkg0NDJJSmcifQ.V8QaTImPoiZe_PyL0bkkHMMNwEltTTPeAhK93QLLKI4",
    # All models use pageId 901 (confirmed from live API capture)
    "MODEL_MAP": {
        "grok-video-normal": {"type": "video", "mode": "normal", "channel": "GROK_IMAGINE", "pageId": 901, "name": "Standard Realistic"},
        "grok-video-fun":    {"type": "video", "mode": "fun",    "channel": "GROK_IMAGINE", "pageId": 901, "name": "Fun Cartoon"},
        "grok-video-spicy":  {"type": "video", "mode": "spicy",  "channel": "GROK_IMAGINE", "pageId": 901, "name": "Spicy Mode"},
        "grok-video-image":  {"type": "video", "mode": "normal", "channel": "GROK_IMAGINE", "pageId": 901, "name": "Image to Video"},
        "grok-image":        {"type": "image", "mode": "normal", "channel": "GROK_TEXT_IMAGE", "pageId": 901, "name": "Text to Image"}
    },
    "DEFAULT_MODEL": "grok-video-normal",
    # Ratio map: UI value -> what the Ximagine API actually accepts (confirmed from live capture)
    "RATIO_MAP": {
        "1:1": "1:1",
        "16:9": "16:9",
        "9:16": "2:3"
    }
}

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# =================================================================
# 2. Data Persistence
# =================================================================
def load_data():
    default = {"stats": {"total": 0, "success": 0, "failed": 0}, "history": [], "theme": "cyberpunk"}
    if os.path.exists(CONFIG["DATA_FILE"]):
        try:
            with open(CONFIG["DATA_FILE"], "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default
    return default

def save_data(data):
    with open(CONFIG["DATA_FILE"], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =================================================================
# 3. Core Engine
# =================================================================
class XimagineEngine:
    @staticmethod
    def generate_identity():
        def get_part(): return random.randint(1, 254)
        ip = f"{get_part()}.{get_part()}.{get_part()}.{get_part()}"
        major = random.randint(128, 132)
        build = random.randint(6000, 7000)
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.0 Safari/537.36"
        sec_ch_ua = f'"Google Chrome";v="{major}", "Chromium";v="{major}", "Not_A Brand";v="24"'
        return {"ip": ip, "ua": ua, "sec_ch_ua": sec_ch_ua}

    @staticmethod
    def get_headers(unique_id=None):
        """
        Headers for generation requests.
        No auth token here so requests go through as anonymous,
        which gives unlimited free generations like before.
        """
        ident = XimagineEngine.generate_identity()
        uid = unique_id or uuid.uuid4().hex
        return {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': CONFIG["ORIGIN_URL"],
            'Referer': f'{CONFIG["ORIGIN_URL"]}/',
            'User-Agent': ident["ua"],
            'uniqueid': uid,
            'X-Forwarded-For': ident["ip"],
            'X-Real-IP': ident["ip"],
            'sec-ch-ua': ident["sec_ch_ua"],
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'priority': 'u=1, i'
        }

    @staticmethod
    def get_upload_headers(file_name):
        """
        Headers for upload to aiquickdraw CDN.
        Uses RSA-encrypted auth + account auth token.
        """
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwJaZ7xi/H1H1jRg3DfYEEaqNYZZQHhzOZkdzzlkE510s/lP0vxZgHDVAI5dBevSpHtZHseWtKp93jqQwmdaaITGA+A2VpXDr2t8yJ0TZ3EjttLWWUT14Z+xAN04JUqks8/fm3Lpff9PYf8xGdh0zOO6XHu36N2zlK3KcpxoGBiYGYT0yJ4mH4gawXW18lddB+WuLFktzj9rPWaT2ofk1n+aULAr6lthpgFah47QI93bNwQ7cLuvwUUDmlfa4SUJlrdjfdWh7Vzh4amkmq+aR29FdZ0XLRo9FhMBQopGZCPFIucOjpYPIoWbSEQBR6VlM6OrZ4wHpLzAjVNnaGYdRLQIDAQAB
-----END PUBLIC KEY-----"""

        payload = json.dumps({
            "timestamp": int(time.time() * 1000),
            "path": "tools/file/video",
            "fileName": file_name
        })

        public_key = serialization.load_pem_public_key(
            RSA_PUBLIC_KEY.encode(),
            backend=default_backend()
        )
        encrypted = public_key.encrypt(
            payload.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        encrypted_auth = base64.b64encode(encrypted).decode()

        ident = XimagineEngine.generate_identity()
        return {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Authorization': f"Encrypted {encrypted_auth}",
            'Origin': CONFIG["ORIGIN_URL"],
            'Referer': f'{CONFIG["ORIGIN_URL"]}/',
            'User-Agent': ident["ua"],
            'uniqueid': uuid.uuid4().hex,
            'X-Forwarded-For': ident["ip"],
            'X-Real-IP': ident["ip"],
            'sec-ch-ua': ident["sec_ch_ua"],
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }

    @staticmethod
    def build_payload(prompt, model_config, aspect_ratio, image_urls):
        """Build payload matching exactly what the live Ximagine website sends"""
        api_ratio = CONFIG["RATIO_MAP"].get(aspect_ratio, aspect_ratio)
        print(f"[RATIO] UI selected: {aspect_ratio} -> Sending to API: {api_ratio}")

        payload = {
            "prompt": prompt,
            "channel": model_config["channel"],
            "pageId": model_config["pageId"],
            "source": "ximagine.io",
        "watermarkFlag": True,
"removeWatermark": True,
            "private": False,
            "privateFlag": False,
            "isTemp": True,
            "model": "grok-imagine",
            "videoType": "text-to-video",
            "aspectRatio": api_ratio,
            "imageUrls": []
        }

        if model_config["type"] == "video":
            payload["mode"] = model_config["mode"]
            if image_urls:
                payload["videoType"] = "image-to-video"
                payload["imageUrls"] = image_urls

        return payload

# =================================================================
# 4. Business Logic (API Routes)
# =================================================================
@app.route('/v1/models', methods=['GET'])
def list_models():
    models = []
    for k, v in CONFIG["MODEL_MAP"].items():
        models.append({
            "id": k,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "ximagine",
            "name": v["name"]
        })
    return jsonify({"object": "list", "data": models})

@app.route('/v1/upload', methods=['POST'])
def handle_upload():
    """
    Try uploading to Ximagine CDN first.
    Falls back to imgbb if CDN rejects (Turnstile blocked).
    """
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400

    try:
        import io
        file_content = file.read()

        # --- Attempt 1: Upload to Ximagine CDN ---
        try:
            file_obj = io.BytesIO(file_content)
            upload_headers = XimagineEngine.get_upload_headers(file.filename)
            files = {
                'file': (file.filename, file_obj, file.content_type or 'image/png'),
                'path': (None, "tools/file/video")
            }
            res = requests.post(CONFIG["UPLOAD_URL"], headers=upload_headers, files=files, timeout=60, verify=False)
            print(f"[UPLOAD CDN] Status  : {res.status_code}")
            print(f"[UPLOAD CDN] Response: {res.text[:300]}")
            data = res.json()
            if data.get("code") == 200 and data.get("data"):
                image_url = data["data"]
                print(f"[UPLOAD CDN OK] URL: {image_url}")
                return jsonify({"success": True, "data": {"url": image_url}, "code": 200})
        except Exception as cdn_err:
            print(f"[UPLOAD CDN FAILED] {cdn_err} - falling back to imgbb")

        # --- Attempt 2: Fall back to imgbb ---
        b64_image = base64.b64encode(file_content).decode('utf-8')
        res2 = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": CONFIG["IMGBB_API_KEY"], "image": b64_image, "name": file.filename},
            timeout=60
        )
        print(f"[UPLOAD IMGBB] Status  : {res2.status_code}")
        print(f"[UPLOAD IMGBB] Response: {res2.text[:300]}")
        data2 = res2.json()
        if data2.get("success") and data2.get("data", {}).get("url"):
            image_url = data2["data"]["url"]
            print(f"[UPLOAD IMGBB OK] URL: {image_url}")
            return jsonify({"success": True, "data": {"url": image_url}, "code": 200})

        return jsonify({"success": False, "error": "Both upload methods failed", "raw": data2})

    except Exception as e:
        import traceback
        print(f"[UPLOAD EXCEPTION] {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/v1/proxy/download', methods=['GET'])
def proxy_download():
    """Proxy video download - streams with correct headers for browser save dialog"""
    url = request.args.get('url')
    if not url:
        return "Missing URL", 400
    try:
        headers = {
            "User-Agent": XimagineEngine.generate_identity()["ua"],
            "Referer": CONFIG["ORIGIN_URL"],
            "Accept": "*/*"
        }
        req = requests.get(url, headers=headers, stream=True, timeout=60, verify=False)

        filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
        if not filename.endswith('.mp4'):
            filename += '.mp4'

        def generate_stream():
            for chunk in req.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        response = Response(
            stream_with_context(generate_stream()),
            content_type=req.headers.get('Content-Type', 'video/mp4')
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Length'] = req.headers.get('Content-Length', '')
        response.headers['Accept-Ranges'] = 'bytes'
        return response

    except Exception as e:
        print(f"[DOWNLOAD ERROR] {str(e)}")
        return str(e), 500

@app.route('/v1/query/status', methods=['GET'])
def query_status():
    """Status query API for frontend client polling"""
    task_id = request.args.get('taskId')
    unique_id = request.args.get('uniqueId')
    task_type = request.args.get('type', 'video')
    if not task_id:
        return jsonify({"error": "Missing taskId"}), 400
    try:
        headers = XimagineEngine.get_headers(unique_id)
        channel = "GROK_TEXT_IMAGE" if task_type == "image" else "GROK_IMAGINE"
        res = requests.get(
            f"{CONFIG['API_BASE']}/ai/{task_id}?channel={channel}",
            headers=headers, timeout=10, verify=False
        )
        poll_data = res.json()
        data = poll_data.get("data", {})
        result = {"status": "processing", "progress": 0}
        if data.get("completeData"):
            try:
                inner = json.loads(data["completeData"])
                if inner.get("data") and inner["data"].get("result_urls") and len(inner["data"]["result_urls"]) > 0:
                    result["status"] = "completed"
                    result["videoUrl"] = inner["data"]["result_urls"][0]
                    result["urls"] = inner["data"]["result_urls"]
                else:
                    result["status"] = "failed"
                    result["error"] = f"No video returned (may have triggered content filter): {json.dumps(inner)[:200]}"
            except Exception as e:
                result["status"] = "failed"
                result["error"] = f"Failed to parse response: {str(e)}"
        elif data.get("failMsg"):
            result["status"] = "failed"
            result["error"] = data["failMsg"]
        else:
            if data.get("progress"):
                result["progress"] = int(float(data["progress"]) * 100)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    body = request.json
    messages = body.get("messages", [])

    prompt = ""
    image_urls = []
    aspect_ratio = "1:1"
    client_poll_mode = False

    last_content = messages[-1]["content"]
    if isinstance(last_content, str):
        try:
            if last_content.strip().startswith('{'):
                parsed = json.loads(last_content)
                prompt = parsed.get("prompt", "")
                image_urls = parsed.get("imageUrls", [])
                aspect_ratio = parsed.get("aspectRatio", "1:1")
                client_poll_mode = parsed.get("clientPollMode", False)
                if parsed.get("model") and parsed["model"] in CONFIG["MODEL_MAP"]:
                    body["model"] = parsed["model"]
            else:
                prompt = last_content
        except:
            prompt = last_content
    elif isinstance(last_content, list):
        for part in last_content:
            if part["type"] == "text": prompt += part["text"]
            if part["type"] == "image_url": image_urls.append(part["image_url"]["url"])

    model_key = body.get("model", CONFIG["DEFAULT_MODEL"])
    if model_key not in CONFIG["MODEL_MAP"]: model_key = CONFIG["DEFAULT_MODEL"]
    if image_urls: model_key = "grok-video-image"

    model_config = CONFIG["MODEL_MAP"][model_key]
    unique_id = uuid.uuid4().hex

    print(f"[REQUEST] model={model_key} | ratio={aspect_ratio} | prompt={prompt[:60]}")

    # ============ clientPollMode: async, returns task ID immediately ============
    if client_poll_mode:
        try:
            # No auth token in headers - anonymous requests = unlimited generations
            headers = XimagineEngine.get_headers(unique_id)
            payload = XimagineEngine.build_payload(prompt, model_config, aspect_ratio, image_urls)
            endpoint = f"{CONFIG['API_BASE']}/ai/video/create" if model_config["type"] == "video" else f"{CONFIG['API_BASE']}/ai/grok/create"

            res = requests.post(endpoint, headers=headers, json=payload, timeout=30, verify=False)
            res_data = res.json()

            print(f"[GEN DEBUG] Status  : {res.status_code}")
            print(f"[GEN DEBUG] Response: {res_data}")

            if res_data.get("code") != 200:
                raise Exception(f"Upstream rejected: {res_data}")

            task_id = res_data["data"]

            def async_generate():
                chunk = {
                    "id": f"chatcmpl-{uuid.uuid4()}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_key,
                    "choices": [{"index": 0, "delta": {"content": f"\n\n✅ **Task Submitted**\n- [TASK_ID:{task_id}|UID:{unique_id}|TYPE:{model_config['type']}]\n"}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return Response(stream_with_context(async_generate()), mimetype='text/event-stream')

        except Exception as e:
            print(f"[GEN EXCEPTION] {str(e)}")
            return jsonify({"error": str(e)}), 500

    # ============ Sync mode: backend polls until complete ============
    def generate():
        def send_chunk(content, finish_reason=None, is_reasoning=False):
            delta = {"reasoning_content": content} if is_reasoning else {"content": content}
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_key,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
            }
            return f"data: {json.dumps(chunk)}\n\n"

        yield send_chunk("🚀 **Initializing generation task...**\n", is_reasoning=True)

        try:
            # No auth token - anonymous requests
            headers = XimagineEngine.get_headers()
            payload = XimagineEngine.build_payload(prompt, model_config, aspect_ratio, image_urls)
            endpoint = f"{CONFIG['API_BASE']}/ai/video/create" if model_config["type"] == "video" else f"{CONFIG['API_BASE']}/ai/grok/create"

            yield send_chunk("📡 Submitting to Ximagine compute cluster...\n", is_reasoning=True)

            res = requests.post(endpoint, headers=headers, json=payload, timeout=30, verify=False)
            res_data = res.json()

            print(f"[GEN DEBUG] Status  : {res.status_code}")
            print(f"[GEN DEBUG] Response: {res_data}")

            if res_data.get("code") != 200:
                raise Exception(f"Upstream rejected: {res_data}")

            task_id = res_data["data"]
            yield send_chunk(f"✅ Task created (TaskID: {task_id})\n", is_reasoning=True)

            start_time = time.time()
            while time.time() - start_time < 120:
                poll_res = requests.get(
                    f"{CONFIG['API_BASE']}/ai/{task_id}?channel={model_config['channel']}",
                    headers=headers, timeout=10, verify=False
                )
                poll_data = poll_res.json()
                data = poll_data.get("data", {})

                if data.get("completeData"):
                    inner = json.loads(data["completeData"])
                    if inner.get("code") == 200 and inner.get("data", {}).get("result_urls"):
                        video_url = inner["data"]["result_urls"][0]
                        db = load_data()
                        db["stats"]["total"] += 1
                        db["stats"]["success"] += 1
                        db["history"].insert(0, {"prompt": prompt, "url": video_url, "time": datetime.now().strftime("%H:%M"), "type": "video"})
                        save_data(db)
                        proxy_url = f"http://127.0.0.1:{CONFIG['PORT']}/v1/proxy/download?url={requests.utils.quote(video_url)}"
                        md = f'''
# 🎬 Video Generation Complete

<video src="{proxy_url}" controls autoplay loop style="width:100%; max-width:800px; border-radius:12px; box-shadow: 0 8px 32px rgba(0,0,0,0.2);"></video>

## 📥 Download Links
- [**Download via Proxy (Recommended)**]({proxy_url})
- [Direct Download]({video_url})

**Task Details:**
- **Model:** `{model_key}`
- **Aspect Ratio:** `{aspect_ratio}`
'''
                        yield send_chunk(md)
                        yield send_chunk("", "stop")
                        break
                    else:
                        raise Exception(f"Generation failed or blocked by content filter: {inner}")

                elif data.get("failMsg"):
                    raise Exception(f"Generation failed: {data['failMsg']}")

                progress = data.get("progress", 0)
                if not progress:
                    elapsed = time.time() - start_time
                    progress = min(0.95, elapsed / 60.0)

                bar_len = 20
                filled = int(float(progress) * bar_len)
                bar = "█" * filled + "░" * (bar_len - filled)
                yield send_chunk(f"⏳ Rendering video: [{bar}] {int(float(progress)*100)}%\n", is_reasoning=True)
                time.sleep(2)
            else:
                raise Exception("Task timed out")

        except Exception as e:
            db = load_data()
            db["stats"]["total"] += 1
            db["stats"]["failed"] += 1
            save_data(db)
            yield send_chunk(f"\n>>> [Error] {str(e)}")
            yield send_chunk("", "stop")

        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# =================================================================
# 5. Dashboard UI - Grok Style
# =================================================================
@app.route('/')
def index():
    return app.send_static_file('index.html')

def _unused_old_ui():
    origin = f"http://127.0.0.1:{CONFIG['PORT']}"
    api_key = CONFIG["API_KEY"]
    version = CONFIG["VERSION"]
    imgbb_key = CONFIG["IMGBB_API_KEY"]

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CYBERPUNK STUDIO | XIMAGINE ENGINE</title>
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Rajdhani:wght@300;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {{
      --neon-blue: #00f5ff; --neon-pink: #ff00ff; --neon-yellow: #ffd700; --neon-purple: #9d4edd;
      --bg-dark: #0a0a0f; --panel: rgba(15, 15, 25, 0.92); --border: rgba(0, 245, 255, 0.3);
      --glass: rgba(255, 255, 255, 0.08); --text: #ffffff; --text-secondary: #a0a0b0;
      --card-gradient: linear-gradient(135deg, rgba(0, 245, 255, 0.1) 0%, rgba(255, 0, 255, 0.05) 100%);
    }}
    [data-theme="matrix"] {{
      --neon-blue: #00ff41; --neon-pink: #008f11; --bg-dark: #000; --panel: rgba(0, 20, 0, 0.95);
      --border: rgba(0, 255, 65, 0.4); --text: #00ff41; --text-secondary: #008f11;
    }}
    [data-theme="golden"] {{
      --neon-blue: #ffd700; --neon-pink: #ff8c42; --bg-dark: #1a1000; --panel: rgba(30, 20, 0, 0.92);
      --border: rgba(255, 215, 0, 0.4); --text: #ffd700; --text-secondary: #b8860b;
    }}
    [data-theme="clean"] {{
      --neon-blue: #4a90e2; --neon-pink: #50c878; --bg-dark: #f8f9fa; --panel: rgba(255, 255, 255, 0.95);
      --border: rgba(74, 144, 226, 0.3); --text: #2c3e50; --text-secondary: #7f8c8d;
    }}
    * {{ box-sizing: border-box; scrollbar-width: thin; scrollbar-color: var(--neon-blue) #111; }}
    body {{ margin: 0; background: var(--bg-dark); color: var(--text); font-family: 'Rajdhani', sans-serif;
      height: 100vh; display: flex; overflow: hidden; transition: background 0.5s; }}
    .sidebar {{ width: 380px; background: var(--panel); border-right: 1px solid var(--border);
      display: flex; flex-direction: column; padding: 20px; z-index: 10; overflow-y: auto; }}
    .brand {{ font-family: 'Orbitron', sans-serif; font-size: 22px; color: var(--neon-blue);
      letter-spacing: 2px; margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between; }}
    .brand-text span {{ font-size: 10px; background: var(--neon-blue); color: #000; padding: 2px 6px; border-radius: 2px; margin-left: 8px; }}
    .theme-btn {{ background: var(--neon-blue); border: none; color: #000; width: 32px; height: 32px;
      border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
    .theme-btn:hover {{ opacity: 0.8; transform: scale(1.1); }}
    .section-title {{ color: var(--text); font-size: 14px; letter-spacing: 1px; text-transform: uppercase;
      margin-bottom: 12px; border-bottom: 2px solid var(--border); padding-bottom: 5px; font-weight: 600; }}
    .control-group {{ margin-bottom: 20px; }}
    .info-card {{ background: var(--glass); border: 1px solid var(--border); border-radius: 8px; padding: 15px; margin-bottom: 20px; }}
    .info-row {{ margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }}
    .info-row:last-child {{ margin-bottom: 0; }}
    .info-label {{ color: var(--text); font-weight: 600; font-size: 13px; }}
    .info-value {{ color: var(--text-secondary); font-family: monospace; font-size: 11px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }}
    .copy-btn {{ background: var(--neon-blue); border: none; color: #000; border-radius: 4px; padding: 4px 10px; font-size: 11px; cursor: pointer; }}
    .copy-btn:hover {{ opacity: 0.9; }}
    label {{ display: block; font-size: 13px; color: var(--text); margin-bottom: 6px; font-weight: 500; }}
    select, input, textarea {{ width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--border);
      color: var(--text); padding: 10px; font-family: 'Rajdhani', sans-serif; border-radius: 6px; }}
    select:focus, input:focus, textarea:focus {{ border-color: var(--neon-blue); outline: none; }}
    .btn-gen {{ width: 100%; background: linear-gradient(90deg, var(--neon-blue), var(--neon-pink)); border: none;
      padding: 15px; font-family: 'Orbitron', sans-serif; font-weight: bold; color: #fff; font-size: 16px;
      cursor: pointer; border-radius: 8px; text-transform: uppercase; letter-spacing: 2px; margin-top: auto; }}
    .btn-gen:hover {{ filter: brightness(1.1); transform: translateY(-2px); }}
    .btn-gen:disabled {{ filter: grayscale(0.8); cursor: not-allowed; transform: none; }}
    .upload-zone {{ border: 2px dashed var(--border); border-radius: 8px; padding: 20px; text-align: center;
      cursor: pointer; transition: 0.3s; background: rgba(255,255,255,0.02); min-height: 80px;
      display: flex; flex-direction: column; align-items: center; justify-content: center; }}
    .upload-zone:hover, .upload-zone.dragover {{ border-color: var(--neon-blue); background: rgba(0, 245, 255, 0.05); }}
    .upload-info {{ font-size: 12px; color: var(--text-secondary); }}
    .preview-wrapper {{ position: relative; display: none; margin-top: 10px; }}
    .upload-preview {{ max-height: 120px; max-width: 100%; border-radius: 6px; border: 2px solid var(--neon-blue); }}
    .btn-delete-img {{ position: absolute; top: -8px; right: -8px; background: #ff4757; color: #fff; border: none;
      border-radius: 50%; width: 24px; height: 24px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 12px; }}
    .mode-hint {{ font-size: 12px; color: var(--text-secondary); margin-top: 10px; text-align: center; padding: 8px; background: var(--glass); border-radius: 4px; }}
    .char-counter {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--text-secondary); margin-top: 8px; padding: 8px; background: var(--glass); border-radius: 6px; }}
    .char-counter.warning {{ color: #ff9800; }}
    .char-counter.error {{ color: #f44336; }}
    .main {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}
    .gallery {{ flex: 1; padding: 25px; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; align-content: start; }}
    .gallery-item {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
      transition: all 0.3s; position: relative; animation: fadeIn 0.5s ease; }}
    @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .gallery-item:hover {{ transform: translateY(-5px); border-color: var(--neon-blue); box-shadow: 0 8px 30px rgba(0,0,0,0.4); }}
    .media-container {{ width: 100%; aspect-ratio: 16/9; background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%);
      display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative; }}
    .media-container img, .media-container video {{ width: 100%; height: 100%; object-fit: cover; }}
    .item-info {{ padding: 15px; font-size: 13px; background: var(--card-gradient); }}
    .item-prompt {{ color: var(--text); font-size: 14px; margin-bottom: 10px; overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
    .item-meta {{ display: flex; flex-wrap: wrap; gap: 6px; font-size: 12px; }}
    .meta-tag {{ background: var(--glass); padding: 3px 8px; border-radius: 10px; border: 1px solid var(--border); }}
    .meta-tag i {{ font-size: 10px; color: var(--neon-blue); margin-right: 4px; }}
    .item-actions {{ display: flex; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }}
    .action-btn {{ flex: 1; padding: 6px; border: none; border-radius: 4px; font-size: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px; }}
    .btn-download {{ background: var(--neon-blue); color: #000; }}
    .btn-delete {{ background: #ff4757; color: #fff; }}
    .task-overlay {{ position: absolute; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(5px);
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; }}
    .task-spinner {{ width: 40px; height: 40px; border: 3px solid var(--neon-blue); border-top-color: transparent;
      border-radius: 50%; animation: spin 1s linear infinite; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .task-status-bar {{ position: absolute; bottom: 0; left: 0; width: 100%; height: 5px; background: rgba(255,255,255,0.1); }}
    .task-progress-fill {{ height: 100%; background: linear-gradient(90deg, var(--neon-blue), var(--neon-pink)); transition: width 0.3s; }}
    .toast {{ position: fixed; top: 20px; right: 20px; background: var(--panel); border-left: 4px solid var(--neon-blue);
      padding: 15px 20px; color: var(--text); z-index: 200; transform: translateX(150%); transition: 0.3s; border-radius: 4px; }}
    .toast.show {{ transform: translateX(0); }}
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="brand">
      <div class="brand-text">XIMAGINE PRO<span>{version}</span></div>
      <button class="theme-btn" onclick="toggleTheme()" title="Switch Theme"><i class="fas fa-palette"></i></button>
    </div>
    <div class="control-group">
      <div class="info-card">
        <div class="info-row">
          <span class="info-label">API Address</span>
          <span class="info-value" id="api-origin">{origin}</span>
          <button class="copy-btn" onclick="copyApiOrigin()">Copy</button>
        </div>
        <div class="info-row">
          <span class="info-label">API Key</span>
          <span class="info-value" id="api-key">{api_key}</span>
          <button class="copy-btn" onclick="copyApiKey()">Copy</button>
        </div>
      </div>
    </div>
    <div style="font-size:12px; color:#ff4444; margin-bottom:20px; padding:10px; border:1px solid #ff4444; border-radius:5px; background:rgba(255,68,68,0.1);">
      ⚠️ <b>Warning:</b> Data will be lost if you refresh or close the page. Download your videos before closing!
    </div>
    <div class="control-group">
      <div class="section-title">Settings</div>
      <label for="ratio">Aspect Ratio</label>
      <select id="ratio">
        <option value="1:1">1:1 (Square)</option>
        <option value="16:9">16:9 (Landscape)</option>
        <option value="9:16">9:16 (Portrait)</option>
      </select>
      <label for="video-mode" style="margin-top:10px">Video Style</label>
      <select id="video-mode">
        <option value="normal">Standard Realistic</option>
        <option value="fun">Fun Cartoon</option>
        <option value="spicy">Spicy Mode</option>
      </select>
    </div>
    <div class="control-group" style="flex:1">
      <div class="section-title">Reference Image (Optional)</div>
      <div class="upload-zone" id="drop-zone">
        <div id="upload-placeholder">
          <div class="upload-info">
            <i class="fas fa-cloud-upload-alt" style="font-size:24px;margin-bottom:5px"></i><br>
            Click or drag and drop an image here
          </div>
        </div>
        <div class="preview-wrapper" id="preview-wrapper">
          <img id="upload-preview" class="upload-preview">
          <button class="btn-delete-img" onclick="deleteImage(event)"><i class="fas fa-times"></i></button>
        </div>
      </div>
      <div class="mode-hint" id="mode-hint"><i class="fas fa-keyboard"></i> Current Mode: Text to Video</div>
      <input type="file" id="file-input" style="display:none" accept="image/*">
      <div class="section-title" style="margin-top:15px">Creative Prompt</div>
      <textarea id="prompt" rows="4" maxlength="1800" placeholder="Enter your creative description here..."></textarea>
      <div class="char-counter" id="char-counter">
        <span><span id="current-chars">0</span> / 1800</span>
        <span>Character Limit</span>
      </div>
    </div>
    <button class="btn-gen" id="btn-gen" onclick="submitTask()"><i class="fas fa-play"></i> Generate</button>
  </div>
  <div class="main">
    <div class="gallery" id="gallery"></div>
  </div>
  <div class="toast" id="toast">Message</div>
  <script>
    var API_KEY = "{api_key}";
    var ORIGIN = "{origin}";
    var IMGBB_KEY = "{imgbb_key}";
    let uploadedImageUrl = null;
    let tasks = [];
    let history = [];

    function copyToClipboard(text) {{ navigator.clipboard.writeText(text).then(() => showToast("Copied to clipboard")); }}
    function copyApiOrigin() {{ copyToClipboard(document.getElementById('api-origin').textContent); }}
    function copyApiKey() {{ copyToClipboard(document.getElementById('api-key').textContent); }}
    function showToast(msg) {{ const t = document.getElementById('toast'); t.innerText = msg; t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 3000); }}

    const themes = ['cyberpunk', 'matrix', 'golden', 'clean'];
    function toggleTheme() {{
      let current = localStorage.getItem('ximagine_theme') || 'cyberpunk';
      let idx = themes.indexOf(current);
      let next = themes[(idx + 1) % themes.length];
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('ximagine_theme', next);
      showToast('Theme: ' + next);
    }}

    function init() {{
      const savedTheme = localStorage.getItem('ximagine_theme') || 'cyberpunk';
      document.documentElement.setAttribute('data-theme', savedTheme);
      updateCharCounter();
      document.getElementById('prompt').addEventListener('input', updateCharCounter);
      document.getElementById('drop-zone').addEventListener('click', function(e) {{
        if (uploadedImageUrl) return;
        document.getElementById('file-input').click();
      }});
      document.getElementById('file-input').addEventListener('change', function(e) {{
        if (e.target.files[0]) uploadFile(e.target.files[0]);
      }});
      const dropZone = document.getElementById('drop-zone');
      dropZone.addEventListener('dragover', (e) => {{ e.preventDefault(); dropZone.classList.add('dragover'); }});
      dropZone.addEventListener('dragleave', (e) => {{ e.preventDefault(); dropZone.classList.remove('dragover'); }});
      dropZone.addEventListener('drop', (e) => {{
        e.preventDefault(); dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
      }});
      renderGallery();
    }}

    function updateCharCounter() {{
      const textarea = document.getElementById('prompt');
      const counter = document.getElementById('char-counter');
      const currentChars = document.getElementById('current-chars');
      const charCount = textarea.value.length;
      currentChars.textContent = charCount;
      counter.classList.remove('warning', 'error');
      if (charCount >= 1800) counter.classList.add('error');
      else if (charCount >= 1600) counter.classList.add('warning');
    }}

    async function uploadFile(file) {{
      try {{
        document.getElementById('upload-placeholder').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(ORIGIN + '/v1/upload', {{ method: 'POST', body: formData }});
        const data = await res.json();
        if (data.success && data.data && data.data.url) {{
          uploadedImageUrl = data.data.url;
          showPreview(uploadedImageUrl);
          showToast('Image uploaded successfully');
        }} else {{
          throw new Error(data.error || 'Upload failed');
        }}
      }} catch(e) {{
        document.getElementById('upload-placeholder').innerHTML =
          '<div class="upload-info"><i class="fas fa-cloud-upload-alt" style="font-size:24px"></i><br>Click or drag and drop an image</div>';
        showToast('Upload failed: ' + e.message);
      }}
    }}

    function showPreview(url) {{
      document.getElementById('upload-preview').src = url;
      document.getElementById('preview-wrapper').style.display = 'block';
      document.getElementById('upload-placeholder').style.display = 'none';
      document.getElementById('mode-hint').innerHTML = '<i class="fas fa-magic"></i> Current Mode: Image to Video';
    }}

    function deleteImage(e) {{
      e.stopPropagation();
      uploadedImageUrl = null;
      document.getElementById('preview-wrapper').style.display = 'none';
      document.getElementById('upload-placeholder').style.display = 'flex';
      document.getElementById('upload-placeholder').innerHTML =
        '<div class="upload-info"><i class="fas fa-cloud-upload-alt" style="font-size:24px"></i><br>Click or drag and drop an image</div>';
      document.getElementById('file-input').value = '';
      document.getElementById('mode-hint').innerHTML = '<i class="fas fa-keyboard"></i> Current Mode: Text to Video';
    }}

    async function submitTask() {{
      const prompt = document.getElementById('prompt').value.trim();
      if (!prompt) return showToast('Please enter a prompt');
      if (prompt.length > 1800) return showToast('Prompt exceeds character limit');
      const ratio = document.getElementById('ratio').value;
      const videoStyle = document.getElementById('video-mode').value;
      let modelId = 'grok-video-' + videoStyle;
      if (uploadedImageUrl) modelId = 'grok-video-image';
      const taskId = 'loc_' + Date.now();
      const newTask = {{
        id: taskId, status: 'pending', prompt, model: modelId,
        ratio, refImage: uploadedImageUrl,
        date: new Date().toLocaleString(), progress: 0, pollCount: 0
      }};
      tasks.unshift(newTask);
      renderGallery();
      processTask(newTask);
    }}

    function renderGallery() {{
      const container = document.getElementById('gallery');
      container.innerHTML = '';
      const allItems = [...tasks, ...history];
      allItems.forEach(item => {{
        const el = document.createElement('div');
        el.className = 'gallery-item';
        let mediaContent = '';
        if (item.status === 'completed') {{
          const videoUrl = (item.urls && item.urls[0]) || item.videoUrl || '';
          mediaContent = '<video src="' + videoUrl + '" controls loop playsinline></video>';
        }} else if (item.status === 'failed') {{
          mediaContent = '<div style="color:#ff4757;padding:20px;text-align:center">Generation Failed</div>';
        }} else {{
          mediaContent =
            '<div class="task-overlay">' +
            '<div class="task-spinner"></div>' +
            '<div style="font-size:12px;color:var(--neon-blue)">' + (item.status === 'pending' ? 'Initializing...' : 'Rendering...') + '</div>' +
            '<div style="font-size:14px">Poll #' + (item.pollCount || 0) + '</div>' +
            '</div>' +
            '<div class="task-status-bar"><div class="task-progress-fill" style="width:' + (item.progress || 0) + '%"></div></div>';
          if (item.refImage) mediaContent = '<img src="' + item.refImage + '" style="opacity:0.3">' + mediaContent;
        }}
        let actionsHtml = '';
        if (item.status === 'completed' && item.urls && item.urls.length > 0) {{
          actionsHtml =
            '<div class="item-actions">' +
            '<button class="action-btn btn-download" onclick="downloadVideo(\\'' + item.urls[0] + '\\', \\'' + item.id + '\\')"><i class="fas fa-download"></i> Download</button>' +
            '<button class="action-btn btn-delete" onclick="deleteItem(\\'' + item.id + '\\')"><i class="fas fa-trash"></i> Delete</button>' +
            '</div>';
        }} else if (item.status === 'failed') {{
          actionsHtml =
            '<div class="item-actions">' +
            '<button class="action-btn btn-delete" onclick="deleteItem(\\'' + item.id + '\\')"><i class="fas fa-trash"></i> Delete</button>' +
            '</div>';
        }}
        el.innerHTML =
          '<div class="media-container" id="media-' + item.id + '">' + mediaContent + '</div>' +
          '<div class="item-info">' +
          '<div class="item-prompt">' + item.prompt.replace(/</g, '&lt;') + '</div>' +
          '<div class="item-meta">' +
          '<span class="meta-tag"><i class="fas fa-film"></i>' + item.model + '</span>' +
          '<span class="meta-tag"><i class="fas fa-expand"></i>' + item.ratio + '</span>' +
          '</div>' + actionsHtml + '</div>';
        container.appendChild(el);
      }});
    }}

    async function processTask(task) {{
      try {{
        task.status = 'processing';
        renderGallery();
        const payload = {{
          model: task.model,
          messages: [{{ role: 'user', content: JSON.stringify({{
            prompt: task.prompt,
            aspectRatio: task.ratio,
            clientPollMode: true,
            imageUrls: task.refImage ? [task.refImage] : []
          }}) }}],
          stream: true
        }};
        const res = await fetch(ORIGIN + '/v1/chat/completions', {{
          method: 'POST',
          headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let realTaskId = null, uniqueId = null;
        while (true) {{
          const {{ done, value }} = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, {{ stream: true }});
          const match = buffer.match(/\\[TASK_ID:(.*?)\\|UID:(.*?)\\|TYPE:(.*?)\\]/);
          if (match) {{ realTaskId = match[1]; uniqueId = match[2]; break; }}
        }}
        if (!realTaskId) throw new Error('Could not retrieve task ID');
        pollTaskStatus(task, realTaskId, uniqueId);
      }} catch (e) {{
        console.error(e);
        task.status = 'failed';
        renderGallery();
        showToast('Generation failed: ' + e.message);
      }}
    }}

    function pollTaskStatus(task, realTaskId, uniqueId) {{
      let count = 0;
      const pollInterval = setInterval(async () => {{
        count++;
        task.pollCount = count;
        if (task.progress < 95) {{ task.progress += 1; updateTaskUI(task); }}
        try {{
          const res = await fetch(
            ORIGIN + '/v1/query/status?taskId=' + realTaskId + '&uniqueId=' + uniqueId + '&type=video',
            {{ headers: {{ 'Authorization': 'Bearer ' + API_KEY }} }}
          );
          const data = await res.json();
          if (data.status === 'completed' || data.videoUrl || (data.urls && data.urls.length > 0)) {{
            clearInterval(pollInterval);
            task.status = 'completed';
            task.progress = 100;
            task.urls = data.urls || (data.videoUrl ? [data.videoUrl] : []);
            moveToHistory(task);
          }} else if (data.status === 'failed') {{
            clearInterval(pollInterval);
            task.status = 'failed';
            renderGallery();
            showToast('Generation failed: ' + (data.error || 'Unknown error'));
          }} else if (data.progress) {{
            task.progress = data.progress;
            updateTaskUI(task);
          }}
        }} catch(e) {{
          if (count > 60) {{ clearInterval(pollInterval); task.status = 'failed'; renderGallery(); showToast('Generation timed out'); }}
        }}
      }}, 2000);
    }}

    function updateTaskUI(task) {{
      const mediaEl = document.getElementById('media-' + task.id);
      if (mediaEl && task.status !== 'completed') {{
        const progressFill = mediaEl.querySelector('.task-progress-fill');
        const progressText = mediaEl.querySelector('.task-overlay div:last-child');
        if (progressFill) progressFill.style.width = (task.progress || 0) + '%';
        if (progressText) progressText.innerText = 'Poll #' + (task.pollCount || 0);
      }}
    }}

    function moveToHistory(task) {{
      tasks = tasks.filter(t => t.id !== task.id);
      history.unshift({{
        id: 'hist_' + Date.now(), status: 'completed', prompt: task.prompt,
        urls: task.urls, date: task.date, model: task.model, ratio: task.ratio
      }});
      renderGallery();
      showToast('Generation complete!');
    }}

    function deleteItem(itemId) {{
      if (!confirm('Are you sure you want to delete this item?')) return;
      tasks = tasks.filter(t => t.id !== itemId);
      history = history.filter(h => h.id !== itemId);
      renderGallery();
      showToast('Deleted');
    }}

    function downloadVideo(url, itemId) {{
  const proxyUrl = ORIGIN + '/v1/proxy/download?url=' + encodeURIComponent(url);
  // Open in system browser which handles downloads properly
  // PyWebView cannot trigger file saves directly
  window.open(proxyUrl, '_blank');
  showToast('Opening in browser - save the video from there');
}}

    init();
  </script>
</body>
</html>'''
    return html

# =================================================================
# 6. Entry Point
# =================================================================
def run_flask():
    app.run(port=CONFIG["PORT"], threaded=True)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    webview.create_window(
        CONFIG["PROJECT_NAME"],
        f"http://127.0.0.1:{CONFIG['PORT']}",
        width=1498,
        height=1739,
        background_color='#050505',
        resizable=True
    )
    webview.start()