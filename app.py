"""小说大纲生成器 Web 服务（Flask）。

根据用户提示 + 设置，调用 OpenAI 兼容的大模型 API（DeepSeek / OpenAI / Moonshot 等），
生成结构化的中文小说大纲。

接口:
    GET  /                前端页面
    GET  /api/health      健康检查
    GET  /api/config      读取当前 API 配置（API Key 打码）
    POST /api/config      保存 API 配置（base_url / api_key / model）
    POST /api/generate    根据提示生成小说大纲
"""
import io
import json
import os
import re
import time

from flask import Flask, jsonify, request, send_file, send_from_directory

import docx_export
import llm_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SUMMARY_SUFFIX = "章节梗概"
CONTENT_SUFFIX = "章节正文"

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


def _default_config():
    """默认配置，优先读取环境变量，其次使用 DeepSeek 默认值。"""
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
        "save_dir": os.environ.get("LLM_SAVE_DIR", os.path.join(BASE_DIR, "novels")),
        "thinking": os.environ.get("LLM_THINKING", ""),
    }


def _load_config():
    cfg = _default_config()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for key in ("base_url", "api_key", "model", "save_dir", "thinking"):
                    if saved.get(key):
                        cfg[key] = saved[key]
        except (OSError, ValueError):
            pass
    return cfg


def _save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _mask(key):
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _to_text(value):
    """把前端可能传来的字符串或列表统一转为顿号分隔的文本。"""
    if isinstance(value, list):
        return "、".join(str(v).strip() for v in value if str(v).strip())
    return (value or "").strip()


def _resolve_config(data):
    """合并请求里的临时配置到已保存配置。"""
    cfg = _load_config()
    if data.get("base_url"):
        cfg["base_url"] = data["base_url"].strip().rstrip("/")
    if data.get("model"):
        cfg["model"] = data["model"].strip()
    if data.get("api_key") and "*" not in data["api_key"]:
        cfg["api_key"] = data["api_key"].strip()
    # 思考强度：始终以请求为准（可为空=默认）
    cfg["thinking"] = (data.get("thinking") or "").strip()
    return cfg


def _safe_name(name):
    """把小说名称转为安全的文件名（去除非法字符）。"""
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", str(name or "").strip())
    name = name.strip().strip(".")
    return name or "未命名"


def _get_save_dir(cfg):
    """返回保存目录（不存在则创建）。"""
    save_dir = (cfg.get("save_dir") or "").strip() or os.path.join(BASE_DIR, "novels")
    os.makedirs(save_dir, exist_ok=True)
    return save_dir


_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_num(s):
    """简单汉字数字（一~九十九）转整数，失败返回 None。"""
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    if s == "十":
        return 10
    if s.startswith("十") and len(s) == 2 and s[1] in _CN_DIGITS:
        return 10 + _CN_DIGITS[s[1]]
    if s.endswith("十") and len(s) == 2 and s[0] in _CN_DIGITS:
        return _CN_DIGITS[s[0]] * 10
    return None


def _parse_chapter_count(outline, chapters_text):
    """尽量确定总章节数：优先用户输入的数字，其次解析大纲中的章节标记（含范围）。"""
    m = re.match(r"^\s*(\d+)\s*章?\s*$", chapters_text or "")
    if m:
        return int(m.group(1))

    nums = []
    # 单个章节标记：第1章 / 第500章（分卷「第X卷」不计入）
    nums.extend(int(x) for x in re.findall(r"第\s*(\d+)\s*[章节集]", outline or ""))
    # 范围标记：第 1～10 章 / 第451~500章 / 第451-500章 / 第451至500章
    nums.extend(int(x) for x in re.findall(r"第\s*\d+\s*[～~—至\-]\s*(\d+)\s*章", outline or ""))
    # 中文数字：第一章 / 第十一章（分卷「第X卷」不计入）
    for x in re.findall(r"第\s*([一二三四五六七八九十]+)\s*[章节集]", outline or ""):
        n = _cn_num(x)
        if n:
            nums.append(n)
    return max(nums) if nums else None


def _split_chapters(md):
    """把章节梗概 markdown 按「## 第N章」标题拆成 [(标题, 内容), ...]，分卷标题不计入。"""
    lines = (md or "").replace("\r\n", "\n").split("\n")
    chapters = []
    cur = None
    head_re = re.compile(r"^#{1,4}\s*第\s*[0-9一二三四五六七八九十百]+\s*[章节集]")
    volume_re = re.compile(r"^#{1,4}\s*第\s*[0-9一二三四五六七八九十百]+\s*卷")
    for line in lines:
        if head_re.match(line):
            if cur is not None:
                chapters.append(cur)
            cur = [line]
        elif volume_re.match(line):
            # 分卷标题：跳过，不计入章节梗概
            continue
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        chapters.append(cur)
    result = []
    for block in chapters:
        title = block[0].lstrip("#").strip()
        result.append((title, "\n".join(block).strip()))
    return result


def _chapter_sort_key(fname):
    m = re.search(r"第\s*(\d+)", fname)
    if m:
        return (0, int(m.group(1)), fname)
    m2 = re.search(r"第\s*([一二三四五六七八九十]+)", fname)
    if m2:
        n = _cn_num(m2.group(1))
        if n:
            return (0, n, fname)
    return (1, 0, fname)


def _max_chapter_in_folder(folder):
    """返回文件夹内已有章节文件的最大章节号（无则 0）。"""
    if not os.path.isdir(folder):
        return 0
    nums = []
    for f in os.listdir(folder):
        if not f.endswith(".md"):
            continue
        m = re.search(r"第\s*(\d+)", f)
        if m:
            nums.append(int(m.group(1)))
            continue
        m2 = re.search(r"第\s*([一二三四五六七八九十]+)", f)
        if m2:
            n = _cn_num(m2.group(1))
            if n:
                nums.append(n)
    return max(nums) if nums else 0


def _chapter_range_label(filenames):
    """从文件名列表提取章节范围标签（如「第1-5章」）。"""
    nums = []
    for f in filenames:
        m = re.search(r"第\s*(\d+)", f)
        if m:
            nums.append(int(m.group(1)))
    if not nums:
        return "章节"
    lo, hi = min(nums), max(nums)
    return f"第{lo}-{hi}章" if lo != hi else f"第{lo}章"


def _split_fixed(md):
    """把修复结果按「【章节标题】」标记拆成 [(标题, 内容), ...]。"""
    lines = (md or "").replace("\r\n", "\n").split("\n")
    result = []
    cur_title = None
    cur_lines = []
    for line in lines:
        m = re.match(r"^【(.+?)】\s*$", line.strip())
        if m:
            if cur_title is not None:
                result.append((cur_title, "\n".join(cur_lines).strip()))
            cur_title = m.group(1).strip()
            cur_lines = []
        else:
            if cur_title is not None:
                cur_lines.append(line)
    if cur_title is not None:
        result.append((cur_title, "\n".join(cur_lines).strip()))
    return result


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/health")
def health():
    cfg = _load_config()
    return jsonify({
        "ok": True,
        "api_key_set": bool(cfg["api_key"]),
        "model": cfg["model"],
    })


@app.route("/api/config", methods=["GET"])
def get_config():
    cfg = _load_config()
    return jsonify({
        "base_url": cfg["base_url"],
        "api_key": _mask(cfg["api_key"]),
        "model": cfg["model"],
        "save_dir": cfg["save_dir"],
        "thinking": cfg["thinking"],
        "api_key_set": bool(cfg["api_key"]),
    })


@app.route("/api/config", methods=["POST"])
def set_config():
    data = request.get_json(silent=True) or {}
    cfg = _load_config()

    base_url = (data.get("base_url") or "").strip().rstrip("/")
    model = (data.get("model") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    save_dir = (data.get("save_dir") or "").strip()

    if base_url:
        cfg["base_url"] = base_url
    if model:
        cfg["model"] = model
    if save_dir:
        cfg["save_dir"] = save_dir
    cfg["thinking"] = (data.get("thinking") or "").strip()
    # 仅当用户提交了新的、非打码的 API Key 时才覆盖
    if api_key and "*" not in api_key:
        cfg["api_key"] = api_key

    _save_config(cfg)
    return jsonify({"ok": True, "api_key_set": bool(cfg["api_key"])})


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "请先填写故事灵感 / 提示词"}), 400

    cfg = _resolve_config(data)
    if not cfg["api_key"]:
        return jsonify({"error": "尚未配置 API Key，请先展开「API 设置」填写并保存"}), 400

    options = {
        "genre": _to_text(data.get("genre")),
        "plot_tags": _to_text(data.get("plot_tags")),
        "length": _to_text(data.get("length")),
        "chapters": _to_text(data.get("chapters")),
        "pov": _to_text(data.get("pov")),
        "tone": _to_text(data.get("tone")),
        "extra": _to_text(data.get("extra")),
    }

    novel_name = (data.get("novel_name") or "").strip()

    try:
        content = llm_client.generate_outline(prompt, options, cfg)
    except llm_client.LLMError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"生成失败：{exc}"}), 500

    saved_path = None
    if novel_name:
        safe = _safe_name(novel_name)
        saved_path = os.path.join(_get_save_dir(cfg), safe + ".md")
        try:
            with open(saved_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            return jsonify({"error": f"保存失败：{exc}"}), 500

    return jsonify({"ok": True, "outline": content, "saved_path": saved_path})


@app.route("/api/novels")
def list_novels():
    """列出保存目录下的小说大纲文件（按名称）。"""
    cfg = _load_config()
    save_dir = _get_save_dir(cfg)
    files = sorted(
        f[:-3] for f in os.listdir(save_dir)
        if f.endswith(".md")
        and not f.endswith(SUMMARY_SUFFIX + ".md")
        and os.path.isfile(os.path.join(save_dir, f))
    )
    return jsonify({"save_dir": save_dir, "novels": files})


@app.route("/api/novels/<name>")
def get_novel(name):
    """读取指定名称的小说大纲文件内容。"""
    cfg = _load_config()
    safe = _safe_name(name)
    path = os.path.join(_get_save_dir(cfg), safe + ".md")
    if not os.path.exists(path):
        return jsonify({"error": "未找到该小说的大纲文件"}), 404
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({"name": safe, "content": content})


@app.route("/api/summaries")
def list_summaries():
    """列出已保存的章节梗概文件夹（按小说名）。"""
    cfg = _load_config()
    save_dir = _get_save_dir(cfg)
    names = sorted(
        d[:-(len(SUMMARY_SUFFIX))] for d in os.listdir(save_dir)
        if d.endswith(SUMMARY_SUFFIX) and os.path.isdir(os.path.join(save_dir, d))
    )
    return jsonify({"save_dir": save_dir, "summaries": names})


@app.route("/api/summaries/<name>")
def get_summary(name):
    """读取指定小说的章节梗概文件夹内容（按章节顺序合并所有文件）。"""
    cfg = _load_config()
    safe = _safe_name(name)
    folder = os.path.join(_get_save_dir(cfg), safe + SUMMARY_SUFFIX)
    if not os.path.isdir(folder):
        return jsonify({"error": "未找到该小说的章节梗概文件夹"}), 404
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".md")],
        key=_chapter_sort_key,
    )
    parts = []
    for f in files:
        with open(os.path.join(folder, f), "r", encoding="utf-8") as fh:
            parts.append(fh.read().strip())
    return jsonify({"name": safe, "content": "\n\n".join(parts), "files": files})


@app.route("/api/summaries/<name>/chapters")
def list_summary_chapters(name):
    """列出某小说章节梗概文件夹内的章节文件。"""
    cfg = _load_config()
    safe = _safe_name(name)
    folder = os.path.join(_get_save_dir(cfg), safe + SUMMARY_SUFFIX)
    if not os.path.isdir(folder):
        return jsonify({"error": "未找到该小说的章节梗概文件夹"}), 404
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".md")],
        key=_chapter_sort_key,
    )
    return jsonify({"name": safe, "chapters": files})


@app.route("/api/summaries/<name>/chapter/<fname>")
def get_summary_chapter(name, fname):
    """读取某小说章节梗概文件夹内的单个章节文件。"""
    cfg = _load_config()
    safe = _safe_name(name)
    folder = os.path.join(_get_save_dir(cfg), safe + SUMMARY_SUFFIX)
    path = os.path.join(folder, os.path.basename(fname))
    if not os.path.exists(path):
        return jsonify({"error": "未找到该章节梗概文件"}), 404
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({"name": safe, "filename": fname, "content": content})


@app.route("/api/expand-chapters", methods=["POST"])
def expand_chapters():
    """根据大纲展开逐章梗概：超长时自动分批，按每章独立文件保存到小说文件夹。"""
    data = request.get_json(silent=True) or {}
    outline = (data.get("outline") or "").strip()
    if not outline:
        return jsonify({"error": "请先粘贴小说大纲"}), 400

    cfg = _resolve_config(data)
    if not cfg["api_key"]:
        return jsonify({"error": "尚未配置 API Key，请先展开「API 设置」填写并保存"}), 400

    options = {
        "chapters": _to_text(data.get("chapters")),
        "words": _to_text(data.get("words")),
    }
    novel_name = (data.get("novel_name") or "").strip()

    total = _parse_chapter_count(outline, options["chapters"])
    batch_size = 10

    # 提前创建保存文件夹（若需要），并准备文件名去重集合
    folder_path = None
    seen = set()
    if novel_name:
        safe = _safe_name(novel_name)
        folder_path = os.path.join(_get_save_dir(cfg), safe + SUMMARY_SUFFIX)
        os.makedirs(folder_path, exist_ok=True)

    # 断点续传：若文件夹内已有章节文件，从其最大章节号之后接续生成
    start_from = 1
    if folder_path and os.path.isdir(folder_path):
        done = _max_chapter_in_folder(folder_path)
        if done > 0:
            start_from = done + 1
            for f in os.listdir(folder_path):
                if f.endswith(".md"):
                    seen.add(f[:-3])
    resumed = start_from > 1

    def _write_chapters(chapters, saved_files):
        """把一批章节立即写入文件夹。"""
        for title, block in chapters:
            base = _safe_name(title) or "未命名"
            fname = base
            i = 2
            while fname in seen:
                fname = f"{base}_{i}"
                i += 1
            seen.add(fname)
            with open(os.path.join(folder_path, fname + ".md"), "w", encoding="utf-8") as f:
                f.write(block)
            saved_files.append(fname)

    combined_parts = []
    saved_files = []
    batch_count = 0

    try:
        if total and total > batch_size:
            for start in range(start_from, total + 1, batch_size):
                end = min(start + batch_size - 1, total)
                batch_count += 1
                content = llm_client.expand_chapter_summaries(outline, options, cfg, start=start, end=end)
                chapters = _split_chapters(content)
                combined_parts.extend(block for _, block in chapters)
                if folder_path:
                    _write_chapters(chapters, saved_files)
        else:
            content = llm_client.expand_chapter_summaries(outline, options, cfg)
            chapters = _split_chapters(content)
            combined_parts.extend(block for _, block in chapters)
            if folder_path:
                _write_chapters(chapters, saved_files)
    except llm_client.LLMError as exc:
        app.logger.error("expand-chapters 失败（本次已保存 %s 章）: %s", len(saved_files), exc)
        return jsonify({
            "error": f"{exc}（本次已保存 {len(saved_files)} 章，重试将自动接续）",
            "saved_files": saved_files,
        }), 502
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("expand-chapters 异常")
        return jsonify({"error": f"生成失败：{exc}"}), 500

    chapter_count = len(combined_parts)
    total_in_folder = 0
    if folder_path:
        total_in_folder = len([f for f in os.listdir(folder_path) if f.endswith(".md")])

    content = "\n\n".join(combined_parts)
    if resumed and chapter_count == 0:
        message = f"所有章节已生成完毕（共 {total_in_folder} 章）"
        content = message
    elif resumed:
        message = f"已接续生成 {chapter_count} 章，累计 {total_in_folder} 章"
    else:
        message = f"已保存 {chapter_count} 章到：{folder_path}" if folder_path else f"已生成 {chapter_count} 章"

    return jsonify({
        "ok": True,
        "content": content,
        "folder_path": folder_path,
        "saved_files": saved_files,
        "batch_count": batch_count,
        "chapter_count": chapter_count,
        "resumed": resumed,
        "message": message,
    })


@app.route("/api/write-chapter", methods=["POST"])
def write_chapter():
    """根据章节梗概完成章节正文写作，并保存到小说「章节正文」文件夹。"""
    data = request.get_json(silent=True) or {}
    outline = (data.get("outline") or "").strip()
    if not outline:
        return jsonify({"error": "请先读取或填写故事梗概 / 大纲"}), 400

    cfg = _resolve_config(data)
    if not cfg["api_key"]:
        return jsonify({"error": "尚未配置 API Key，请先展开「API 设置」填写并保存"}), 400

    options = {
        "chapter": _to_text(data.get("chapter")),
        "context": _to_text(data.get("context")),
        "words": _to_text(data.get("words")),
        "tone": _to_text(data.get("tone")),
        "pov": _to_text(data.get("pov")),
        "author": _to_text(data.get("author")),
        "style_sample": _to_text(data.get("style_sample")),
        "requirement": _to_text(data.get("requirement")),
        "prev_content": _to_text(data.get("prev_content")),
    }
    novel_name = (data.get("novel_name") or "").strip()

    try:
        content = llm_client.write_chapter(outline, options, cfg)
    except llm_client.LLMError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"生成失败：{exc}"}), 500

    saved_path = None
    if novel_name:
        safe_novel = _safe_name(novel_name)
        folder = os.path.join(_get_save_dir(cfg), safe_novel + CONTENT_SUFFIX)
        os.makedirs(folder, exist_ok=True)
        chapter = (options.get("chapter") or "未命名章节").strip()
        saved_path = os.path.join(folder, _safe_name(chapter) + ".md")
        try:
            with open(saved_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            return jsonify({"error": f"保存失败：{exc}"}), 500

    return jsonify({"ok": True, "content": content, "saved_path": saved_path})


@app.route("/api/contents")
def list_contents():
    """列出已保存章节正文文件夹的小说（按小说名）。"""
    cfg = _load_config()
    save_dir = _get_save_dir(cfg)
    names = sorted(
        d[:-(len(CONTENT_SUFFIX))] for d in os.listdir(save_dir)
        if d.endswith(CONTENT_SUFFIX) and os.path.isdir(os.path.join(save_dir, d))
    )
    return jsonify({"save_dir": save_dir, "contents": names})


@app.route("/api/contents/<name>/chapters")
def list_content_chapters(name):
    """列出某小说章节正文文件夹内的章节文件。"""
    cfg = _load_config()
    safe = _safe_name(name)
    folder = os.path.join(_get_save_dir(cfg), safe + CONTENT_SUFFIX)
    if not os.path.isdir(folder):
        return jsonify({"error": "未找到该小说的章节正文文件夹"}), 404
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".md")],
        key=_chapter_sort_key,
    )
    return jsonify({"name": safe, "chapters": files})


@app.route("/api/contents/<name>/chapter/<fname>")
def get_content_chapter(name, fname):
    """读取某小说章节正文文件夹内的单个章节文件。"""
    cfg = _load_config()
    safe = _safe_name(name)
    folder = os.path.join(_get_save_dir(cfg), safe + CONTENT_SUFFIX)
    path = os.path.join(folder, os.path.basename(fname))
    if not os.path.exists(path):
        return jsonify({"error": "未找到该章节正文文件"}), 404
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({"name": safe, "filename": fname, "content": content})


@app.route("/api/combined")
def list_combined():
    """列出同时有章节梗概和章节正文的小说。"""
    cfg = _load_config()
    save_dir = _get_save_dir(cfg)
    summary_dirs = {d[:-(len(SUMMARY_SUFFIX))] for d in os.listdir(save_dir) if d.endswith(SUMMARY_SUFFIX) and os.path.isdir(os.path.join(save_dir, d))}
    content_dirs = {d[:-(len(CONTENT_SUFFIX))] for d in os.listdir(save_dir) if d.endswith(CONTENT_SUFFIX) and os.path.isdir(os.path.join(save_dir, d))}
    names = sorted(summary_dirs & content_dirs)
    return jsonify({"save_dir": save_dir, "combined": names})


@app.route("/api/combined/<name>/chapters")
def list_combined_chapters(name):
    """列出同时存在梗概与正文的章节文件。"""
    cfg = _load_config()
    safe = _safe_name(name)
    save_dir = _get_save_dir(cfg)
    summary_folder = os.path.join(save_dir, safe + SUMMARY_SUFFIX)
    content_folder = os.path.join(save_dir, safe + CONTENT_SUFFIX)
    summary_files = {f for f in os.listdir(summary_folder) if f.endswith(".md")} if os.path.isdir(summary_folder) else set()
    content_files = {f for f in os.listdir(content_folder) if f.endswith(".md")} if os.path.isdir(content_folder) else set()
    files = sorted(summary_files & content_files, key=_chapter_sort_key)
    return jsonify({"name": safe, "chapters": files})


@app.route("/api/check-coherence", methods=["POST"])
def check_coherence():
    """选择一批次章节，整体检查连贯性（支持梗概/正文/结合检查）。"""
    data = request.get_json(silent=True) or {}
    novel_name = (data.get("novel_name") or "").strip()
    chapters = data.get("chapters") or []
    kind = (data.get("kind") or "content").strip()

    cfg = _resolve_config(data)
    if not cfg["api_key"]:
        return jsonify({"error": "尚未配置 API Key，请先展开「API 设置」填写并保存"}), 400

    safe_novel = _safe_name(novel_name)
    save_dir = _get_save_dir(cfg)

    chapter_items = []
    if kind == "combined":
        if not novel_name or not chapters:
            return jsonify({"error": "请先选择小说和章节"}), 400
        summary_folder = os.path.join(save_dir, safe_novel + SUMMARY_SUFFIX)
        content_folder = os.path.join(save_dir, safe_novel + CONTENT_SUFFIX)
        for fname in chapters:
            base = os.path.basename(fname)
            summary = content = ""
            sp = os.path.join(summary_folder, base)
            cp = os.path.join(content_folder, base)
            if os.path.exists(sp):
                with open(sp, "r", encoding="utf-8") as f:
                    summary = f.read().strip()
            if os.path.exists(cp):
                with open(cp, "r", encoding="utf-8") as f:
                    content = f.read().strip()
            if summary or content:
                chapter_items.append((os.path.splitext(base)[0], summary, content))
    elif novel_name and chapters:
        suffix = SUMMARY_SUFFIX if kind == "summary" else CONTENT_SUFFIX
        folder_label = "章节梗概" if kind == "summary" else "章节正文"
        folder = os.path.join(save_dir, safe_novel + suffix)
        if not os.path.isdir(folder):
            return jsonify({"error": f"未找到该小说的{folder_label}文件夹"}), 404
        for fname in chapters:
            path = os.path.join(folder, os.path.basename(fname))
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    chapter_items.append((os.path.splitext(os.path.basename(fname))[0], f.read().strip()))
    else:
        # 兼容旧的直接传内容方式
        before = (data.get("before") or "").strip()
        after = (data.get("after") or "").strip()
        if before and after:
            chapter_items = [("前章内容", before), ("后章内容", after)]

    if not chapter_items:
        return jsonify({"error": "请选择要检查的章节"}), 400

    try:
        if kind == "combined":
            content = llm_client.check_coherence_combined(chapter_items, cfg)
        else:
            content = llm_client.check_coherence(chapter_items, cfg)
        return jsonify({"ok": True, "content": content})
    except llm_client.LLMError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"检查失败：{exc}"}), 500


@app.route("/api/fix-coherence", methods=["POST"])
def fix_coherence():
    """选择性修复连贯性问题，并覆盖原文件内容。"""
    data = request.get_json(silent=True) or {}
    novel_name = (data.get("novel_name") or "").strip()
    chapters = data.get("chapters") or []
    issues = data.get("issues") or []
    kind = (data.get("kind") or "content").strip()

    cfg = _resolve_config(data)
    if not cfg["api_key"]:
        return jsonify({"error": "尚未配置 API Key，请先展开「API 设置」填写并保存"}), 400
    if not issues:
        return jsonify({"error": "请选择要修复的问题"}), 400
    if not novel_name or not chapters:
        return jsonify({"error": "请先选择小说和章节"}), 400

    suffix = SUMMARY_SUFFIX if kind == "summary" else CONTENT_SUFFIX
    folder = os.path.join(_get_save_dir(cfg), _safe_name(novel_name) + suffix)
    if not os.path.isdir(folder):
        return jsonify({"error": "未找到该小说的章节文件夹"}), 404

    chapter_items = []
    title_to_file = {}
    for fname in chapters:
        path = os.path.join(folder, os.path.basename(fname))
        if os.path.exists(path):
            title = os.path.splitext(os.path.basename(fname))[0]
            with open(path, "r", encoding="utf-8") as f:
                chapter_items.append((title, f.read()))
            title_to_file[title] = os.path.basename(fname)

    if not chapter_items:
        return jsonify({"error": "未读取到章节内容"}), 400

    try:
        fixed_content = llm_client.fix_coherence(chapter_items, issues, cfg)
    except llm_client.LLMError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"修复失败：{exc}"}), 500

    overwritten = []
    for title, content in _split_fixed(fixed_content):
        if title in title_to_file:
            try:
                with open(os.path.join(folder, title_to_file[title]), "w", encoding="utf-8") as f:
                    f.write(content)
                overwritten.append(title_to_file[title])
            except OSError as exc:
                return jsonify({"error": f"保存失败：{exc}"}), 500

    if not overwritten:
        return jsonify({"error": "修复结果未能匹配到章节文件"}), 500

    return jsonify({
        "ok": True,
        "content": fixed_content,
        "overwritten": overwritten,
        "message": f"已修复并覆盖 {len(overwritten)} 个章节，可重新检验连贯性",
    })


@app.route("/api/save-issues", methods=["POST"])
def save_issues():
    """把未修复的问题整理成文档，保存到「小说名+章节+问题」文件夹。"""
    data = request.get_json(silent=True) or {}
    novel_name = (data.get("novel_name") or "").strip()
    chapters = data.get("chapters") or []
    issues = data.get("issues") or []
    kind = (data.get("kind") or "content").strip()

    if not issues:
        return jsonify({"error": "没有要保存的问题"}), 400
    if not novel_name:
        return jsonify({"error": "缺少小说名称"}), 400

    range_label = _chapter_range_label(chapters)
    folder_name = _safe_name(novel_name) + range_label + "问题"
    folder = os.path.join(_get_save_dir(_load_config()), folder_name)
    os.makedirs(folder, exist_ok=True)

    kind_label = "章节梗概" if kind == "summary" else "章节正文"
    ts = time.strftime("%Y%m%d_%H%M%S")
    lines = [
        "# 问题清单",
        "",
        f"- 小说：{novel_name}",
        f"- 章节范围：{range_label}",
        f"- 类型：{kind_label}",
        f"- 保存时间：{ts}",
        "",
        "## 未修复的问题",
        "",
    ]
    for i, issue in enumerate(issues, 1):
        lines.append(f"{i}. {issue}")
    doc = "\n".join(lines)

    path = os.path.join(folder, f"问题清单_{ts}.md")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc)
    except OSError as exc:
        return jsonify({"error": f"保存失败：{exc}"}), 500

    return jsonify({
        "ok": True,
        "content": doc,
        "saved_path": path,
        "message": f"已保存问题文档到：{folder}",
    })


@app.route("/api/polish-chapters", methods=["POST"])
def polish_chapters():
    """对选中的章节正文进行文笔润色，并覆盖原文件。"""
    data = request.get_json(silent=True) or {}
    novel_name = (data.get("novel_name") or "").strip()
    chapters = data.get("chapters") or []
    style = (data.get("style") or "").strip()

    cfg = _resolve_config(data)
    if not cfg["api_key"]:
        return jsonify({"error": "尚未配置 API Key，请先展开「API 设置」填写并保存"}), 400
    if not novel_name or not chapters:
        return jsonify({"error": "请先选择小说和章节"}), 400

    folder = os.path.join(_get_save_dir(cfg), _safe_name(novel_name) + CONTENT_SUFFIX)
    if not os.path.isdir(folder):
        return jsonify({"error": "未找到该小说的章节正文文件夹"}), 404

    chapter_items = []
    title_to_file = {}
    for fname in chapters:
        path = os.path.join(folder, os.path.basename(fname))
        if os.path.exists(path):
            title = os.path.splitext(os.path.basename(fname))[0]
            with open(path, "r", encoding="utf-8") as f:
                chapter_items.append((title, f.read()))
            title_to_file[title] = os.path.basename(fname)

    if not chapter_items:
        return jsonify({"error": "未读取到章节内容"}), 400

    try:
        polished_content = llm_client.polish_chapters(chapter_items, style, cfg)
    except llm_client.LLMError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"润色失败：{exc}"}), 500

    overwritten = []
    for title, content in _split_fixed(polished_content):
        if title in title_to_file:
            try:
                with open(os.path.join(folder, title_to_file[title]), "w", encoding="utf-8") as f:
                    f.write(content)
                overwritten.append(title_to_file[title])
            except OSError as exc:
                return jsonify({"error": f"保存失败：{exc}"}), 500

    if not overwritten:
        return jsonify({"error": "润色结果未能匹配到章节文件"}), 500

    return jsonify({
        "ok": True,
        "content": polished_content,
        "overwritten": overwritten,
        "message": f"已润色并覆盖 {len(overwritten)} 个章节",
    })


@app.route("/api/export", methods=["POST"])
def export_docx():
    """把 Markdown 大纲导出为 Word (.docx) 文件。"""
    data = request.get_json(silent=True) or {}
    outline = (data.get("outline") or "").strip()
    if not outline:
        return jsonify({"error": "没有可导出的内容"}), 400

    title = (data.get("title") or "小说大纲").strip() or "小说大纲"

    try:
        doc = docx_export.markdown_to_docx(outline, title=title)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name=f"{title}.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"导出失败：{exc}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8086, debug=True)
