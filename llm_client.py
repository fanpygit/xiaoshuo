"""OpenAI 兼容大模型 API 客户端：大纲生成 / 章节梗概 / 章节写作 / 连贯性检查。"""
import time

import requests

DEFAULT_TIMEOUT = 180
DEFAULT_MAX_TOKENS = 32768
_TEMP_MAP = {"low": 0.3, "medium": 0.6, "high": 0.9}


class LLMError(Exception):
    """调用大模型失败时抛出。"""


def _chat_completions_url(base_url):
    base = (base_url or "").rstrip("/")
    # 兼容用户直接填了 /v1 或 /chat/completions 的情况
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


SYSTEM_PROMPT = """你是一位资深的中文小说策划编辑与大纲写作专家。请根据用户提供的故事灵感与要求，撰写一份完整、专业、可直接用于创作的小说大纲。

请严格使用 Markdown 格式输出，并包含以下结构（用二级标题 ## 分隔各节）：

## 一、一句话简介
一句话概括整部小说的核心看点。

## 二、故事梗概
用 200～300 字概述故事整体走向（起因、发展、高潮、结局）。

## 三、核心人物
列出 3～6 个主要人物，每个用「- **姓名**：身份 + 性格 + 目标/动机」一行说明。

## 四、世界观设定
时代背景、力量体系/规则、重要势力或地理等设定要点。

## 五、主线剧情
按「开端 / 发展 / 转折 / 高潮 / 结局」分阶段，每个阶段 1～2 句话。

## 六、分卷分章大纲
按卷（若为长篇）或按章节，列出每一章/卷的标题与 1～2 句话情节梗概。

## 七、主题与立意
故事想表达的核心主题、情感内核。

## 八、可拓展方向
续作、番外或设定可挖掘的点。

要求：语言通顺、具体、可执行；如用户有体裁、篇幅、章节数、视角、风格等要求请严格遵守；篇幅要与用户要求相匹配；分卷分章部分要与所选篇幅及总章节数相匹配。"""


def build_user_prompt(prompt, options):
    parts = ["请根据以下要求生成小说大纲。", "", f"故事灵感 / 提示词：{prompt}"]
    labels = {
        "genre": "题材类型",
        "plot_tags": "情节标签",
        "length": "篇幅",
        "chapters": "总章节数",
        "pov": "叙事视角",
        "tone": "风格基调",
        "extra": "额外要求",
    }
    for key, label in labels.items():
        value = (options.get(key) or "").strip()
        if value:
            parts.append(f"{label}：{value}")
    parts.append("")
    parts.append("请直接输出大纲正文，不要输出与大纲无关的说明或客套话。")
    return "\n".join(parts)


def _chat(messages, cfg, temperature=0.8):
    """通用对话补全调用（带重试），返回文本内容。"""
    level = (cfg.get("thinking") or "").strip()
    if level in _TEMP_MAP:
        temperature = _TEMP_MAP[level]
    url = _chat_completions_url(cfg["base_url"])
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "max_tokens": DEFAULT_MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    last_err = ""
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.Timeout:
            last_err = "请求超时"
            time.sleep(2 * (attempt + 1))
            continue
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"网络请求失败：{exc}")

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                raise LLMError("API 返回了无法解析的内容")
            try:
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
            except (KeyError, IndexError, TypeError):
                raise LLMError("API 返回结构异常，未找到生成内容")
            if not content or not content.strip():
                # 思考模式下 content 可能为空，回退到 reasoning_content
                content = msg.get("reasoning_content") or ""
            if not content or not content.strip():
                raise LLMError("API 返回了空内容")
            return content.strip()

        # 提取错误信息
        detail = ""
        try:
            err = resp.json().get("error")
            if isinstance(err, dict):
                detail = err.get("message", "")
            if not detail:
                detail = resp.text[:300]
        except ValueError:
            detail = resp.text[:300]

        # 限流或服务端临时错误：重试
        if resp.status_code in (429, 500, 502, 503):
            last_err = f"HTTP {resp.status_code}：{detail}"
            time.sleep(3 * (attempt + 1))
            continue

        raise LLMError(f"API 返回错误（HTTP {resp.status_code}）：{detail}")

    raise LLMError(f"多次重试后仍失败：{last_err}")


def generate_outline(prompt, options, cfg):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(prompt, options)},
    ]
    return _chat(messages, cfg, temperature=0.8)


# ---------------- 章节梗概 ----------------

SYSTEM_PROMPT_CHAPTERS = """你是一位资深的中文小说编辑，擅长把小说大纲拆解为逐章的详细梗概。

请结合用户提供的小说大纲的总体内容（人物设定、世界观、主线剧情等），重点依据大纲中的「分卷分章大纲」部分来展开逐章梗概：必须忠实于大纲中已有的章节划分与剧情内容，沿用大纲中已有的章节标题，不得自行增删章节、不得改变剧情走向或人物设定，只在大纲基础上补充细节。

请严格使用 Markdown 输出，为大纲中的每一章单独列出：

## 第N章 章节标题
- **本章主线**：本章要推进的核心剧情（1～2 句话）
- **关键事件**：本章发生的具体事件（分点列出）
- **人物与冲突**：出场人物及其矛盾冲突
- **结尾钩子**：本章结尾留下的悬念或转折

要求：章数与用户要求的总章节数相匹配；若大纲中已有章节标题则沿用；每章梗概具体、可执行；前后章节之间要有因果关联和递进；只输出章节梗概正文，不要输出无关说明。"""


def build_chapters_prompt(outline, options, start=None, end=None):
    if start is not None and end is not None:
        head = f"请结合下面小说大纲的总体内容，重点依据其「分卷分章大纲」部分，只生成第{start}章到第{end}章的逐章详细梗概（不要偏离大纲的章节划分与剧情）。"
    else:
        head = "请结合下面小说大纲的总体内容，重点依据其「分卷分章大纲」部分，逐章生成详细梗概（不要偏离大纲的章节划分与剧情）。"
    parts = [head, "", "【小说大纲】", outline]
    if (options.get("chapters") or "").strip():
        parts.extend(["", f"总章节数：{options['chapters']}"])
    if (options.get("words") or "").strip():
        parts.append(f"每章梗概字数：约 {options['words']}")
    parts.extend(["", "请直接输出逐章梗概正文。"])
    return "\n".join(parts)


def expand_chapter_summaries(outline, options, cfg, start=None, end=None):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_CHAPTERS},
        {"role": "user", "content": build_chapters_prompt(outline, options, start, end)},
    ]
    return _chat(messages, cfg, temperature=0.7)


# ---------------- 章节写作 ----------------

SYSTEM_PROMPT_WRITE = """你是一位优秀的中文网络小说作家。请根据用户提供的故事梗概/大纲与章节上下文，完成指定章节的小说正文写作。

要求：
- 用流畅、有画面感的中文写正文，符合所选风格
- 严格遵循章节字数要求（如有）
- 保持与前文设定、人物性格、剧情逻辑一致
- 若有「前文正文」，请严格衔接其结尾的时间、地点、人物状态，保持时序与逻辑一致
- 章节要有起承转合，结尾留适当悬念
- 如有参考网文作者写作风格或风格样例，请尽量模仿其用词、句式、节奏与叙事特点
- 只输出该章节的正文内容，不要输出与正文无关的说明"""


def build_write_prompt(outline, options):
    chapter = (options.get("chapter") or "").strip() or "下一章"
    parts = ["请完成下面指定章节的小说写作。", "", "【故事梗概 / 大纲】", outline]
    if (options.get("context") or "").strip():
        parts.extend(["", "【前后章节梗概（用于保持连贯）】", options["context"]])
    if (options.get("prev_content") or "").strip():
        parts.extend(["", "【前文正文（已写章节，用于衔接，请保持时序、地点、逻辑一致）】", options["prev_content"]])
    parts.extend(["", f"【本次要写的章节】{chapter}"])
    if (options.get("words") or "").strip():
        parts.append(f"章节字数要求：约 {options['words']}")
    if (options.get("tone") or "").strip():
        parts.append(f"风格基调：{options['tone']}")
    if (options.get("pov") or "").strip():
        parts.append(f"叙事视角：{options['pov']}")
    if (options.get("author") or "").strip():
        parts.append(f"参考网文作者写作风格：{options['author']}")
    if (options.get("style_sample") or "").strip():
        parts.extend(["", "【参考风格样例（请模仿其用词、句式与节奏）】", options["style_sample"]])
    if (options.get("requirement") or "").strip():
        parts.append(f"写作要求：{options['requirement']}")
    parts.extend(["", "请直接输出本章节正文。"])
    return "\n".join(parts)


def write_chapter(outline, options, cfg):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_WRITE},
        {"role": "user", "content": build_write_prompt(outline, options)},
    ]
    return _chat(messages, cfg, temperature=0.85)


# ---------------- 连贯性检查 ----------------

SYSTEM_PROMPT_COHERENCE = """你是一位严谨的小说审校编辑，专门检查小说多个章节之间的整体连贯性。

请按章节顺序对比用户提供的若干章节内容，整体检查以下方面：
1. 剧情逻辑：事件因果是否连贯，有无矛盾或漏洞
2. 人物一致性：人物性格、身份、能力、关系是否前后一致
3. 时间线：时间、地点、场景切换是否合理
4. 设定一致性：世界观、力量体系、道具等设定是否一致
5. 伏笔与呼应：前文伏笔是否有遗漏或未交代

请用 Markdown 输出一份连贯性检查报告：
## 一、总体评价
## 二、发现的问题
每个问题独占一行，严格使用「数字. 问题描述」格式（例如「1. 第3章与第2章人物性格不一致」）；若没有问题，只写「无」。
## 三、修改建议
## 四、需要补写或过渡的内容

只输出检查报告，不要输出无关说明。"""


def build_coherence_prompt(chapters):
    parts = ["请检查下面这些章节内容的整体连贯性。", ""]
    for name, content in chapters:
        parts.extend([f"【{name}】", content, ""])
    parts.append("请输出连贯性检查报告。")
    return "\n".join(parts)


def check_coherence(chapters, cfg):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_COHERENCE},
        {"role": "user", "content": build_coherence_prompt(chapters)},
    ]
    return _chat(messages, cfg, temperature=0.4)


# ---------------- 结合检查（梗概 + 正文） ----------------

SYSTEM_PROMPT_COHERENCE_COMBINED = """你是一位严谨的小说审校编辑。请对比每章的「章节梗概」与「正文内容」，检查以下方面：

1. 梗概与正文一致性：正文是否忠实实现了梗概中的情节、人物、事件，有无偏离、矛盾或遗漏
2. 剧情逻辑：各章之间事件因果是否连贯，有无矛盾或漏洞
3. 人物一致性：人物性格、身份、能力、关系在梗概与正文、以及各章之间是否一致
4. 时间线：时间、地点、场景切换是否合理
5. 设定一致性：世界观、力量体系、道具等设定是否一致

请用 Markdown 输出检查报告：
## 一、总体评价
## 二、发现的问题
每个问题独占一行，严格使用「数字. 问题描述」格式；若没有问题，只写「无」。
## 三、修改建议
## 四、需要补写或过渡的内容

只输出检查报告，不要输出无关说明。"""


def build_coherence_combined_prompt(chapters):
    parts = ["请结合每章的章节梗概与正文内容，检查一致性与连贯性。", ""]
    for name, summary, content in chapters:
        parts.extend([f"【{name}】", f"章节梗概：{summary}", f"正文内容：{content}", ""])
    parts.append("请输出检查报告。")
    return "\n".join(parts)


def check_coherence_combined(chapters, cfg):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_COHERENCE_COMBINED},
        {"role": "user", "content": build_coherence_combined_prompt(chapters)},
    ]
    return _chat(messages, cfg, temperature=0.4)


# ---------------- 连贯性修复 ----------------

SYSTEM_PROMPT_FIX = """你是一位严谨的小说编辑。请根据用户指出的连贯性问题，修复各章节内容。

要求：
- 严格按用户给出的章节标题和顺序，逐个输出修复后的章节内容
- 每个章节用「【章节标题】」独占一行作为分隔标记，标记后紧跟该章节修复后的完整内容
- 只修改与问题相关的部分，尽量保持其余内容不变
- 章节标题必须与原文完全一致"""


def build_fix_prompt(chapters, issues):
    parts = ["请修复以下章节中的连贯性问题。", "", "【需要修复的问题】"]
    for i, issue in enumerate(issues, 1):
        parts.append(f"{i}. {issue}")
    parts.extend(["", "【各章节内容】"])
    for name, content in chapters:
        parts.extend([f"【{name}】", content, ""])
    parts.extend(["", "请逐个输出修复后的章节内容（用【章节标题】标记分隔）。"])
    return "\n".join(parts)


def fix_coherence(chapters, issues, cfg):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_FIX},
        {"role": "user", "content": build_fix_prompt(chapters, issues)},
    ]
    return _chat(messages, cfg, temperature=0.3)


# ---------------- 文笔润色 ----------------

SYSTEM_PROMPT_POLISH = """你是一位优秀的中文小说编辑，擅长文笔润色。请在保持原意、情节、人物、对白、设定不变的前提下，对章节正文进行文笔润色，使语言更生动流畅、更有画面感和感染力。

要求：
- 保持情节、人物、对白、设定等核心内容不变，只优化文字表达
- 严格按原章节标题和顺序，逐个输出润色后的完整正文
- 每个章节用「【章节标题】」独占一行作为分隔标记，标记后紧跟该章节润色后的完整内容
- 章节标题必须与原文完全一致"""


def build_polish_prompt(chapters, style):
    parts = ["请对以下章节正文进行文笔润色。", ""]
    if (style or "").strip():
        parts.extend([f"润色要求：{style.strip()}", ""])
    parts.append("【各章节内容】")
    for name, content in chapters:
        parts.extend([f"【{name}】", content, ""])
    parts.append("请逐个输出润色后的章节内容（用【章节标题】标记分隔）。")
    return "\n".join(parts)


def polish_chapters(chapters, style, cfg):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_POLISH},
        {"role": "user", "content": build_polish_prompt(chapters, style)},
    ]
    return _chat(messages, cfg, temperature=0.7)
