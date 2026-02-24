# Telegram 智能情报系统

多源监听、多 Bot 分发、Gemini 复盘、Obsidian 沉淀、Longbridge 行情与 15 分钟异动简报。从「流式信息」到「结构化财富知识」。

---

## (a) 快速上手指南

### 环境

- Python 3.10+（推荐 3.12，兼容 3.14）
- 代理：v2rayN 等，默认 10808 端口（可在配置中修改）

### 配置步骤

1. **克隆/进入项目**
   ```bash
   cd /path/to/tg
   ```

2. **创建隐藏配置目录**
   ```bash
   mkdir -p .secrets
   ```

3. **环境变量**
   - 复制示例：`cp config/config.env.example .secrets/config.env`
   - 编辑 `.secrets/config.env`，必填：
     - `API_ID`、`API_HASH`（[my.telegram.org](https://my.telegram.org) 申请）
     - `GEMINI_API_KEY`（[Google AI Studio](https://aistudio.google.com/apikey)）
   - 选填：`BARK_KEY`、`BOT_1_TOKEN`/`BOT_2_TOKEN`、`OBSIDIAN_VAULT`、`LONGBRIDGE_*`、`BRIEF_TARGET_CHAT_ID` 等

4. **多源与分发矩阵**
   - 复制：`cp config/mapping.example.yaml .secrets/mapping.yaml`
   - 按需修改 `sources`（群组 ID、话题 ID、大佬 usernames、Bot、目标群组、是否 Bark）

5. **安装依赖与运行**
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
   首次运行会要求 Telegram 登录（手机号、验证码），session 会保存在 `.secrets/` 或项目根。

---

## (b) Gemini 深度复盘提示词说明

系统使用两段核心 Prompt，均可在代码中调整（`src/gemini_service.py`）。

### 1. 全局群聊总结（Summaries）

- **用途**：对指定时间范围内群内全部消息做复盘，输出交易准则、操作逻辑、异动提醒。
- **核心 Prompt 要点**：
  - 角色：美股交易丰富的交易员
  - 输入：Telegram 群组消息（时间、发言人、内容）
  - 输出结构：
    - **【交易准则】**：下单/卖出/加仓逻辑，如何找股票背后逻辑，过滤闲聊
    - **【操作逻辑】**：入场/止损理由（技术面、基本面、风控点）
    - **【异动提醒】**：冷门股或涨幅好的标的及原因
  - 格式：Markdown、多用 Emoji、适合手机端阅读

### 2. 大佬言论深度萃取（Alpha_Insights）

- **用途**：仅针对配置的「大佬」发言做深度提炼，便于检索与决策。
- **核心 Prompt 要点**：
  - 角色：资深美股交易员与情报分析师
  - 输出结构：
    - **核心观点提炼**：3～5 条 bullet，共识/分歧
    - **逻辑与依据**：技术面/基本面/宏观，含标的与逻辑链
    - **标的与操作建议**：具体标的、仓位与止损止盈思路
    - **风险与注意**：大佬提到的风险点

两段 Prompt 的完整文本见 `src/gemini_service.py` 中的 `PROMPT_GLOBAL_SUMMARY` 与 `PROMPT_ALPHA_INSIGHTS`。

---

## (c) 多 Bot 配置（@BotFather）

1. 打开 Telegram，搜索 **@BotFather**。
2. 发送 `/newbot`，按提示设置名称与 username（如 `MyAlphaBot`）。
3. 获得 **Token**（形如 `123456:ABC-DEF...`），复制。
4. 在 `.secrets/config.env` 中新增一行，例如：`BOT_1_TOKEN=123456:ABC-DEF...`。
5. 若需多个 Bot（不同群组用不同 Bot 转发），重复 2～4，使用 `BOT_2_TOKEN` 等。
6. 在 `.secrets/mapping.yaml` 的每个 source 下：
   - `bot_token_env_key: BOT_1_TOKEN`（或 `BOT_2_TOKEN`）
   - `target_chat_ids: [-1001234567890]`（要把 Bot 拉进目标群组，并填该群组 ID）
7. 将对应 Bot 以成员身份加入目标群组，确保有发消息权限。

获取群组 ID：将 [@userinfobot](https://t.me/userinfobot) 拉进群或转发一条群消息给该 Bot 查看。

---

## (d) 项目愿景

- **问题**：信息过载、群聊噪音大、优质观点易被淹没。
- **目标**：从「流信息」到「结构化财富知识」：
  - **多源聚合**：同时监控 N 个频道/群组及指定话题。
  - **AI 复盘**：定时（如 12 小时）用 Gemini 做全局总结与大佬观点萃取。
  - **Obsidian 沉淀**：总结与 Alpha 自动写入本地 Markdown，带 YAML 与目录分级，便于检索。
  - **股票异动与简报**：Longbridge 监控价格阈值并 Bark；15 分钟级别 RSI 超买/超卖时，结合大佬言论生成《15min 异动投资建议简报》并推送到群。

---

## (e) Obsidian 联动进阶：Dataview 今日 Alpha

写入的 Markdown 均带 YAML frontmatter，例如：

```yaml
---
date: 2026-02-07 14:30
source: 金银铜派大星
tags:
  - 复盘
  - 交易准则
  - 异动
---
```

在 Obsidian 中安装 **Dataview** 插件后，可在仪表盘或任意笔记中插入「今日 Alpha」查询：

```dataview
TABLE date, source
FROM "Trading_Intelligence/Alpha_Insights"
WHERE date(today) <= date(date)
SORT date DESC
LIMIT 20
```

或按关键词筛选：

```dataview
LIST
FROM "Trading_Intelligence/Alpha_Insights"
WHERE contains(tags, "Alpha")
SORT file.mtime DESC
```

库路径由 `.secrets/config.env` 中的 `OBSIDIAN_VAULT` 指定；子目录固定为 `Trading_Intelligence/Summaries` 与 `Trading_Intelligence/Alpha_Insights`。

---

## 目录结构

```
tg/
├── .secrets/           # 敏感配置（不提交）
│   ├── config.env
│   └── mapping.yaml
├── config/
│   ├── config.env.example
│   └── mapping.example.yaml
├── src/
│   ├── config_loader.py
│   ├── telegram_listener.py
│   ├── distribution.py
│   ├── gemini_service.py
│   ├── obsidian_writer.py
│   ├── bark_notifier.py
│   ├── longbridge_monitor.py
│   ├── investment_brief.py
│   ├── tasks.py
│   ├── telegram_fetch.py
│   └── mapping_loader.py
├── main.py
├── requirements.txt
└── README.md
```

---

## 隐私与 Git

- 所有敏感配置请仅放在 `.secrets/` 下；`.gitignore` 已包含 `.secrets/`、`*.session`、`*.log`、`__pycache__/`、`.DS_Store` 等，避免误提交到 GitHub。
