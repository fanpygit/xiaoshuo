"""表情包换脸 Web 服务（Flask）。

接口:
    GET  /                前端页面
    GET  /api/health      健康检查
    GET  /api/templates   列出 templates/ 目录下的模板图片
    POST /api/generate    上传源照片 + 目标图/模板，生成换脸表情包
    GET  /output/<name>   获取生成结果
"""
import os
import uuid

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory

import face_swap
import meme_utils

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

for _d in (UPLOAD_DIR, OUTPUT_DIR, TEMPLATES_DIR):
    os.makedirs(_d, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _read_image(file_storage):
    data = np.frombuffer(file_storage.read(), np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解析图片，请上传 jpg/png/webp/bmp 格式")
    return img


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "swapper_ready": os.path.exists(face_swap.INSWAPPER_PATH)})


@app.route("/api/templates")
def list_templates():
    files = sorted(
        f for f in os.listdir(TEMPLATES_DIR)
        if os.path.splitext(f)[1].lower() in ALLOWED_EXT
    )
    return jsonify({"templates": files})


@app.route("/templates/<path:name>")
def get_template(name):
    return send_from_directory(TEMPLATES_DIR, name)


@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        if "source" not in request.files or not request.files["source"].filename:
            return jsonify({"error": "请先上传源照片（你的人脸）"}), 400
        source_img = _read_image(request.files["source"])

        target_img = None
        if "target" in request.files and request.files["target"].filename:
            target_img = _read_image(request.files["target"])
        else:
            template_name = request.form.get("template", "")
            if template_name:
                safe = os.path.basename(template_name)
                path = os.path.join(TEMPLATES_DIR, safe)
                if os.path.exists(path):
                    target_img = cv2.imread(path)

        if target_img is None:
            return jsonify({"error": "请上传目标表情包图片，或选择一个模板"}), 400

        top_text = (request.form.get("top_text") or "").strip()
        bottom_text = (request.form.get("bottom_text") or "").strip()

        result = face_swap.swap_face(source_img, target_img)

        if top_text or bottom_text:
            result = meme_utils.add_meme_text(result, top_text, bottom_text)

        out_name = f"{uuid.uuid4().hex}.png"
        out_path = os.path.join(OUTPUT_DIR, out_name)
        cv2.imwrite(out_path, result)

        return jsonify({"url": f"/output/{out_name}"})
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"处理失败：{exc}"}), 500


@app.route("/output/<path:name>")
def get_output(name):
    return send_from_directory(OUTPUT_DIR, name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8085, debug=True)
