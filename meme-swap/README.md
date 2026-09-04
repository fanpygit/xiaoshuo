# 表情包换脸 · 第一版（MVP）

一个**本地优先**的「换脸表情包」Web 应用：上传你的人脸照片 + 一个含人脸的表情包图片，
用 InsightFace 把人脸换过去，再叠加经典的黑字白描边文字。

> 第一版只做「换脸 + 模板 + 文字」三件事，不包含云端推理 / 提示词驱动生成（那是后续阶段）。

## 功能

- 人脸交换：InsightFace `inswapper_128.onnx`
- 模板：把表情包图片放进 `templates/` 目录即可在网页下拉框选择
- 文字：上/下排文字叠加，黑字白描边，自动换行，支持中文
- 全部本地运行，图片不出本机

## 环境要求

- Python 3.10+（在 3.12 验证通过）
- 首次运行需联网（自动下载人脸检测模型 + 换脸模型，合计约 1 GB）
- 依赖已固定 `scikit-image>=0.26` / `scipy>=1.14`，以兼容 numpy 2.x（否则会报 `numpy.dtype size changed`）

## 国内网络加速（可选）

直连 PyPI 可能超时，可用清华镜像：

```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载模型（换脸 + 人脸检测，共约 900 MB，只需一次）
python download_models.py        # inswapper_128.onnx 换脸模型
python download_buffalo_l.py     # buffalo_l 人脸检测模型

# 3. 启动服务
python app.py
```

浏览器打开 http://127.0.0.1:8085

> 模型默认从 ModelScope（魔搭）国内镜像下载；GitHub/HuggingFace 访问不稳时脚本会自动回退重试。

## 使用步骤

1. 上传一张你的正面清晰照片（源照片）
2. 选择一个模板，或上传一张含人脸的表情包图片（目标图）
3. （可选）填写上排/下排文字
4. 点击「生成表情包」，下载结果

## 目录结构

```
meme-swap/
├── app.py               # Flask 后端 + 接口
├── face_swap.py         # InsightFace 换脸核心
├── meme_utils.py        # 文字叠加工具
├── download_models.py   # 下载换脸模型 inswapper_128.onnx
├── download_buffalo_l.py # 下载人脸检测模型 buffalo_l
├── requirements.txt
├── models/              # 换脸模型 inswapper_128.onnx（下载后）
├── templates/           # 内置模板图片（自己放）
├── static/              # 前端页面
├── uploads/             # 运行时上传缓存
└── output/              # 生成结果
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| GET | `/api/health` | 健康检查（含换脸模型是否就绪） |
| GET | `/api/templates` | 列出模板 |
| POST | `/api/generate` | `multipart/form-data`：`source`(必填)、`target` 或 `template`(二选一)、`top_text`、`bottom_text` |

## ⚠️ 授权与合规提示

- InsightFace 提供的预训练模型（含 `inswapper_128.onnx`）**仅供非商业研究用途**，
  若要商用，请自行更换/获取可商用的换脸模型。
- 换脸涉及人脸等敏感个人信息，正式发布前需遵守《个人信息保护法》、
  《互联网信息服务深度合成管理规定》等要求：取得用户单独同意、为合成内容添加标识、
  提供举报与删除机制，并避免用于冒用他人肖像。

## 已知限制 / 后续计划

- 目前只替换图中「最大的一张脸」，多人脸/多目标后续再支持
- 后续阶段：提示词驱动的风格生成（Stable Diffusion + InstantID/PhotoMaker）、
  更多内置模板、移动端 App
