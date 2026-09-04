"""下载换脸模型 inswapper_128.onnx 到 models/ 目录。

insightface 的人脸检测模型（buffalo_l）会在首次运行时自动下载，
无需手动处理；本脚本只负责下载换脸模型 inswapper_128.onnx。

用法:
    python download_models.py
"""
import os
import sys

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
TARGET = os.path.join(MODELS_DIR, "inswapper_128.onnx")

# 多个候选下载地址（按顺序尝试，任何一个成功即可）
# ModelScope（魔搭）为国内镜像，优先使用；GitHub/HuggingFace 作为备用
URLS = [
    "https://modelscope.cn/models/chwshuang/inswapper_128.onnx/resolve/master/inswapper_128.onnx",
    "https://modelscope.cn/models/zhangjin/inswapper/resolve/master/inswapper_128.onnx",
    "https://hf-mirror.com/datasets/Gourieff/ReActor/resolve/main/models/inswapper_128.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v0.7/inswapper_128.onnx",
    "https://huggingface.co/datasets/Gourieff/ReActor/resolve/main/models/inswapper_128.onnx",
]


def download(url, dest):
    import requests

    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(
                        f"\r  下载中 {done // (1024 * 1024)}/{total // (1024 * 1024)} MB ({pct}%)",
                        end="",
                    )
        print()


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    if os.path.exists(TARGET) and os.path.getsize(TARGET) > 100 * 1024 * 1024:
        print(f"模型已存在：{TARGET}")
        return

    print(f"开始下载换脸模型 inswapper_128.onnx（约 530 MB）到 {TARGET}")
    last_err = None
    for url in URLS:
        print(f"尝试: {url}")
        try:
            download(url, TARGET)
            print(f"下载完成：{TARGET} ({os.path.getsize(TARGET) // (1024 * 1024)} MB)")
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  失败: {exc}")
    print("\n所有地址下载失败，请手动下载 inswapper_128.onnx 并放到 models/ 目录。")
    print(f"手动下载后可放置到: {TARGET}")
    if last_err:
        print(f"最后错误: {last_err}")
    sys.exit(1)


if __name__ == "__main__":
    main()
