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
        
        // 隐藏 Telegram 原生加载界面
        const hideSplash = () => {
            const splash = document.querySelector('tg-splash-screen');
            if (splash) {
                splash.style.cssText = 'display: none !important; visibility: hidden !important; opacity: 0 !important;';
            }
            document.querySelectorAll('[class*="splash"], [id*="splash"]').forEach(el => {
                el.style.cssText = 'display: none !important; visibility: hidden !important;';
            });
        };
        hideSplash();
        setTimeout(hideSplash, 100);
        setTimeout(hideSplash, 500);
        
        document.body.style.visibility = 'visible';
    } else {
        document.body.style.visibility = 'visible';
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
            scores[dim] = Math.min(10, (scores[dim] || 0) + pts);
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

    // 使用新的标签系统
    document.getElementById('result-icon').textContent = result.primaryInfo.emoji;
    document.getElementById('result-badge-cn').textContent = `【${result.labelCn}】`;
    document.getElementById('result-badge-en').textContent = `[${result.labelEn}]`;
    document.getElementById('result-user').textContent = `${name} 的专属档案`;
    document.getElementById('diagnosis-text').textContent = result.aiReport;

    // 渲染得分条（显示 x/10 格式）
    const barsEl = document.getElementById('score-bars');
    barsEl.innerHTML = '';
    result.bars.forEach((bar, i) => {
        const item = document.createElement('div');
        item.className = 'score-bar-item';
        item.innerHTML = `
            <span class="score-bar-emoji">${bar.emoji}</span>
            <span class="score-bar-label">${bar.cn}</span>
            <div class="score-bar-track">
                <div class="score-bar-fill" style="width:${bar.pct}%;background:${bar.color};"></div>
            </div>
            <span class="score-bar-value">${bar.val}/10</span>
        `;
        item.style.animationDelay = `${i * 0.1}s`;
        barsEl.appendChild(item);
    });

    // 更新总分和诊断
    const totalEl = document.getElementById('total-score');
    if (totalEl) {
        totalEl.innerHTML = `🎯 六维总分：<span>${result.sixDimTotal}</span>/60 (${result.percentScore}%)\n${result.madnessEmoji} ${result.madnessLevel}`;
    }

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
    ctx.fillText(result.primaryInfo.emoji, 400, 240);

    // 结果类型徽章
    ctx.font = 'bold 32px sans-serif';
    ctx.fillStyle = '#6c5ce7';
    ctx.fillText(`【${result.labelCn}】`, 400, 310);

    // 英文类型
    ctx.font = '20px sans-serif';
    ctx.fillStyle = '#888';
    ctx.fillText(`[${result.labelEn}]`, 400, 350);

    // 用户名
    ctx.font = '22px sans-serif';
    ctx.fillStyle = '#aaa';
    ctx.fillText(`${name} 的专属档案`, 400, 400);

    // 主维度和次维度
    ctx.font = '18px sans-serif';
    ctx.fillStyle = '#6c5ce7';
    ctx.fillText(`主维度：${result.primaryInfo.emoji} ${result.primaryInfo.cn} (${result.primaryScore}/10)`, 400, 440);

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
        // 进度条填充
        roundRect(ctx, 280, y - 8, Math.max(bar.pct * 35, 8), 24, 12);
        ctx.fillStyle = bar.color;
        ctx.fill();
        // 数值 (x/10格式)
        ctx.fillStyle = '#888';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(`${bar.val}/10`, 720, y + 8);
    });

    // AI诊断区背景（扩大区域以显示六维总分）
    roundRect(ctx, 40, 920, 720, 180, 20);
    ctx.fillStyle = 'rgba(26,26,58,0.9)';
    ctx.fill();

    // 六维总分显示
    ctx.font = 'bold 22px sans-serif';
    ctx.fillStyle = '#6c5ce7';
    ctx.textAlign = 'left';
    ctx.fillText(`🎯 六维总分：${result.sixDimTotal}/60 (${result.percentScore}%)`, 70, 960);
    
    // 疯狂等级
    ctx.font = '20px sans-serif';
    ctx.fillStyle = '#e84393';
    ctx.fillText(`${result.madnessEmoji} ${result.madnessLevel}`, 70, 990);

    // AI诊断标题
    ctx.fillStyle = '#888';
    ctx.font = '18px sans-serif';
    ctx.fillText('🧠 AI 诊断报告', 70, 1025);

    // 诊断内容（最后一行）
    ctx.font = '18px sans-serif';
    ctx.fillStyle = '#eee';
    ctx.fillText(CHAR_DESCRIPTIONS[result.dominant] || result.diagnosis.split('\n').pop(), 70, 1055, 660);

    // 底部
    ctx.fillStyle = '#6c5ce7';
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('#2026SBTI 个性测试  请到TG @XuanxuedashiBOT', 400, 1140);
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
// ── 分享结果 ────────────────────────────────────
async function shareResult() {
    const name = user?.first_name || '测试者';
    const result = window.SBTIData?.buildResult(name, scores);
    if (!result) {
        if (tg) tg.showAlert('结果数据未找到，请重试');
        return;
    }

    const resultPage = document.getElementById('result');
    const resultCard = resultPage?.querySelector('.result-card');
    if (!resultCard) {
        if (tg) tg.showAlert('结果页面未找到');
        return;
    }

    if (tg) tg.HapticFeedback.impactOccurred('light');

    try {
        // 等待动画完成
        await new Promise(r => setTimeout(r, 300));

        const canvas = await html2canvas(resultCard, {
            backgroundColor: '#0a0a1a',
            scale: 2,
            useCORS: true,
            logging: false,
            allowTaint: true,
            foreignObjectRendering: false,
            onclone: (clonedDoc) => {
                const fills = clonedDoc.querySelectorAll('.score-bar-fill');
                fills.forEach(f => {
                    f.style.transition = 'none';
                    f.style.animation = 'none';
                    const w = f.style.width;
                    f.style.width = w;
                });
            }
        });

        const dataUrl = canvas.toDataURL('image/png');
        const shareText = `#SBTI2026 六维人格测试

👤 ${name} 的专属档案
🏷️ 【${result.labelCn}】
📊 六维总分：${result.sixDimTotal}/60 (${result.percentScore}%)
${result.madnessEmoji} ${result.madnessLevel}

🧠 AI诊断报告
${result.aiReport.split('\n').slice(0,3).join('\n')}

@XuanxuedashiBOT 👈快来试试`;

        if (tg) {
            const encodedText = encodeURIComponent(shareText);
            const tgShareUrl = `https://t.me/share/url?url=https://xuan-miniapp-sbti.onrender.com&text=${encodedText}`;

            try {
                const blob = await (await fetch(dataUrl)).blob();
                const file = new File([blob], `SBTI_${name}_2026.png`, { type: 'image/png' });
                await navigator.share({ files: [file], text: shareText });
                return;
            } catch (e) {
                // 不支持分享 → 下载图片 + 打开TG链接
                const link = document.createElement('a');
                link.download = `SBTI_${name}_2026.png`;
                link.href = dataUrl;
                link.click();
                setTimeout(() => window.open(tgShareUrl, '_blank'), 300);
                if (tg) tg.HapticFeedback.impactOccurred('medium');
                return;
            }
        }

        // 无TG环境：下载图片
        const link = document.createElement('a');
        link.download = `SBTI_${name}_2026.png`;
        link.href = dataUrl;
        link.click();

    } catch (e) {
        console.error('shareResult error:', e);
        if (tg) tg.showAlert('分享失败，请稍后重试');
    }
}

// Canvas 2D 绘制结果图片
function drawResultToCanvas(name, result) {
    const canvas = document.createElement('canvas');
    canvas.width = 800;
    canvas.height = 1100;
    const ctx = canvas.getContext('2d');
    
    // 背景渐变
    const grad = ctx.createLinearGradient(0, 0, 0, 1100);
    grad.addColorStop(0, '#0a0a1a');
    grad.addColorStop(1, '#12122a');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 800, 1100);
    
    // 顶部装饰
    ctx.fillStyle = '#6c5ce7';
    ctx.fillRect(0, 0, 800, 6);
    
    // 标题
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 40px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('🧬 SBTI 2026 六维人格测试', 400, 70);
    
    // 分隔线
    ctx.strokeStyle = '#6c5ce7';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(60, 100);
    ctx.lineTo(740, 100);
    ctx.stroke();
    
    // 人格emoji和大标签
    ctx.font = '100px sans-serif';
    ctx.fillText(result.primaryInfo.emoji, 400, 230);
    
    ctx.font = 'bold 32px sans-serif';
    ctx.fillStyle = '#6c5ce7';
    ctx.fillText(`【${result.labelCn}】`, 400, 300);
    
    ctx.font = '20px sans-serif';
    ctx.fillStyle = '#888';
    ctx.fillText(`[${result.labelEn}]`, 400, 340);
    
    ctx.fillStyle = '#aaa';
    ctx.font = '22px sans-serif';
    ctx.fillText(`${name} 的专属档案`, 400, 390);
    
    ctx.font = '18px sans-serif';
    ctx.fillStyle = '#6c5ce7';
    ctx.fillText(`主维度：${result.primaryInfo.emoji} ${result.primaryInfo.cn} (${result.primaryScore}/10)`, 400, 430);
    
    // 六维数据
    result.bars.forEach((bar, i) => {
        const y = 500 + i * 60;
        ctx.font = '24px sans-serif';
        ctx.fillStyle = bar.color;
        ctx.textAlign = 'left';
        ctx.fillText(bar.emoji, 60, y);
        ctx.font = '18px sans-serif';
        ctx.fillStyle = '#bbb';
        ctx.fillText(bar.cn, 110, y);
        ctx.textAlign = 'right';
        ctx.fillText(`${bar.val}/10`, 740, y);
        
        // 进度条背景
        ctx.fillStyle = 'rgba(255,255,255,0.1)';
        ctx.beginPath();
        ctx.roundRect(60, y - 15, 520, 24, 12);
        ctx.fill();
        // 进度条
        ctx.fillStyle = bar.color;
        ctx.beginPath();
        ctx.roundRect(60, y - 15, Math.max(bar.pct * 5.2, 8), 24, 12);
        ctx.fill();
    });
    
    // 总分
    ctx.font = 'bold 24px sans-serif';
    ctx.fillStyle = '#e84393';
    ctx.textAlign = 'center';
    ctx.fillText(`${result.madnessEmoji} 六维总分：${result.sixDimTotal}/60 (${result.percentScore}%)`, 400, 940);
    
    // AI诊断摘要
    ctx.fillStyle = '#888';
    ctx.font = '18px sans-serif';
    ctx.fillText('🧠 AI诊断报告', 60, 990);
    ctx.fillStyle = '#eee';
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'left';
    const lines = result.aiReport.split('\n').slice(0, 5);
    lines.forEach((line, i) => {
        if (line.trim()) {
            ctx.fillText(line.substring(0, 45), 60, 1030 + i * 26);
        }
    });
    
    // 底部标签
    ctx.font = '14px sans-serif';
    ctx.fillStyle = '#555';
    ctx.textAlign = 'center';
    ctx.fillText('#SBTI2026 #六维人格测试', 400, 1080);
    
    return canvas.toDataURL('image/png');
}// ── 更新 Bot 按钮 ───────────────────────────────
function updateBotButton() {
    if (tg && tg.MainButton) {
        tg.MainButton.setText('返回玄学大师Bot');
        tg.MainButton.onClick(() => {
            window.location.href = `https://t.me/${tg.initDataUnsafe?.bot?.username || 'XuanxuedashiBOT'}`;
        });
        tg.MainButton.show();
    }
}
