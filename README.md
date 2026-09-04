# 📚 小说写作助手

一个**本地运行**的 Web 应用：围绕小说创作全流程，提供四大工具——
**大纲生成、逐章梗概、章节写作、连贯性检查**，调用在线大模型（DeepSeek / OpenAI / Moonshot 等 OpenAI 兼容接口）。

## 功能

- **📚 大纲生成**：根据提示词生成结构化小说大纲（一句话简介、梗概、人物、世界观、主线、分卷分章、主题、拓展方向）
- **📑 章节梗概**：结合大纲总体内容、按「分卷分章大纲」展开逐章主线梗概（本章主线 / 关键事件 / 人物冲突 / 结尾钩子）；支持从保存路径读取大纲，按小说名创建文件夹、每章独立文件保存，超长时自动分批生成
- **✍️ 章节写作**：支持从保存路径选择章节梗概文件作为写作上下文
- **✍️ 章节写作**：根据故事梗概与前后章节上下文完成指定章节正文，支持**章节字数限制**
- **🔗 连贯性检查**：对比前后章节，检查剧情、人物、时间线、设定、伏笔的一致性并给出修改建议
- 支持题材（下拉多选，按拼音首字母排序）/ 情节标签（下拉多选，按拼音首字母排序）/ 篇幅 / 总章节数 / 叙事视角 / 风格基调 / 额外要求等选项
- **大纲文件化保存**：生成时填写「小说名称」，自动按名称保存为 `.md` 文件到可配置的保存路径
- 支持任意 OpenAI 兼容接口，默认 DeepSeek，可切换 OpenAI、Moonshot、Kimi 等
- 前端自动渲染 Markdown，支持「复制 Markdown」「下载 .md」「导出 Word(.docx)」
- API Key 保存在本机 `config.json`（已加入 `.gitignore`），也可通过环境变量配置

## 环境要求

- Python 3.10+
- 一个可用的在线大模型 API Key（DeepSeek / OpenAI 等）

## 快速开始

```bash
# 1. 安装依赖（建议使用国内镜像）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 2. 启动服务
python app.py
```

浏览器打开 http://127.0.0.1:8086

### 配置 API Key（任选其一）

**方式一：网页内填写**（推荐）

点击页面顶部「⚙️ API 设置」，填写 Base URL、模型名称、API Key，点「保存设置到本机」。

**方式二：环境变量**

```bash
# PowerShell
$env:LLM_API_KEY="sk-xxx"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-chat"
python app.py
```

常见默认值：

| 服务 | Base URL | 模型示例 |
|------|----------|----------|
| DeepSeek | https://api.deepseek.com | deepseek-v4-flash / deepseek-v4-pro |
| OpenAI | https://api.openai.com | gpt-4o-mini |
| Moonshot(Kimi) | https://api.moonshot.cn | moonshot-v1-8k |

## 使用步骤

1. 展开「API 设置」，配置并保存 API Key
2. 在「📚 大纲生成」填写故事灵感（并填写小说名称），生成并保存大纲
3. 在「📑 章节梗概」从保存路径读取大纲文件（或手动粘贴），展开逐章主线梗概
4. 在「✍️ 章节写作」粘贴梗概/上下文，设置章节字数，完成章节正文写作
5. 在「🔗 连贯性检查」粘贴前后章节，检查一致性
6. 结果支持复制 Markdown / 下载 `.md` / 导出 Word

## 目录结构

```
xiaoshuo/
├── app.py            # Flask 后端 + 接口
├── llm_client.py     # OpenAI 兼容大模型客户端 + 四类提示词模板
├── docx_export.py    # Markdown 转 Word(.docx) 导出
├── requirements.txt
├── config.json       # 本地保存的 API 配置（运行后生成，勿提交）
├── static/           # 前端页面
│   ├── index.html
│   ├── app.js        # 含轻量 Markdown 渲染器
│   └── style.css
└── README.md
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| GET | `/api/health` | 健康检查（含是否已配置 Key） |
| GET | `/api/config` | 读取当前配置（Key 打码，含 `save_dir`） |
| GET | `/api/novels` | 列出保存路径下的已保存小说（大纲文件） |
| GET | `/api/novels/<name>` | 读取指定小说的大纲文件内容 |
| GET | `/api/summaries` | 列出已保存的章节梗概文件 |
| GET | `/api/summaries/<name>` | 读取指定小说的章节梗概文件内容 |
| POST | `/api/config` | 保存配置 `{base_url, api_key, model}` |
| POST | `/api/generate` | 生成大纲，JSON：`{prompt, genre, length, chapters, pov, tone, extra, ...}` |
| POST | `/api/expand-chapters` | 逐章梗概，JSON：`{outline, chapters, words, ...}` |
| POST | `/api/write-chapter` | 章节写作，JSON：`{outline, context, chapter, words, tone, pov, ...}` |
| POST | `/api/check-coherence` | 连贯性检查，JSON：`{before, after, ...}` |
| POST | `/api/export` | 导出 Word，JSON：`{outline, title}`，返回 `.docx` 文件 |

> 以上接口均可附带 `base_url`、`model`、`api_key` 以临时覆盖服务端配置。

## 已知限制 / 后续计划

- 生成质量取决于所选用的大模型能力
- 章节写作当前为「单章生成」，暂不支持整本批量续写
- 后续可扩展：多轮追问式细化、导出 PDF、保存历史、按章节自动批量续写
