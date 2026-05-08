/**
 * 🔮 SBTI 性格测试 Mini App
 * 前端应用逻辑
 */

(function() {
    'use strict';

    const AppState = {
        currentQuestion: 0,
        answers: [],
        totalQuestions: 0,
        result: null
    };

    let tg = window.Telegram?.WebApp;

    function initTelegram() {
        if (tg) {
            tg.ready();
            tg.expand();
        }
    }

    const API = {
        async getQuestions() {
            try {
                const response = await fetch('/api/questions');
                const data = await response.json();
                return data;
            } catch (error) {
                console.error('获取题目失败:', error);
                return null;
            }
        },

        async submitAnswers(answers) {
            try {
                const response = await fetch('/api/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ answers })
                });
                const data = await response.json();
                return data;
            } catch (error) {
                console.error('提交答案失败:', error);
                return null;
            }
        }
    };

    const UI = {
        showLoading(text = 'AI分析中...') {
            const overlay = document.getElementById('loading-overlay');
            overlay.querySelector('p').textContent = text;
            overlay.classList.add('active');
        },

        hideLoading() {
            document.getElementById('loading-overlay').classList.remove('active');
        },

        showScreen(screenId) {
            document.querySelectorAll('.screen').forEach(screen => {
                screen.classList.remove('active');
            });
            document.getElementById(screenId).classList.add('active');
        },

        updateProgress() {
            const progress = ((AppState.currentQuestion + 1) / AppState.totalQuestions) * 100;
            document.getElementById('progress-fill').style.width = progress + '%';
            document.getElementById('current-q').textContent = AppState.currentQuestion + 1;
        },

        renderQuestion(question) {
            const questionText = document.getElementById('question-text');
            const optionsContainer = document.getElementById('options');
            
            questionText.textContent = question.question;
            optionsContainer.innerHTML = '';

            question.options.forEach((option, index) => {
                const optionEl = document.createElement('div');
                optionEl.className = 'option';
                optionEl.dataset.key = option.key;
                optionEl.textContent = option.text;
                
                optionEl.addEventListener('click', () => this.selectOption(optionEl, option.key));
                optionsContainer.appendChild(optionEl);
            });

            // 更新按钮状态
            document.getElementById('prev-btn').disabled = AppState.currentQuestion === 0;
            document.getElementById('next-btn').disabled = !AppState.answers[AppState.currentQuestion];
        },

        selectOption(element, key) {
            // 移除其他选中状态
            document.querySelectorAll('.option').forEach(opt => {
                opt.classList.remove('selected');
            });
            
            element.classList.add('selected');
            AppState.answers[AppState.currentQuestion] = key;
            document.getElementById('next-btn').disabled = false;
        },

        async goToQuestion(index) {
            AppState.currentQuestion = index;
            this.updateProgress();

            const data = await API.getQuestions();
            if (data && data.questions) {
                AppState.totalQuestions = data.questions.length;
                document.getElementById('total-q').textContent = AppState.totalQuestions;
                this.renderQuestion(data.questions[AppState.currentQuestion]);
            }
        },

        async submitTest() {
            this.showLoading();
            
            const result = await API.submitAnswers(AppState.answers);
            
            this.hideLoading();

            if (result && result.success && result.result) {
                AppState.result = result.result;
                this.showResult(result.result);
            } else {
                alert('提交失败，请重试');
            }
        },

        showResult(result) {
            document.getElementById('mbti-type').textContent = result.type;
            
            // 显示人格描述
            const descriptions = {
                'INTJ': { name: '建筑师', desc: '你是一个独立思考者，善于战略规划，拥有强大的分析能力和创造力。你喜欢解决复杂的问题，追求知识和效率。' },
                'INTP': { name: '思想家', desc: '你是一个深刻的思想家，对知识和理论充满好奇。你善于分析，喜欢独立工作，追求完美的逻辑和理解。' },
                'ENTJ': { name: '指挥官', desc: '你是一个天生的领导者，果断、自信、有战略眼光。你喜欢挑战，追求效率和成果，善于组织团队达成目标。' },
                'ENTP': { name: '辩论家', desc: '你是一个充满创意的思想家，好奇心强，思维敏捷。你喜欢辩论和探索新想法，善于发现机会和可能性。' },
                'INFJ': { name: '提倡者', desc: '你是一个理想主义者，有着深刻的洞察力和同理心。你追求意义和价值，善于帮助他人实现潜能。' },
                'INFP': { name: '调停者', desc: '你是一个理想主义者，善良、忠诚、有创造力。你重视内心的价值观，追求自我实现和帮助他人。' },
                'ENFJ': { name: '主人公', desc: '你是一个热情的领导者和激励者，有强烈的沟通能力。你善于启发他人，追求团队和谐与共同成长。' },
                'ENFP': { name: '竞选者', desc: '你是一个充满热情和创意的自由灵魂，好奇心强，乐观积极。你善于激励他人，享受探索新的可能性。' },
                'ISTJ': { name: '物流师', desc: '你是一个可靠、务实的人，重视责任和诚信。你做事有条理，注重细节，善于执行和完成目标。' },
                'ISFJ': { name: '守护者', desc: '你是一个忠诚、温暖的人，重视传统和责任。你善于照顾他人，默默奉献，是可靠的伙伴。' },
                'ESTJ': { name: '总经理', desc: '你是一个务实、高效的领导者，重视秩序和成果。你善于组织和管理，决策果断，执行力强。' },
                'ESFJ': { name: '执政官', desc: '你是一个热情、友善的人，重视和谐与合作。你善于照顾他人，社交能力强，是团队中的粘合剂。' },
                'ISTP': { name: '大师', desc: '你是一个灵活、实际的问题解决者，善于动手操作。你喜欢探索事物的原理，独立而专注。' },
                'ISFP': { name: '探险家', desc: '你是一个温柔、敏感的艺术者，热爱自由和美。你善于发现生活的美好，行动力强，喜欢体验新事物。' },
                'ESTP': { name: '企业家', desc: '你是一个充满活力和行动力的人，喜欢冒险和挑战。你善于把握机会，反应敏捷，享受当下。' },
                'ESFP': { name: '表演者', desc: '你是一个充满活力和热情的人，热爱社交和娱乐。你善于活跃气氛，享受生活，是大家的开心果。' }
            };

            const typeDesc = descriptions[result.type] || { name: '未知', desc: '等待探索' };
            document.getElementById('type-description').innerHTML = `
                <strong>${typeDesc.name}</strong><br>
                ${typeDesc.desc}
            `;

            // 显示维度分数
            const dimensions = document.getElementById('dimensions');
            dimensions.innerHTML = `
                <div class="dimension-item">
                    <div class="dimension-name">外向-内向</div>
                    <div class="dimension-value">${result.scores.E >= result.scores.I ? 'E ' + Math.round(result.scores.E) : 'I ' + Math.round(result.scores.I)}</div>
                </div>
                <div class="dimension-item">
                    <div class="dimension-name">实感-直觉</div>
                    <div class="dimension-value">${result.scores.S >= result.scores.N ? 'S ' + Math.round(result.scores.S) : 'N ' + Math.round(result.scores.N)}</div>
                </div>
                <div class="dimension-item">
                    <div class="dimension-name">思考-情感</div>
                    <div class="dimension-value">${result.scores.T >= result.scores.F ? 'T ' + Math.round(result.scores.T) : 'F ' + Math.round(result.scores.F)}</div>
                </div>
                <div class="dimension-item">
                    <div class="dimension-name">判断-知觉</div>
                    <div class="dimension-value">${result.scores.J >= result.scores.P ? 'J ' + Math.round(result.scores.J) : 'P ' + Math.round(result.scores.P)}</div>
                </div>
            `;

            this.showScreen('result-screen');
        },

        shareResult() {
            if (!AppState.result || !tg) return;
            
            const shareText = `🔮 SBTI性格测试\n\n我的性格类型：${AppState.result.type}\n\n快来测试你的性格吧！`;
            
            if (navigator.clipboard) {
                navigator.clipboard.writeText(shareText).then(() => {
                    alert('结果已复制到剪贴板！');
                });
            }
        },

        restart() {
            AppState.currentQuestion = 0;
            AppState.answers = [];
            AppState.result = null;
            this.showScreen('welcome-screen');
        }
    };

    function bindEvents() {
        document.getElementById('start-btn').addEventListener('click', () => {
            UI.showScreen('test-screen');
            UI.goToQuestion(0);
        });

        document.getElementById('next-btn').addEventListener('click', async () => {
            if (AppState.currentQuestion < AppState.totalQuestions - 1) {
                AppState.currentQuestion++;
                UI.updateProgress();
                
                const data = await API.getQuestions();
                if (data && data.questions) {
                    UI.renderQuestion(data.questions[AppState.currentQuestion]);
                }
            } else {
                UI.submitTest();
            }
        });

        document.getElementById('prev-btn').addEventListener('click', async () => {
            if (AppState.currentQuestion > 0) {
                AppState.currentQuestion--;
                UI.updateProgress();
                
                const data = await API.getQuestions();
                if (data && data.questions) {
                    UI.renderQuestion(data.questions[AppState.currentQuestion]);
                    
                    // 恢复之前的答案
                    const savedAnswer = AppState.answers[AppState.currentQuestion];
                    if (savedAnswer) {
                        const optionEl = document.querySelector(`.option[data-key="${savedAnswer}"]`);
                        if (optionEl) {
                            document.querySelectorAll('.option').forEach(opt => opt.classList.remove('selected'));
                            optionEl.classList.add('selected');
                        }
                    }
                }
            }
        });

        document.getElementById('share-btn').addEventListener('click', () => UI.shareResult());
        document.getElementById('restart-btn').addEventListener('click', () => UI.restart());
    }

    async function init() {
        initTelegram();
        bindEvents();
        
        const data = await API.getQuestions();
        if (data && data.questions) {
            AppState.totalQuestions = data.questions.length;
            document.getElementById('total-q').textContent = AppState.totalQuestions;
        }
    }

    document.addEventListener('DOMContentLoaded', init);

})();