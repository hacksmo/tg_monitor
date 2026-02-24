# 这个仓库本质上是一个“Telegram 投资情报自动化流水线”：

把群里的实时消息一自动筛选/分发定时 AI复盘写入Obsidian 结合行情触发短线简报。 

---

## 它在做什么（按流程）

### 1、启动后并行跑多个任务
main.py 会同时拉起：

Telegram 用户端监听（收消息）

多个 Bot 客户端（转发消息）

每 12 小时复盘任务

Longbridge 行情监控

每 15 分钟的 RSI 简报检查
这些都在异步/后台线程里并行，不互相阻塞。

### 2、多源监听 + 条件过滤
监听逻辑按 mapping 里的 sources 工作，支持按 group_id / topic_id / usernames 精确过滤，命中后调用分发。

### 3、分发到目标群（可选 Bark 推送）
命中的消息会用对应 Bot 发送到 target_chat_ids，超长消息自动分块；如果来源配置了 bark_on_message，会发手机 Bark 通知。

### 4、定时 AI 复盘（12h）
定时任务会拉历史消息，生成两类输出：

群聊全量总结（Summary）

大佬言论萃取（Alpha_Insights）
然后写入 Obsidian，并推送到指定 Telegram Topic。

### 5、Gemini 负责文本分析/生成
仓库内置两套 Prompt（全局总结、Alpha 萃取），并带模型回退与重试逻辑；另外还能生成“15 分钟异动投资建议简报”。

### 6、行情与短线触发

Longbridge 模块：订阅股票实时行情，突破/跌破阈值时 Bark 告警。

简报模块：拉 NVDA/SPY 15m K 线算 RSI，超买/超卖时结合最近大佬消息让 Gemini 生成简报并发到 Topic。

### 7、配置驱动（核心在 .secrets）

环境变量：Telegram/Gemini/代理/Bot/Bark/Obsidian/Longbridge 凭据。

mapping.yaml：定义监听来源、alpha 用户、股票阈值、RSI 阈值等。