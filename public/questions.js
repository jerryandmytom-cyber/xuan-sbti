/**
 * SBTI 2026 题库（50道，随机抽取6题）
 * 与 xuanvip_SBTI.py 保持同步
 * 
 * 维度权重说明：
 * - 正向题：选项分数10=强关联，8=中关联，2=弱关联
 * - 反向题：分数越低反而越能体现该维度特征
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
    {
        id: 16,
        text: '朋友晒了一张精修自拍，你会？',
        options: [
            { text: '认真夸赞，分析哪里修得好 📸', score: { vibe: 10 } },
            { text: '怀疑是不是同一个人，不敢认 🙈', score: { ego: 8, chaos: 2 } },
            { text: '点个赞划走，不想多看 👆', score: { apathy: 10 } },
            { text: '思考自己下次拍照怎么构图 🤳', score: { grind: 8, ego: 2 } },
        ]
    },
    {
        id: 17,
        text: '你写朋友圈的频率是？',
        options: [
            { text: '有主题系列更新，定期营业 📅', score: { lore: 10 } },
            { text: '想发就发，不考虑数据反馈 📝', score: { chaos: 10 } },
            { text: '一年不超过5条，珍惜羽毛 🪶', score: { apathy: 10 } },
            { text: '每次发完都会看阅读量 📊', score: { grind: 10 } },
        ]
    },
    {
        id: 18,
        text: '遇到选择困难时，你一般会？',
        options: [
            { text: '列个Excel表格分析利弊 🧮', score: { grind: 10 } },
            { text: '让别人替自己选，反正后果一起扛 🤝', score: { apathy: 10 } },
            { text: '掷骰子或抛硬币，让命运决定 🎲', score: { chaos: 10 } },
            { text: '跟着感觉走，感觉对了就是对了 ✨', score: { vibe: 10 } },
        ]
    },
    {
        id: 19,
        text: '你参加聚会的目的是？',
        options: [
            { text: '认识新人，扩展社交网络 🌐', score: { ego: 8, grind: 2 } },
            { text: '和老朋友叙旧，珍惜老伙计 👯', score: { lore: 8, vibe: 2 } },
            { text: '为了吃顿好的，仅此而已 🍖', score: { apathy: 10 } },
            { text: '万一遇到有趣的人呢，随缘 🚶', score: { chaos: 10 } },
        ]
    },
    {
        id: 20,
        text: '你给自己贴的标签是？',
        options: [
            { text: '这也不能，那也不能，反正不是普通人 🚫', score: { ego: 10 } },
            { text: '没有标签，我就是一个没有标签的人 🏷️', score: { lore: 8, ego: 2 } },
            { text: '随心情切换，每天不一样 🌈', score: { chaos: 10 } },
            { text: '专注搞钱，其他都是浮云 💰', score: { grind: 10 } },
        ]
    },
    {
        id: 21,
        text: '你通常怎么应对负面情绪？',
        options: [
            { text: '写长文发在只有自己可见的地方 📝', score: { lore: 10 } },
            { text: '找人倾诉，一定要把情绪倒干净 🗣️', score: { vibe: 10 } },
            { text: '刷短视频逃避，等它自己消失 🌀', score: { apathy: 10 } },
            { text: '跑步或健身，物理消化情绪 🏃', score: { grind: 10 } },
        ]
    },
    {
        id: 22,
        text: '你更愿意成为哪种关系的中心？',
        options: [
            { text: '朋友圈的信息枢纽，谁的事都知道 🕸️', score: { vibe: 10 } },
            { text: '家人离不开的那种，无可替代 🏠', score: { lore: 8, grind: 2 } },
            { text: '工作群的红人，有事第一个想到 👑', score: { ego: 10 } },
            { text: '小圈子的灵魂人物，质量大于数量 🎭', score: { ego: 8, lore: 2 } },
        ]
    },
    {
        id: 23,
        text: '当有人说「你怎么变了」，你的反应是？',
        options: [
            { text: '我就是变了，你跟得上吗 😎', score: { ego: 10 } },
            { text: '变？我一直是这样啊 🤨', score: { lore: 8, vibe: 2 } },
            { text: '没变啊，你的感觉不准 👀', score: { apathy: 10 } },
            { text: '可能吧，但我不在乎别人怎么说 🤷', score: { chaos: 8, ego: 2 } },
        ]
    },
    {
        id: 24,
        text: '你更享受哪种独处方式？',
        options: [
            { text: '关掉手机，躺尸到天荒地老 🛋️', score: { apathy: 10 } },
            { text: '学习新技能，让时间更有价值 📚', score: { grind: 10 } },
            { text: '整理回忆，编排自己的人生剧本 📖', score: { lore: 10 } },
            { text: '发呆幻想，脑内剧场无限精彩 🎬', score: { ego: 8, chaos: 2 } },
        ]
    },
    {
        id: 25,
        text: '你如何看待「躺平」这个词？',
        options: [
            { text: '我的终极人生哲学，非常认同 🛌', score: { apathy: 10 } },
            { text: '不过是自嘲罢了，该卷还是卷 💪', score: { grind: 10 } },
            { text: '躺不平的，你看房贷答应吗 🏦', score: { vibe: 8, grind: 2 } },
            { text: '一种人设标签，适合某些场合 🎪', score: { lore: 10 } },
        ]
    },
    {
        id: 26,
        text: '你的工作风格更接近？',
        options: [
            { text: 'Deadline是第一生产力，拖到最后一秒 ⏰', score: { chaos: 10 } },
            { text: '提前规划，任务分解，日清日结 📋', score: { grind: 10 } },
            { text: '看心情，心情好效率高，心情差摆烂 🌊', score: { apathy: 10 } },
            { text: '让老板满意是核心，其他都是浮云 👔', score: { ego: 10 } },
        ]
    },
    {
        id: 27,
        text: '你如何处理好友列表里的人？',
        options: [
            { text: '定期清理，不适合就删，社交要断舍离 🧹', score: { ego: 10 } },
            { text: '从来不删，万一哪天需要呢 📋', score: { grind: 8, apathy: 2 } },
            { text: '分组管理，不同的人给不同的权限 🔐', score: { lore: 10 } },
            { text: '根本不在乎列表，反正也不怎么聊天 💬', score: { apathy: 10 } },
        ]
    },
    {
        id: 28,
        text: '你对自己未来的期待是？',
        options: [
            { text: '财务自由，提前退休，周游世界 🌍', score: { grind: 10 } },
            { text: '成为一个传说，有故事可以说 📖', score: { ego: 8, lore: 2 } },
            { text: '活在当下，想那么远干嘛 🦋', score: { chaos: 10 } },
            { text: '找到几个知心人，岁月静好 🌙', score: { vibe: 10 } },
        ]
    },
    {
        id: 29,
        text: '职场中你属于哪种类型？',
        options: [
            { text: '准时打卡，绩效A，朋友圈都是工作打卡 📊', score: { grind: 10 } },
            { text: '踩点下班，工作只是生活的一部分 ⏰', score: { apathy: 10 } },
            { text: '办公室政治专家，谁和谁不对付都门清 🕵️', score: { lore: 8, vibe: 2 } },
            { text: '开会时内心戏丰富，表面点头如捣蒜 👔', score: { ego: 8, chaos: 2 } },
        ]
    },
    {
        id: 30,
        text: '恋爱关系中你更接近？',
        options: [
            { text: '每日汇报行程，安全感来自于掌控 📱', score: { ego: 10 } },
            { text: '各玩各的，信任是给对方自由 🦋', score: { apathy: 8, chaos: 2 } },
            { text: '发朋友圈必带对象，营造幸福人设 📸', score: { lore: 10 } },
            { text: '情绪跟着对方走，TA开心我就开心 😊', score: { vibe: 10 } },
        ]
    },
    {
        id: 31,
        text: '社交媒体上你更在意？',
        options: [
            { text: '点赞数，数据证明存在感 📊', score: { grind: 10 } },
            { text: '评论区互动，社交不能断 🔥', score: { vibe: 10 } },
            { text: '粉丝增长曲线，数字让我兴奋 📈', score: { ego: 8, grind: 2 } },
            { text: '收藏量，关注但不点赞是我的风格 💾', score: { lore: 8, apathy: 2 } },
        ]
    },
    {
        id: 32,
        text: '你发朋友圈的真实目的是？',
        options: [
            { text: '记录生活，若干年后翻看 📖', score: { lore: 8, vibe: 2 } },
            { text: '立人设，让别人羡慕去吧 😏', score: { ego: 10 } },
            { text: '单纯想发，发完就不管了 🙌', score: { chaos: 8, apathy: 2 } },
            { text: '工作需要，维持形象分 👔', score: { grind: 10 } },
        ]
    },
    {
        id: 33,
        text: '以下哪种情况最让你崩溃？',
        options: [
            { text: '精心拍的照片只有12个赞 😱', score: { grind: 10 } },
            { text: '被朋友当众揭短，社死现场 💀', score: { ego: 10 } },
            { text: '计划全部打乱，从头再来 💔', score: { lore: 10 } },
            { text: '和谁都不熟，尴尬的空气 🫠', score: { vibe: 10 } },
        ]
    },
    {
        id: 34,
        text: '「收到请回复」对你来说意味着？',
        options: [
            { text: '必须秒回，否则会焦虑不安 📱', score: { grind: 10 } },
            { text: '看心情，决定回不回 🎲', score: { chaos: 8, apathy: 2 } },
            { text: '为什么要回复？我已读了不是吗 👀', score: { apathy: 10 } },
            { text: '先看看别人回什么，跟风党 🐑', score: { vibe: 8, grind: 2 } },
        ]
    },
    {
        id: 35,
        text: '你排队时一般会？',
        options: [
            { text: '研究怎么缩短排队时间，效率至上 ⏱️', score: { grind: 10 } },
            { text: '和前后的人聊天，社交无处不在 💬', score: { vibe: 10 } },
            { text: '刷手机发呆，时间自动流逝 📱', score: { apathy: 10 } },
            { text: '内心编剧：前面的人会不会突然闹事 🎬', score: { chaos: 10 } },
        ]
    },
    {
        id: 36,
        text: '你相册里数量最多的照片类型是？',
        options: [
            { text: '自拍，每个角度都要收集 📸', score: { ego: 10 } },
            { text: '食物拍，美食当前先喂手机 🍜', score: { lore: 8, vibe: 2 } },
            { text: '截图，合集可以出一本书 📚', score: { grind: 10 } },
            { text: '没什么照片，定期清理是习惯 🧹', score: { apathy: 10 } },
        ]
    },
    {
        id: 37,
        text: '你如何应对群聊里的冲突？',
        options: [
            { text: '截图保存，以后万一用得上 📸', score: { lore: 10 } },
            { text: '发表情包化解，幽默是武器 🎭', score: { chaos: 10 } },
            { text: '潜水围观，内心写好了剧本 📝', score: { ego: 8, vibe: 2 } },
            { text: '直接退出，眼不见为净 🚪', score: { apathy: 10 } },
        ]
    },
    {
        id: 38,
        text: '你更愿意为什么内容付费？',
        options: [
            { text: '知识付费课程，升值自己 💰', score: { grind: 10 } },
            { text: '情绪价值产品，我快乐最重要 🎵', score: { vibe: 8, chaos: 2 } },
            { text: '社交会员，圈子决定阶层 🌐', score: { ego: 10 } },
            { text: '无所谓，有免费的就用 🙌', score: { apathy: 10 } },
        ]
    },
    {
        id: 39,
        text: '反问：你其实是个很卷的人吗？（诚实作答）',
        options: [
            { text: '是的，我很努力，我要出人头地 💪', score: { grind: 10 } },
            { text: '不是，我只是假装很忙 😅', score: { lore: 8, apathy: 2 } },
            { text: '看情况，被逼急了也会卷起来 🔥', score: { chaos: 8, vibe: 2 } },
            { text: '我躺得很平，但偶尔也会焦虑 🛌', score: { apathy: 8, grind: 2 } },
        ]
    },
    {
        id: 40,
        text: '反问：你在意别人对你的评价吗？',
        options: [
            { text: '完全不在意，我的人生我说了算 🙌', score: { ego: 10 } },
            { text: '表面不在意，内心已经分析了三遍 🧠', score: { lore: 10 } },
            { text: '会在意，但不会表现出来 🎭', score: { vibe: 10 } },
            { text: '无所谓，反正大家都在忙自己的事 👀', score: { apathy: 10 } },
        ]
    },
    {
        id: 41,
        text: '反问：你是朋友圈的中心人物吗？',
        options: [
            { text: '必须是，有我在气氛就不会冷 🎉', score: { ego: 10 } },
            { text: '不是，我是幕后玩家 👻', score: { lore: 10 } },
            { text: '看场合，有时候我只想安静 🎧', score: { apathy: 8, vibe: 2 } },
            { text: '我负责制造氛围，不是主角 ✨', score: { chaos: 8, vibe: 2 } },
        ]
    },
    {
        id: 42,
        text: '反问：你真的能接受躺平吗？',
        options: [
            { text: '躺平是梦想，但钱包不允许 💸', score: { grind: 8, apathy: 2 } },
            { text: '可以，我已经躺平很久了 😴', score: { apathy: 10 } },
            { text: '嘴上躺平，身体很诚实 🏃', score: { chaos: 10 } },
            { text: '间歇性躺平，持续性焦虑 🔄', score: { vibe: 8, grind: 2 } },
        ]
    },
    {
        id: 43,
        text: '你在以下哪个场景最自在？',
        options: [
            { text: '一个人在家，完全不用社交 🏠', score: { apathy: 10 } },
            { text: '会议室，所有的目光都聚焦在我身上 👑', score: { ego: 10 } },
            { text: '深夜的便利店，安静治愈 🌙', score: { lore: 8, vibe: 2 } },
            { text: '音乐节，人浪涌动，释放自我 🎸', score: { chaos: 10 } },
        ]
    },
    {
        id: 44,
        text: '你的消费观更接近？',
        options: [
            { text: '该花花该省省，每分钱都要花在刀刃上 🗡️', score: { grind: 10 } },
            { text: '今天心情好，买！明天再说 💳', score: { chaos: 10 } },
            { text: '买什么都像在构建人设的一部分 🎭', score: { lore: 10 } },
            { text: '买之前先看测评，不交智商税 📱', score: { vibe: 8, grind: 2 } },
        ]
    },
    {
        id: 45,
        text: '当朋友突然找你借钱，你会？',
        options: [
            { text: '直接问要多少，转账不废话 💰', score: { vibe: 10 } },
            { text: '先发个表情包拖延，再想办法 😅', score: { chaos: 10 } },
            { text: '编个理由婉拒，关系没到那份上 🚫', score: { ego: 10 } },
            { text: '假装没看到，过几天再说 🙈', score: { apathy: 10 } },
        ]
    },
    {
        id: 46,
        text: '你更相信什么？',
        options: [
            { text: '努力就会有回报，天道酬勤 📈', score: { grind: 10 } },
            { text: '运气，选择大于努力 🍀', score: { chaos: 10 } },
            { text: '关系，有人脉走遍天下 🌐', score: { ego: 10 } },
            { text: '缘分，命里有时终须有 🕊️', score: { lore: 8, vibe: 2 } },
        ]
    },
    {
        id: 47,
        text: '你更愿意为什么花时间？',
        options: [
            { text: '自我提升，学习新技能永远不亏 📚', score: { grind: 10 } },
            { text: '维护关系，情感投资很重要 💕', score: { vibe: 10 } },
            { text: '经营人设，每个细节都要完美 🎨', score: { lore: 10 } },
            { text: '发呆放空，让大脑彻底休息 🧘', score: { apathy: 10 } },
        ]
    },
    {
        id: 48,
        text: '你在群里最常扮演的角色是？',
        options: [
            { text: '气氛组，发表情包我最强 🎭', score: { chaos: 10 } },
            { text: '信息枢纽，有事找我准没错 📡', score: { vibe: 10 } },
            { text: '潜水员，默默观察一切 👀', score: { apathy: 8, lore: 2 } },
            { text: '话题发起者，带节奏我在行 🚀', score: { ego: 10 } },
        ]
    },
    {
        id: 49,
        text: '反问：你觉得自己是个有特点的人吗？',
        options: [
            { text: '必须有，我的存在就是特点 ✨', score: { ego: 10 } },
            { text: '特点不明显，但有一点点 🦋', score: { lore: 8, vibe: 2 } },
            { text: '我不是人民币，做不到人人喜欢 🤷', score: { apathy: 10 } },
            { text: '特点这种东西是可以打造的 🎭', score: { lore: 10 } },
        ]
    },
    {
        id: 50,
        text: '你希望别人记住你的是什么？',
        options: [
            { text: '我取得的成就，站C位的资本 🏆', score: { ego: 10 } },
            { text: '我是个有趣的人，和我聊天很快乐 😄', score: { chaos: 8, vibe: 2 } },
            { text: '我对朋友很好，值得深交 🤝', score: { vibe: 10 } },
            { text: '没什么希望，被记住也累 🙈', score: { apathy: 10 } },
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
        // 灵活计分：每题10分×6题=60分满分，pct反映真实水平（0-100范围）
        const pct = Math.round((val / 60) * 10) * 10; // 映射到0-100%的十分位
        return { ...info, key, val, pct: Math.min(pct, 100) };
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