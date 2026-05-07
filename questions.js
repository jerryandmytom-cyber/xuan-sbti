/**
 * SBTI 2026 题库（15题，随机抽取6题）
 * 与 xuanvip_SBTI.py 保持同步
 */

const SBTI_DIMS = {
    apathy: { cn: '躺平指数', en: 'ZZZZ', emoji: '😴', color: '#636e72' },
    ego:    { cn: '自我中心值', en: 'MALO', emoji: '🪞', color: '#fdcb6e' },
    chaos:  { cn: '疯狂浓度', en: 'FUCK', emoji: '🌀', color: '#e17055' },
    grind:  { cn: '卷王系数', en: 'GRND', emoji: '💼', color: '#0984e3' },
    vibe:   { cn: '氛围感知力', en: 'VIBE', emoji: '✨', color: '#e84393' },
    lore:   { cn: '人设稳定度', en: 'LORE', emoji: '🎭', color: '#00cec9' },
};

const CHAR_DESCRIPTIONS = {
    apathy: '能量守恒大师，用最少的投入换取最大的精神安宁。不是不爱，是爱得太累了。',
    ego:    '宇宙中心候选人，世界是你的镜子，每面都在反射你的高光时刻。',
    chaos:  '人间搅局艺术家，你的出现让世界的信噪比直线下降，但也充满了惊喜。',
    grind:  '卷王王中王，你把「内卷」升华成了一种美学，效率是你的信仰。',
    vibe:   '氛围感知雷达，你能在0.5秒内读懂房间里所有人的微表情，然后精准破防。',
    lore:   '人设工程师，你的每一条发言都是精心设计的叙事碎片，粉丝们正在拼图。',
};

const VIRAL_TITLES = {
    apathy: [
        ['完全静止体', 'Full Static Mode'],
        ['核心沉默主义者', 'Core Silence Enjoyer'],
        ['零耗能生物', 'Zero-Energy Entity'],
    ],
    ego: [
        ['主角光环认证人', 'Main Character Certified'],
        ['个人叙事构建师', 'Personal Lore Architect'],
        ['视角霸主', 'POV Monopolist'],
    ],
    chaos: [
        ['量子发癫体', 'Quantum Unhinged'],
        ['混沌魅力体', 'Chaos Charisma Core'],
        ['全员情绪污染源', 'Emotional Hazard Unit'],
    ],
    grind: [
        ['效率怪物进化体', 'Efficiency Monster EVO'],
        ['时间密度最大化者', 'Time Density Maximizer'],
        ['全栈人生CEO', 'Full-Stack Life CEO'],
    ],
    vibe: [
        ['氛围感过载实体', 'Vibe Overload Entity'],
        ['共情辐射源', 'Empathy Radiation Core'],
        ['情绪天气预报员', 'Emotional Weather Anchor'],
    ],
    lore: [
        ['人设钢铁侠', 'Personal Lore Ironman'],
        ['叙事连贯性冠军', 'Narrative Consistency Champ'],
        ['角色扮演终身会员', 'Lifelong Character Player'],
    ],
};

const ALL_QUESTIONS = [
    {
        id: 1,
        text: '当你发现群聊有 99+ 未读消息，你的第一反应是？',
        options: [
            { text: '右键全部已读，继续摸鱼 🤫', score: { apathy: 10 } },
            { text: '爬楼找有没有人提到自己 🧐', score: { ego: 10 } },
            { text: '直接退群，人间不值得 🚪', score: { chaos: 10 } },
            { text: '认真看完，生怕错过重要信息 👀', score: { grind: 10 } },
        ]
    },
    {
        id: 2,
        text: '朋友发了条 2 分钟的语音，你会？',
        options: [
            { text: '1.5x 速度播完，笑着回 \'好的\'', score: { grind: 8, apathy: 2 } },
            { text: '截图发给另一个朋友问啥意思 😈', score: { ego: 7, chaos: 3 } },
            { text: '听完深感共鸣，写了一大段回复', score: { vibe: 10 } },
            { text: '挂着语音睡着了，明天再说', score: { apathy: 10 } },
        ]
    },
    {
        id: 3,
        text: '你的社交媒体主页风格是？',
        options: [
            { text: '精心策划的人设，每条都有主题色 🎨', score: { lore: 10 } },
            { text: '一年发三条，且全是转发', score: { apathy: 10 } },
            { text: '随机发癫内容，粉丝看不懂就对了', score: { chaos: 10 } },
            { text: '成就卡合集 + 工作打卡，绩效全公开', score: { grind: 10 } },
        ]
    },
    {
        id: 4,
        text: '工作群凌晨2点弹出消息，你会？',
        options: [
            { text: '静音睡觉，明天再说 😊', score: { apathy: 10 } },
            { text: '内心纠结3分钟，然后继续睡', score: { vibe: 8, apathy: 2 } },
            { text: '立刻回复，证明自己是卷王 💪', score: { grind: 10 } },
            { text: '截图发朋友圈：这就是打工人的命运', score: { lore: 7, chaos: 3 } },
        ]
    },
    {
        id: 5,
        text: '朋友找你吐槽，你一般会？',
        options: [
            { text: '认真倾听，给出分析建议 📋', score: { grind: 10 } },
            { text: '共情满分，同步进入悲伤模式 🥲', score: { vibe: 10 } },
            { text: '听完立刻转移话题，不想被负能量影响', score: { apathy: 8, chaos: 2 } },
            { text: '记下来，以后写进段子 🤔', score: { ego: 7, lore: 3 } },
        ]
    },
    {
        id: 6,
        text: '你去唱卡拉OK，一般会？',
        options: [
            { text: '抢麦 DJ 台，主导全场 🎤', score: { ego: 10, chaos: 2 } },
            { text: '角落里当气氛组，偶尔配合 🎶', score: { apathy: 8, vibe: 2 } },
            { text: '提前点好歌单，严格按歌单唱', score: { lore: 10 } },
            { text: '麦克风递过来就假装唱歌，实际上是听歌', score: { apathy: 10 } },
        ]
    },
    {
        id: 7,
        text: '当你听到一个重大八卦，你的反应是？',
        options: [
            { text: '第一时间转发给最铁的朋友 😱', score: { chaos: 10 } },
            { text: '表面平静，内心已经开始分析高铁', score: { vibe: 8, grind: 2 } },
            { text: '假装不知道，但已经截图存档 📸', score: { lore: 10 } },
            { text: '哦。真的吗。', score: { apathy: 10 } },
        ]
    },
    {
        id: 8,
        text: '周末你一般怎么过？',
        options: [
            { text: '加班 or 搞副业，躺平是对生命的浪费', score: { grind: 10 } },
            { text: '自然醒，点外卖，刷剧到天黑 📺', score: { apathy: 10 } },
            { text: '约朋友探店拍照，发精心编辑的朋友圈', score: { lore: 8, vibe: 2 } },
            { text: '随机触发：临时约局，目的地看心情', score: { chaos: 10 } },
        ]
    },
    {
        id: 9,
        text: '你被当众表扬了，你的内心戏是？',
        options: [
            { text: '：）表面淡定，实际已经在想获奖感言', score: { ego: 10 } },
            { text: '能不能快点结束，我想静静 😇', score: { apathy: 10 } },
            { text: '这内容要更新到下个月的人设帖子里', score: { lore: 10 } },
            { text: '感谢团队，这不是我一个人的功劳 📝', score: { vibe: 10 } },
        ]
    },
    {
        id: 10,
        text: '你和朋友吵架了，你会？',
        options: [
            { text: '先发一条长消息解释清楚，不留误会', score: { grind: 10, vibe: 2 } },
            { text: '拉黑删除，三天后当无事发生', score: { apathy: 10 } },
            { text: '发一条意味深长的朋友圈内涵对方', score: { chaos: 10 } },
            { text: '想想这段关系在人设里的位置，再决定', score: { lore: 10 } },
        ]
    },
    {
        id: 11,
        text: '你做选择的风格，更接近哪个？',
        options: [
            { text: '利弊分析表格，量化评分决策 📊', score: { grind: 10 } },
            { text: '感觉对了就冲，逻辑是后来的事 ✨', score: { vibe: 10 } },
            { text: '随机数生成器，命运交给算法 🎲', score: { chaos: 10 } },
            { text: '先想想这个选择是否符合人设定位', score: { lore: 10 } },
        ]
    },
    {
        id: 12,
        text: '你在一个陌生领域里，会怎么做？',
        options: [
            { text: '先搜索50篇相关文章，理论先行 📚', score: { grind: 10 } },
            { text: '假装很懂，先入场再说 🎭', score: { ego: 10 } },
            { text: '等朋友带路，不想自己踩坑', score: { apathy: 10 } },
            { text: '乱闯，踩坑了就是最好的学习', score: { chaos: 10 } },
        ]
    },
    {
        id: 13,
        text: '你理想的退休生活是？',
        options: [
            { text: '周游世界，打卡所有顶级目的地 🌍', score: { grind: 10 } },
            { text: '回乡下种地，社交媒体偶尔发发日常', score: { lore: 8, apathy: 2 } },
            { text: '什么都不做，就是躺着 💤', score: { apathy: 10 } },
            { text: '不知道，退休的事退休再说 🤷', score: { chaos: 8, vibe: 2 } },
        ]
    },
    {
        id: 14,
        text: '你的聊天记录风格更像？',
        options: [
            { text: '能发表情包绝不打字 🎭', score: { chaos: 10 } },
            { text: '回复永远在5分钟内，效率至上 ⚡', score: { grind: 10 } },
            { text: '长篇大论，认真到对方已读不回', score: { vibe: 10 } },
            { text: '只回有必要回复的，其他装作没看到 🙈', score: { apathy: 10 } },
        ]
    },
    {
        id: 15,
        text: '你被别人模仿了，你会？',
        options: [
            { text: '暗中观察，看TA模仿得像不像 👀', score: { lore: 10 } },
            { text: '有点不爽，但懒得计较 😑', score: { apathy: 10 } },
            { text: '直接当面质问，你在搞什么？🔥', score: { ego: 10 } },
            { text: '觉得好笑，甚至想教TA几招 🧑‍🏫', score: { vibe: 10 } },
        ]
    },
];

// 随机抽取n道题
function getRandomQuestions(n = 6) {
    const shuffled = [...ALL_QUESTIONS].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, n);
}

// 计算主维度
function getDominantDim(scores) {
    return Object.entries(scores).reduce((a, b) => a[1] > b[1] ? a : b)[0];
}

// 获取随机标题
function getViralTitle(dim) {
    const titles = VIRAL_TITLES[dim] || VIRAL_TITLES.chaos;
    return titles[Math.floor(Math.random() * titles.length)];
}

// 构建结果数据
function buildResult(name, scores) {
    const dominant = getDominantDim(scores);
    const [titleCn, titleEn] = getViralTitle(dominant);
    const dimInfo = SBTI_DIMS[dominant];
    const total = Math.max(Object.values(scores).reduce((s, v) => s + v, 0), 1);

    const bars = Object.entries(SBTI_DIMS).map(([key, info]) => {
        const val = scores[key] || 0;
        const pct = Math.round((val / total) * 10);
        return { ...info, key, val, pct };
    });

    return {
        titleCn,
        titleEn,
        dominant,
        dimInfo,
        bars,
        diagnosis: CHAR_DESCRIPTIONS[dominant],
        name,
    };
}

window.SBTIData = { SBTI_DIMS, ALL_QUESTIONS, getRandomQuestions, buildResult };