"""文字叠加工具：经典表情包风格（黑字 + 白描边），自动换行，支持中文。"""
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_CACHE = {}


def _candidate_fonts():
    if os.name == "nt":
        return [
            r"C:\Windows\Fonts\simhei.ttf",    # 黑体（单文件，中文）
            r"C:\Windows\Fonts\msyhbd.ttc",    # 微软雅黑 粗体
            r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
            r"C:\Windows\Fonts\simsun.ttc",    # 宋体
            r"C:\Windows\Fonts\arialbd.ttf",   # Arial 粗体（英文）
            r"C:\Windows\Fonts\arial.ttf",
        ]
    if os.path.exists("/System/Library/Fonts"):
        return [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
    return [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]


def _load_font(size):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    font = None
    for path in _candidate_fonts():
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def _wrap_text(text, font, draw, max_width, stroke_width):
    """按最大宽度逐字换行。"""
    lines = []
    current = ""
    for ch in text:
        trial = current + ch
        bbox = draw.textbbox((0, 0), trial, font=font, stroke_width=stroke_width)
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_meme_text(pil_img, top_text="", bottom_text="", font_size=None):
    """在 PIL 图像上绘制上下文字（黑字白描边，居中，自动换行）。"""
    draw = ImageDraw.Draw(pil_img)
    w, h = pil_img.size
    if font_size is None:
        font_size = max(18, int(w * 0.07))
    font = _load_font(font_size)
    stroke = max(2, font_size // 12)
    max_width = int(w * 0.9)

    def draw_block(text, anchor):
        if not text:
            return
        lines = _wrap_text(text, font, draw, max_width, stroke)
        line_height = font_size + stroke * 2 + int(font_size * 0.25)
        total_h = line_height * len(lines)
        y0 = int(h * 0.03) if anchor == "top" else h - total_h - int(h * 0.03)
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2 - bbox[0]
            y = y0 + i * line_height
            draw.text(
                (x, y),
                line,
                font=font,
                fill=(0, 0, 0),
                stroke_width=stroke,
                stroke_fill=(255, 255, 255),
            )

    draw_block(top_text, "top")
    draw_block(bottom_text, "bottom")
    return pil_img


def add_meme_text(img_bgr, top_text="", bottom_text=""):
    """BGR 图像 -> 叠加文字 -> BGR 图像。"""
    pil_img = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    pil_img = draw_meme_text(pil_img, top_text, bottom_text)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
