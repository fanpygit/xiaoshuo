"""下载 insightface 的 buffalo_l 人脸检测模型到本地（从 ModelScope 镜像）。

因为国内访问 GitHub 不稳定，insightface 首次运行自动下载 buffalo_l 会失败，
这里从 ModelScope 镜像下载并放到 insightface 默认的模型目录。

用法:
    python download_buffalo_l.py
"""
import os
import sys

INSIGHTFACE_ROOT = os.path.join(os.path.expanduser("~"), ".insightface", "models")
BUFFALO_L_DIR = os.path.join(INSIGHTFACE_ROOT, "buffalo_l")

BASE_URL = "https://modelscope.cn/models/zhangjin/inswapper/resolve/master/models/buffalo_l"
FILES = ["det_10g.onnx", "w600k_r50.onnx", "2d106det.onnx", "1k3d68.onnx", "genderage.onnx"]


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
                    print(
                        f"\r  {os.path.basename(dest)} {done // (1024 * 1024)}/{total // (1024 * 1024)} MB",
                        end="",
                    )
        print()


def main():
    os.makedirs(BUFFALO_L_DIR, exist_ok=True)
    for name in FILES:
        dest = os.path.join(BUFFALO_L_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"{name} 已存在，跳过")
            continue
        print(f"下载 {name} ...")
        try:
            download(f"{BASE_URL}/{name}", dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  失败: {exc}")
            sys.exit(1)
    print(f"\n完成。buffalo_l 已就绪：{BUFFALO_L_DIR}")


if __name__ == "__main__":
    main()
