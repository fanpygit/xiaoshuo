"""核心换脸模块：使用 InsightFace 的 inswapper_128.onnx 做人脸交换。

- 人脸检测/关键点/识别：insightface.app.FaceAnalysis（buffalo_l 模型包，首次运行自动下载）
- 换脸：insightface.model_zoo.INSwapper（inswapper_128.onnx）

注意：InsightFace 提供的预训练模型（含换脸模型）仅供非商业研究用途，商用需自行解决授权。
"""
import os

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
INSWAPPER_PATH = os.path.join(MODELS_DIR, "inswapper_128.onnx")

_face_app = None
_swapper = None


def _face_area(face):
    bbox = face.bbox
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def _largest_face(faces):
    return max(faces, key=_face_area)


def get_face_app():
    """懒加载人脸分析器（检测 + 关键点 + 识别）。"""
    global _face_app
    if _face_app is None:
        from insightface.app import FaceAnalysis

        _face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _face_app.prepare(ctx_id=0, det_size=(640, 640))
    return _face_app


def get_swapper():
    """懒加载换脸模型。缺失时给出明确提示，引导用户运行 download_models.py。"""
    global _swapper
    if _swapper is None:
        if not os.path.exists(INSWAPPER_PATH):
            raise FileNotFoundError(
                "未找到换脸模型 inswapper_128.onnx，请先运行: python download_models.py"
            )
        from insightface.model_zoo import get_model

        _swapper = get_model(INSWAPPER_PATH, download=False, download_zip=False)
    return _swapper


def swap_face(source_bgr, target_bgr):
    """把 source 里的人脸换到 target 的人脸上。

    参数:
        source_bgr: OpenCV BGR 图像（提供人脸身份的照片）
        target_bgr: OpenCV BGR 图像（要被替换人脸的目标图/表情包模板）

    返回:
        换脸后的 BGR 图像
    """
    app = get_face_app()
    swapper = get_swapper()

    source_faces = app.get(source_bgr)
    if not source_faces:
        raise ValueError("源照片中未检测到人脸，请换一张更清晰的正脸照")

    target_faces = app.get(target_bgr)
    if not target_faces:
        raise ValueError("目标图中未检测到人脸，请换一个含人脸的表情包/图片")

    source_face = _largest_face(source_faces)
    target_face = _largest_face(target_faces)

    result = swapper.get(target_bgr, target_face, source_face, paste_back=True)
    return result
