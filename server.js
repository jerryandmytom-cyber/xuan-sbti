const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    next();
});

// 服务 public 目录（SBTI纯前端应用）
app.use(express.static(path.join(__dirname, 'public')));

// 首页
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 健康检查
app.get('/health', (req, res) => {
    res.json({ status: 'ok', service: 'SBTI 2026 Mini App' });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`🔮 SBTI 2026 疯狂指数测试 Mini App`);
    console.log(`🌐 运行中: http://localhost:${PORT}`);
    console.log(`🚀 部署模式: Render`);
});