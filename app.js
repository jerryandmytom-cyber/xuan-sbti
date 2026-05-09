/**
 * SBTI Mini App - Main Application Logic
 */

let tg = null;
let user = null;
let currentQuestions = [];
let currentStep = 0;
let scores = { apathy: 0, ego: 0, chaos: 0, grind: 0, vibe: 0, lore: 0 };

// ── 初始化 ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        user = tg.initDataUnsafe?.user;
    }

    // 闪屏延迟
    setTimeout(() => {
        const splash = document.getElementById('splash');
        splash.classList.add('fade-out');
        setTimeout(() => {
            splash.classList.add('gone');
            showPage('home');
        }, 600);
    }, 1500);

    // 按钮事件
    document.getElementById('start-btn').addEventListener('click', startTest);
    document.getElementById('retest-btn').addEventListener('click', startTest);
    document.getElementById('share-btn').addEventListener('click', shareResult);
});

// ── 页面切换 ────────────────────────────────────
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('visible'));
    const el = document.getElementById(pageId);
    if (el) el.classList.add('visible');
    // 等待 visibility 过渡完成后（400ms）再滚动，确保元素已渲染
    setTimeout(() => {
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
        document.documentElement.scrollTop = 0;
        document.body.scrollTop = 0;
    }, 450);
    if (tg) {
        tg.expand();
    }
}

// ── 开始测试 ────────────────────────────────────
function startTest() {
    scores = { apathy: 0, ego: 0, chaos: 0, grind: 0, vibe: 0, lore: 0 };
    currentStep = 0;
    currentQuestions = window.SBTIData?.getRandomQuestions(6) || [];
    showPage('quiz');
    renderQuestion();
}

// ── 渲染题目 ────────────────────────────────────
function renderQuestion() {
    const q = currentQuestions[currentStep];
    if (!q) return showResult();

    const stepLabel = document.getElementById('step-label');
    const aiBadge = document.getElementById('ai-badge');
    const questionText = document.getElementById('question-text');
    const optionsEl = document.getElementById('options');
    const progressFill = document.getElementById('progress-fill');

    const total = currentQuestions.length;
    stepLabel.textContent = `第 ${currentStep + 1}/${total} 题`;

    // AI badge：第4题开始显示动态题标记
    if (currentStep >= 3) {
        aiBadge.classList.remove('hidden');
    } else {
        aiBadge.classList.add('hidden');
    }

    // 进度条
    progressFill.style.width = `${((currentStep) / total) * 100}%`;

    questionText.textContent = q.text;

    optionsEl.innerHTML = '';
    q.options.forEach((opt, idx) => {
        const btn = document.createElement('button');
        btn.className = 'option-btn';
        btn.innerHTML = `<span class="option-number">${idx + 1}</span><span>${opt.text}</span>`;
        btn.addEventListener('click', () => selectOption(idx));
        optionsEl.appendChild(btn);
    });
}

// ── 选择选项 ────────────────────────────────────
function selectOption(idx) {
    const q = currentQuestions[currentStep];
    const opt = q.options[idx];

    // 累加得分
    if (opt.score) {
        for (const [dim, pts] of Object.entries(opt.score)) {
            scores[dim] = (scores[dim] || 0) + pts;
        }
    }

    // 视觉反馈
    const btns = document.querySelectorAll('.option-btn');
    btns.forEach((b, i) => {
        if (i === idx) b.classList.add('selected');
        b.style.pointerEvents = 'none';
    });

    // 下一题（延迟让用户看到选择效果）
    setTimeout(() => {
        currentStep++;
        if (currentStep >= currentQuestions.length) {
            showResult();
        } else {
            renderQuestion();
        }
    }, 400);
}

// ── 显示结果 ────────────────────────────────────
function showResult() {
    const name = user?.first_name || '测试者';
    const result = window.SBTIData?.buildResult(name, scores);
    if (!result) return;

    document.getElementById('result-icon').textContent = result.dimInfo.emoji;
    document.getElementById('result-badge-cn').textContent = `【${result.titleCn}】`;
    document.getElementById('result-badge-en').textContent = `[${result.titleEn}]`;
    document.getElementById('result-user').textContent = `${name} 的专属档案`;
    document.getElementById('diagnosis-text').textContent = result.diagnosis;

    // 渲染得分条
    const barsEl = document.getElementById('score-bars');
    barsEl.innerHTML = '';
    result.bars.forEach((bar, i) => {
        const item = document.createElement('div');
        item.className = 'score-bar-item';
        item.innerHTML = `
            <span class="score-bar-emoji">${bar.emoji}</span>
            <span class="score-bar-label">${bar.cn}</span>
            <div class="score-bar-track">
                <div class="score-bar-fill" style="width:${bar.pct * 10}%;background:${bar.color};"></div>
            </div>
            <span class="score-bar-value">${bar.val}pt</span>
        `;
        item.style.animationDelay = `${i * 0.1}s`;
        barsEl.appendChild(item);
    });

    showPage('result');
}

// ── 导出图片 ────────────────────────────────────
function exportResultImage() {
    const name = user?.first_name || '测试者';
    const result = window.SBTIData?.buildResult(name, scores);
    if (!result) return;

    const canvas = document.createElement('canvas');
    canvas.width = 800;
    canvas.height = 1200;
    const ctx = canvas.getContext('2d');

    // 背景
    const grad = ctx.createLinearGradient(0, 0, 0, 1200);
    grad.addColorStop(0, '#0a0a1a');
    grad.addColorStop(1, '#12122a');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 800, 1200);

    // 顶部装饰线
    ctx.fillStyle = '#6c5ce7';
    ctx.fillRect(0, 0, 800, 6);

    // 标题
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 42px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('🧬 SBTI 2026 疯狂指数个性测试', 400, 80);

    // 分隔线
    ctx.strokeStyle = '#6c5ce7';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(80, 110);
    ctx.lineTo(720, 110);
    ctx.stroke();

    // 卡片背景
    roundRect(ctx, 40, 140, 720, 340, 20);
    ctx.fillStyle = 'rgba(26,26,58,0.9)';
    ctx.fill();
    ctx.strokeStyle = '#6c5ce7';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // 结果 emoji
    ctx.font = '80px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(result.dimInfo.emoji, 400, 240);

    // 结果类型徽章
    ctx.font = 'bold 32px sans-serif';
    ctx.fillStyle = '#6c5ce7';
    ctx.fillText(`【${result.titleCn}】`, 400, 310);

    // 英文类型
    ctx.font = '20px sans-serif';
    ctx.fillStyle = '#888';
    ctx.fillText(`[${result.titleEn}]`, 400, 350);

    // 用户名
    ctx.font = '22px sans-serif';
    ctx.fillStyle = '#aaa';
    ctx.fillText(`${name} 的专属档案`, 400, 400);

    // 核心维度
    ctx.font = '18px sans-serif';
    ctx.fillStyle = '#6c5ce7';
    ctx.fillText(`核心维度：${result.dimInfo.emoji} ${result.dimInfo.cn}（${result.dimInfo.en}）`, 400, 440);

    // 雷达区背景
    roundRect(ctx, 40, 500, 720, 420, 20);
    ctx.fillStyle = 'rgba(26,26,58,0.9)';
    ctx.fill();

    // 雷达标题
    ctx.fillStyle = '#888';
    ctx.font = '18px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('📊 六维雷达数据', 70, 540);

    // 得分条
    result.bars.forEach((bar, i) => {
        const y = 570 + i * 60;
        // emoji
        ctx.font = '24px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(bar.emoji, 70, y + 8);
        // 标签
        ctx.font = '18px sans-serif';
        ctx.fillStyle = '#bbb';
        ctx.fillText(bar.cn, 115, y + 8);
        // 进度条背景
        roundRect(ctx, 280, y - 8, 350, 24, 12);
        ctx.fillStyle = 'rgba(255,255,255,0.1)';
        ctx.fill();
        // 进度条填充（使用百分制映射，bar.pct是0-100）
        const barWidth = Math.max(Math.round((bar.pct / 100) * 350), 8);
        roundRect(ctx, 280, y - 8, barWidth, 24, 12);
        ctx.fillStyle = bar.color;
        ctx.fill();
        // 数值
        ctx.fillStyle = '#888';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(`${bar.val}pt`, 720, y + 8);
    });

    // AI诊断区背景
    roundRect(ctx, 40, 940, 720, 140, 20);
    ctx.fillStyle = 'rgba(26,26,58,0.9)';
    ctx.fill();

    // AI诊断标题
    ctx.fillStyle = '#888';
    ctx.font = '18px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('🧠 AI 诊断报告', 70, 975);

    // 诊断内容
    ctx.font = '20px sans-serif';
    ctx.fillStyle = '#eee';
    ctx.fillText(result.diagnosis, 70, 1010, 660);

    // 底部
    ctx.fillStyle = '#6c5ce7';
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('@EasternMysteryBot · #SBTI2026 #疯狂指数', 400, 1140);
    ctx.fillStyle = '#444';
    ctx.font = '14px sans-serif';
    ctx.fillText('Powered by 玄学大师 × SBTI 2026', 400, 1170);

    // 下载
    const link = document.createElement('a');
    link.download = `SBTI_${name}_2026.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
    if (tg) tg.HapticFeedback.impactOccurred('medium');
}

// 圆角矩形辅助
function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

// ── 分享结果 ────────────────────────────────────
async function shareResult() {
    const name = user?.first_name || '测试者';
    const result = window.SBTIData?.buildResult(name, scores);
    if (!result) {
        if (tg) tg.showAlert('结果数据未找到，请重试');
        return;
    }

    // 先确保结果页可见
    const resultPage = document.getElementById('result');
    const resultCard = resultPage?.querySelector('.result-card');
    if (!resultCard) {
        if (tg) tg.showAlert('结果页面未找到');
        return;
    }

    if (tg) tg.HapticFeedback.impactOccurred('light');

    try {
        const canvas = await html2canvas(resultCard, {
            backgroundColor: '#0a0a1a',
            scale: 2,
            useCORS: true,
            logging: false,
            allowTaint: true,
            foreignObjectRendering: false,
        });

        const dataUrl = canvas.toDataURL('image/png');

        if (tg && navigator.share) {
            // 尝试带图片分享
            try {
                const blob = await (await fetch(dataUrl)).blob();
                const file = new File([blob], `SBTI_${name}_2026.png`, { type: 'image/png' });
                await navigator.share({
                    files: [file],
                    text: `🧬 SBTI 2026 疯狂指数测试\n\n👤 ${name} 的专属档案\n\n🏷️ 【${result.titleCn}】${result.dimInfo.emoji}\n\n🧠 ${result.diagnosis}\n\n#SBTI2026 #疯狂指数`,
                });
                return;
            } catch {
                // 文件分享不支持，降级为纯文字
            }
            // 纯文字分享
            try {
                await navigator.share({
                    text: `🧬 SBTI 2026 疯狂指数测试\n\n👤 ${name} 的专属档案\n\n🏷️ 【${result.titleCn}】${result.dimInfo.emoji} ${result.dimInfo.cn}\n\n🧠 ${result.diagnosis}\n\n#SBTI2026 #疯狂指数`,
                });
                return;
            } catch (e) {
                // 用户取消或不支持，走下载
            }
        }

        // 降级：下载图片
        const link = document.createElement('a');
        link.download = `SBTI_${name}_2026.png`;
        link.href = dataUrl;
        link.click();
        if (tg) tg.HapticFeedback.impactOccurred('medium');

    } catch (e) {
        console.error('shareResult error:', e);
        if (tg) tg.showAlert('截图失败，请检查网络后重试');
    }
}

// ── 更新 Bot 按钮 ───────────────────────────────
function updateBotButton() {
    if (tg && tg.MainButton) {
        tg.MainButton.setText('返回玄学大师Bot');
        tg.MainButton.onClick(() => {
            window.location.href = `https://t.me/${tg.initDataUnsafe?.bot?.username || 'EasternMysteryBot'}`;
        });
        tg.MainButton.show();
    }
}