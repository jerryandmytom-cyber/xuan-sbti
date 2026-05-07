# SBTI Mini App — Telegram Web 应用

## 文件结构

```
xuanvip_miniapp/
├── index.html      # 主页面（HTML + Telegram WebApp SDK）
├── styles.css       # 样式（含暗色主题 + 动画）
├── questions.js     # 题库 + 结果计算逻辑
├── app.js           # 应用主逻辑（状态管理 + 交互）
└── README.md        # 本文件
```

## 部署步骤

### 方式一：GitHub Pages（免费，推荐）

1. 创建 GitHub 仓库，将以上4个文件推送上去
2. 进入仓库 → Settings → Pages → Source: `main` branch → Save
3. 等待部署完成，获得 `https://你的用户名.github.io/仓库名/` URL
4. 用 @BotFather 配置 Bot：`/setappname` → 选择你的 Bot → 填入 URL

### 方式二：Cloudflare Pages（免费 + 更快）

1. 创建 GitHub 仓库
2. 连接到 Cloudflare Pages，选择仓库，Build command 留空
3. 输出目录 `/`
4. 获得 URL 后在 @BotFather 配置

## 与 Python Bot 联动

当前设计为**纯前端版本**，所有逻辑（随机抽题、得分、结果计算）均在 Mini App 内完成。
结果不传回 Bot，Bot 保持独立运行。

如需结果传回 Bot，可在 `app.js` 的 `shareResult()` 中通过
`Telegram.WebApp.sendData(JSON.stringify(result))` 将数据传回。

## 配置 Bot

在 @BotFather：
```
/newbot 或 选择已有 Bot
/setappname → 填入 Mini App 名称
```

在代码中替换 `YourBotUsername` 为实际 Bot 用户名（index.html 中的链接）。

## 开发预览

直接用浏览器打开 `index.html` 即可预览（Telegram SDK 在浏览器中会降级处理，不会影响调试）。

## 外观自定义

- 修改 `styles.css` 中的 CSS 变量可改主题色
- `questions.js` 中题库与 Python 版 `xuanvip_SBTI.py` 保持同步（15题）
- `app.js` 中 `updateBotButton()` 可配置 Bot 回调按钮