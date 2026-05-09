# -*- coding: utf-8 -*-
"""
玄学大师 Telegram Bot - 审核优化版 v3.1
支持：八字/姻缘/紫微/运势/吉时/取名

v3.0 → v3.1 修复与优化清单：
─────────────────────────────────────────────────────
【BUG修复】
1. lucky_color_map / favorable_dir 在 generate_yinyuan_detail 中未定义就引用 → 提升为模块级常量（原已有，但函数内未import）
2. AUX_DESC 字典在 generate_ziwei_detail 中定义后才用，但位置颠倒（在 result 中先引用）→ 移到使用前
3. generate_qiming_with_surname 中 names_lucky 循环里误用上一轮 renge 变量（未重新赋值）→ 修正为 strokes+g1
4. get_geju 中 geju_map 字典定义后从未使用，实为废代码 → 删除
5. WebhookHandler.do_GET 返回 "FortuneMaster FortuneMaster Bot"（重复词）→ 修正
6. PAID_KEYWORDS 触发逻辑缺失——定义了字典和函数但 handle() 中从未调用 → 在 handle() 入口加关键词检测
7. generate_today_fortune 中 lucky_color_map 引用了模块级变量（正常），
   但 generate_yinyuan_detail 末尾也引用 lucky_color_map、favorable_dir，
   而这两个变量在文件末尾才定义 → 统一移到顶部常量区
8. 合婚输入提示写"【阴历】生辰"，但实际不做阴历转换处理 → 去掉误导性提示
9. generate_liunian_dayun 感情运势一行使用链式布尔表达式产生歧义：
   '桃花年：' + ... or '需主动把握机缘'  →  用 or 前的字符串永远非空，导致 or 右侧永不生效 → 修正逻辑
10. calc_qiyun_age 逆推分支：prev_m = (month-2)%12+1 当 month=1 时得 12，当 month=2 时得 1，
    均正确；但 month=1 逆推 prev_m=12 后 days_to_jieqi 可能出现负数（day < jieqi_day 时）→ 加 abs()

【代码质量】
11. 重复的 import datetime 在函数体内 → 全部移到顶部
12. month_gz_idx 变量计算后从未使用 → 删除
13. diff 变量在 get_shishen 中计算后从未使用 → 删除
14. 付费关键词检测应在 handle() 中所有上下文状态判断之后、正常流程入口之前触发
15. 用户状态字典（bazi_context等）永不清理，长期运行内存泄漏 → 增加 TTL 超时清理机制
16. parse_gender 对"她"/"她们"等无法识别 → 扩展匹配词
17. Telegram parse_mode='Markdown' 对特殊字符（_ * [ `）敏感，名字中若含这些字符会报错 → 添加转义函数
18. handle() 中取名姓氏的判断条件过于宽松（任意文本都会进入姓氏流程）→ 加长度和纯汉字限制
"""

import os
import re
import time
import random
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import Update, ReplyKeyboardMarkup, BotCommand

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
if not TOKEN:
    raise RuntimeError("请设置环境变量 TELEGRAM_BOT_TOKEN")

tb = telebot.TeleBot(TOKEN, threaded=False)

# ============ 用户状态（含时间戳用于TTL清理）============
user_service   = {}   # uid -> svc
date_type_wait = {}   # uid -> {birth_info, name, gender, svc, ts}
bazi_context   = {}   # uid -> {name, birth_info, gender, ...}
yinyuan_context = {}  # uid -> {name, birth_info, gender, waiting_hehun}
qiming_context  = {}  # uid -> {name, birth_info, gender}

STATE_TTL = 600  # 10分钟无操作自动清除

def _clean_stale(store: dict):
    """清理超时的用户状态，防止内存泄漏"""
    now = time.time()
    stale = [k for k, v in store.items() if isinstance(v, dict) and now - v.get('ts', now) > STATE_TTL]
    for k in stale:
        store.pop(k, None)

def _stamp(d: dict) -> dict:
    """给状态字典附加时间戳"""
    d['ts'] = time.time()
    return d

# ============ Markdown 转义 ============
def md_escape(text: str) -> str:
    """转义 Telegram Markdown v1 敏感字符，防止发送失败"""
    for ch in ['_', '*', '[', '`']:
        text = text.replace(ch, '\\' + ch)
    return text

# ============ 关键词映射（VIP版全部开放，不再拦截付费） ============
# 关键词 -> 服务标识（按长度降序，防止短词覆盖长词）
PAID_KEYWORD_MAP = {
    '紫微斗数': 'ziwei',
    '流年大运': 'liunian',
    '合婚分析': 'hehun',
    '合八字':   'hehun',
    '流年':     'liunian',
    '大运':     'liunian',
    '合婚':     'hehun',
    '结婚':     'hehun',
    '取名':     'qiming',
    '起名':     'qiming',
    '紫微':     'ziwei',
}

def send_paid_template(chat_id, service_key):
    """兼容旧调用：VIP版改为提示功能已开放。"""

    if service_key == 'liunian':
        text = (
            "📈 *深度流年大运分析* 💰 $3U\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📋 *服务内容*\n"
            "  ✦ 个人大运排盘（阴阳顺逆精准起运）\n"
            "  ✦ 未来10年每年流年干支逐年详批\n"
            "  ✦ 每年事业 / 财运 / 感情 / 健康分项预测\n"
            "  ✦ 关键年份重大变化预警\n"
            "  ✦ 喜用神与流年五行碰撞分析\n"
            "  ✦ 个人专属改运化煞建议\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💳 *付款联系*\n"
            "客服 TG：@ok787768\n"
            "备注：流年大运\n\n"
            "⏰ 服务时间：09:00 - 21:00（GMT+8）\n"
            "✅ 付款后客服为您安排专属批命"
        )

    elif service_key == 'hehun':
        text = (
            "💑 *合婚深度分析* 💰 $5U\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📋 *服务内容*\n"
            "  ✦ 双方八字四柱完整对比解析\n"
            "  ✦ 生肖三合 / 六合 / 相冲 / 相刑全面判断\n"
            "  ✦ 日干五合 / 日支六合精准配对\n"
            "  ✦ 双方五行缺补互补深度分析\n"
            "  ✦ 婚后财运 / 感情 / 子嗣走势预测\n"
            "  ✦ 最佳婚期择吉 + 婚前化解建议\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💳 *付款联系*\n"
            "客服 TG：@ok787768\n"
            "备注：合婚分析\n\n"
            "⏰ 服务时间：09:00 - 21:00（GMT+8）\n"
            "✅ 付款后客服为您安排专属批命"
        )

    elif service_key == 'qiming':
        text = (
            "🍼 *高级八字取名服务* 💰 $6U\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📋 *服务内容*\n"
            "  ✦ 宝宝八字五行精准缺补分析\n"
            "  ✦ 喜用神专属汉字库推荐（形义音三维）\n"
            "  ✦ 三才五格（天格/人格/地格/总格/外格）\n"
            "     全套数理吉凶计算\n"
            "  ✦ 提供 10 个以上精选备选名字\n"
            "  ✦ 每个名字附完整寓意 + 五格评级说明\n"
            "  ✦ 结合姓氏最终优选推荐 + 忌用字提醒\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💳 *付款联系*\n"
            "客服 TG：@ok787768\n"
            "备注：取名服务\n\n"
            "⏰ 服务时间：09:00 - 21:00（GMT+8）\n"
            "✅ 付款后客服为您安排专属取名"
        )

    elif service_key == 'ziwei':
        text = (
            "✨ *紫微斗数详批* 💰 $8U\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📋 *服务内容*\n"
            "  ✦ 命宫主星精准安盘（含辅星煞星）\n"
            "  ✦ 十二宫位逐一深度详批\n"
            "     （命/财/官/夫妻/子女/迁移等）\n"
            "  ✦ 命主性格 / 天赋 / 事业方向精析\n"
            "  ✦ 大限流年运势完整预测\n"
            "  ✦ 感情婚姻 / 财富积累 / 健康风险分析\n"
            "  ✦ 专属开运改运 + 流年趋吉避凶指引\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💳 *付款联系*\n"
            "客服 TG：@ok787768\n"
            "备注：紫微斗数\n\n"
            "⏰ 服务时间：09:00 - 21:00（GMT+8）\n"
            "✅ 付款后客服为您安排专属详批"
        )

    else:
        return False

    text = (
        "✅ *VIP权益已生效*\n\n"
        "当前机器人已开放全部功能，无需额外付费。\n"
        "请直接在菜单中选择对应服务并输入生辰信息开始分析。"
    )
    tb.send_message(chat_id, text, parse_mode='Markdown')
    return True


def get_paid_key(text):
    """检查文本是否含付费关键词，返回 service_key 或 None"""
    for kw in sorted(PAID_KEYWORD_MAP.keys(), key=len, reverse=True):
        if kw in text:
            return PAID_KEYWORD_MAP[kw]
    return None

# ============ 全局辅助常量（提升到顶部，避免函数中引用时未定义）============
# [修复7] lucky_color_map / favorable_dir 原在文件末尾定义，但多个函数内直接引用
LUCKY_COLOR_MAP = {
    '木': '绿色、青色', '火': '红色、紫色', '土': '黄色、棕色',
    '金': '白色、金色', '水': '黑色、蓝色'
}
FAVORABLE_DIR = {
    '木': '东、东南', '火': '南', '土': '西南、中', '金': '西、西北', '水': '北'
}

# ============ 天干地支 ============
TIANGAN   = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
DIZHI     = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
SHENGXIAO = ['鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊', '猴', '鸡', '狗', '猪']

GAN_WUXING = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
              '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
ZHI_WUXING = {'子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土',
              '巳': '火', '午': '火', '未': '土', '申': '金', '酉': '金',
              '戌': '土', '亥': '水'}
ZHI_CANGGAN = {
    '子': ['壬', '癸'],        '丑': ['己', '癸', '辛'],
    '寅': ['甲', '丙', '戊'], '卯': ['甲', '乙'],
    '辰': ['戊', '乙', '癸'], '巳': ['丙', '戊', '庚'],
    '午': ['丙', '丁', '己'], '未': ['己', '丁', '乙'],
    '申': ['庚', '壬', '戊'], '酉': ['庚', '辛'],
    '戌': ['戊', '辛', '丁'], '亥': ['壬', '甲'],
}
WUXING_SHENG = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
WUXING_KE   = {'木': '土', '火': '金', '土': '水', '金': '木', '水': '火'}

# 被生反查表（谁生我）
WUXING_SHENG_BY = {v: k for k, v in WUXING_SHENG.items()}

# ============ 节气（月柱边界）============
JIEQI_MONTH = {
    1:  {'jie': '小寒', 'day': 6,  'zhi_idx': 1},
    2:  {'jie': '立春', 'day': 4,  'zhi_idx': 2},
    3:  {'jie': '惊蛰', 'day': 6,  'zhi_idx': 3},
    4:  {'jie': '清明', 'day': 5,  'zhi_idx': 4},
    5:  {'jie': '立夏', 'day': 6,  'zhi_idx': 5},
    6:  {'jie': '芒种', 'day': 6,  'zhi_idx': 6},
    7:  {'jie': '小暑', 'day': 7,  'zhi_idx': 7},
    8:  {'jie': '立秋', 'day': 7,  'zhi_idx': 8},
    9:  {'jie': '白露', 'day': 8,  'zhi_idx': 9},
    10: {'jie': '寒露', 'day': 8,  'zhi_idx': 10},
    11: {'jie': '立冬', 'day': 7,  'zhi_idx': 11},
    12: {'jie': '大雪', 'day': 7,  'zhi_idx': 0},
}

def get_lunar_month_zhi(solar_year, solar_month, solar_day):
    info = JIEQI_MONTH[solar_month]
    if solar_day >= info['day']:
        return DIZHI[info['zhi_idx']]
    prev_month = solar_month - 1 if solar_month > 1 else 12
    return DIZHI[JIEQI_MONTH[prev_month]['zhi_idx']]

def get_lunar_month_num(solar_year, solar_month, solar_day):
    zhi = get_lunar_month_zhi(solar_year, solar_month, solar_day)
    zhi_idx = DIZHI.index(zhi)
    return (zhi_idx - 1) % 12 + 1

# ============ 日期解析 ============
def parse_date_flexible(text):
    text = text.strip()
    patterns = [
        r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*[时:]?(\d{1,2})[:.](\d{1,2})',
        r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s+(\d{1,2})[:.](\d{1,2})',
        r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})时',
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
        r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            groups = m.groups()
            try:
                year  = int(groups[0]); month = int(groups[1]); day = int(groups[2])
                hour   = int(groups[3]) if len(groups) > 3 and groups[3] else 12
                minute = int(groups[4]) if len(groups) > 4 and groups[4] else 0
                leap = 29 if (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)) else 28
                mdays = [31, leap, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
                if 1800 <= year <= 2100 and 1 <= month <= 12 and 0 <= hour <= 23 and 0 <= minute <= 59:
                    if 1 <= day <= mdays[month - 1]:
                        return {'year': year, 'month': month, 'day': day,
                                'hour': hour, 'minute': minute}
            except Exception:
                continue
    return None

def days_from_civil(year, month, day):
    y   = year - (1 if month <= 2 else 0)
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    m   = month + (-3 if month > 2 else 9)
    doy = (153 * m + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468

def solar_to_lunar_info(year, month, day):
    try:
        from lunarcalendar import Converter, Solar
        l = Converter.Solar2Lunar(Solar(year, month, day))
        month_names = ['正月','二月','三月','四月','五月','六月',
                       '七月','八月','九月','十月','冬月','腊月']
        day_names = ['初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
                     '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
                     '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十']
        gan_idx = (l.year - 4) % 10
        zhi_idx = (l.year - 4) % 12
        ygz = TIANGAN[gan_idx] + DIZHI[zhi_idx]
        return {
            'year': l.year, 'month': l.month, 'day': l.day,
            'is_leap': getattr(l, 'isleap', False),
            'text': f'{ygz}年{month_names[l.month-1]}{day_names[l.day-1]}',
            'numeric': f'{l.year}年{"闰" if getattr(l,"isleap",False) else ""}{l.month}月{l.day}日'
        }
    except Exception:
        gan_idx = (year - 4) % 10
        zhi_idx = (year - 4) % 12
        ygz = TIANGAN[gan_idx] + DIZHI[zhi_idx]
        return {'year': year, 'month': month, 'day': day, 'is_leap': False,
                'text': f'{ygz}年{month}月{day}日', 'numeric': f'{year}年{month}月{day}日'}

def solar_to_lunar(year, month, day):
    return solar_to_lunar_info(year, month, day)['text']

def lunar_to_solar(year, month, day):
    try:
        from lunarcalendar import Converter, Lunar
        s = Converter.Lunar2Solar(Lunar(year, month, day))
        return {'year': s.year, 'month': s.month, 'day': s.day}
    except Exception:
        return {'year': year, 'month': month, 'day': day}

def parse_gender(text):
    # [修复16] 扩展女性关键词
    return '女' if any(w in text for w in ['女', '她', '女士', '小姐', '姐']) else '男'

# ============ 八字核心 ============
def get_zodiac(year):
    return SHENGXIAO[(year - 4) % 12]

def get_ganzhi_year(year):
    idx = (year - 4) % 60
    return TIANGAN[idx % 10] + DIZHI[idx % 12]

def get_ganzhi_month(year, month, day):
    lunar_m = get_lunar_month_num(year, month, day)
    year_gan_idx = TIANGAN.index(get_ganzhi_year(year)[0])
    month_gan_start = (year_gan_idx % 5) * 2 + 2
    month_gan_idx = (month_gan_start + lunar_m - 1) % 10
    month_zhi = get_lunar_month_zhi(year, month, day)
    return TIANGAN[month_gan_idx] + month_zhi

def get_ganzhi_day(year, month, day):
    base  = days_from_civil(1900, 1, 1)
    delta = days_from_civil(year, month, day) - base
    idx   = (delta + 40) % 60
    return TIANGAN[idx % 10] + DIZHI[idx % 12]

def get_ganzhi_hour(year, month, day, hour):
    hour_zhi_idx = ((hour + 1) // 2) % 12
    day_gz       = get_ganzhi_day(year, month, day)
    day_gan_idx  = TIANGAN.index(day_gz[0])
    hour_gan_start = (day_gan_idx % 5) * 2
    hour_gan_idx   = (hour_gan_start + hour_zhi_idx) % 10
    return TIANGAN[hour_gan_idx] + DIZHI[hour_zhi_idx]

def get_wuxing_full(year_gz, month_gz, day_gz, hour_gz):
    wx = {'木': 0.0, '火': 0.0, '土': 0.0, '金': 0.0, '水': 0.0}
    weights = [0.7, 0.5, 0.3]
    for gz in [year_gz, month_gz, day_gz, hour_gz]:
        if gz[0] in GAN_WUXING:
            wx[GAN_WUXING[gz[0]]] += 1.0
        for i, cg in enumerate(ZHI_CANGGAN.get(gz[1], [])):
            if cg in GAN_WUXING:
                wx[GAN_WUXING[cg]] += weights[i] if i < len(weights) else 0.2
    return wx

# ============ 冲合刑害 ============
GAN_HE    = {'甲':'己','乙':'庚','丙':'辛','丁':'壬','戊':'癸',
             '己':'甲','庚':'乙','辛':'丙','壬':'丁','癸':'戊'}
ZHI_LIUHE = {'子':'丑','寅':'亥','卯':'戌','辰':'酉','巳':'申','午':'未',
             '丑':'子','亥':'寅','戌':'卯','酉':'辰','申':'巳','未':'午'}
ZHI_SANHE = {frozenset(['申','子','辰']):'水局', frozenset(['寅','午','戌']):'火局',
             frozenset(['巳','酉','丑']):'金局', frozenset(['亥','卯','未']):'木局'}
ZHI_CHONG = {'子':'午','丑':'未','寅':'申','卯':'酉','辰':'戌','巳':'亥',
             '午':'子','未':'丑','申':'寅','酉':'卯','戌':'辰','亥':'巳'}
ZHI_XING  = {'寅':'巳','巳':'申','申':'寅',
             '丑':'戌','戌':'未','未':'丑',
             '子':'卯','卯':'子',
             '辰':'辰','午':'午','酉':'酉','亥':'亥'}
ZHI_HAI   = {'子':'未','丑':'午','寅':'巳','卯':'辰',
             '申':'亥','酉':'戌','亥':'申','戌':'酉',
             '辰':'卯','巳':'寅','午':'丑','未':'子'}

def analyze_chong_he(pillars):
    results = []
    gans = [gz[0] for gz in pillars]
    zhis = [gz[1] for gz in pillars]
    for i in range(len(gans)):
        for j in range(i+1, len(gans)):
            if GAN_HE.get(gans[i]) == gans[j]:
                results.append(f"{gans[i]}{gans[j]}天干相合")
    for i in range(len(zhis)):
        for j in range(i+1, len(zhis)):
            if ZHI_LIUHE.get(zhis[i]) == zhis[j]:
                results.append(f"{zhis[i]}{zhis[j]}六合")
            if ZHI_CHONG.get(zhis[i]) == zhis[j]:
                results.append(f"{zhis[i]}{zhis[j]}相冲⚡")
            if ZHI_XING.get(zhis[i]) == zhis[j] and zhis[i] != zhis[j]:
                results.append(f"{zhis[i]}{zhis[j]}相刑⚠️")
            if ZHI_HAI.get(zhis[i]) == zhis[j]:
                results.append(f"{zhis[i]}{zhis[j]}相害")
    zhi_set = set(zhis)
    for combo, name in ZHI_SANHE.items():
        if combo.issubset(zhi_set):
            results.append(f"三合{name}✨")
    # 自刑
    for z in zhis:
        if zhis.count(z) >= 2 and ZHI_XING.get(z) == z:
            results.append(f"{z}{z}自刑⚠️")
            break
    return results if results else ["四柱冲合平和"]

# ============ 日主旺衰 ============
def analyze_rizhu_wangshui(day_gan, month_gz, all_gz_list):
    month_zhi = month_gz[1]
    day_wx    = GAN_WUXING.get(day_gan, '土')
    season_strength = {
        ('木','寅'):True,('木','卯'):True,
        ('火','巳'):True,('火','午'):True,
        ('土','辰'):True,('土','戌'):True,('土','丑'):True,('土','未'):True,
        ('金','申'):True,('金','酉'):True,
        ('水','亥'):True,('水','子'):True,
    }
    de_ling   = season_strength.get((day_wx, month_zhi), False)
    day_zhi_wx = ZHI_WUXING.get(all_gz_list[2][1], '土')
    sheng_map = {'木':'水','火':'木','土':'火','金':'土','水':'金'}
    de_di     = (day_wx == day_zhi_wx) or (sheng_map.get(day_wx,'') == day_zhi_wx)
    helper    = 0.0
    for gz in all_gz_list:
        g_wx = GAN_WUXING.get(gz[0], '')
        if g_wx == day_wx:          helper += 1.0
        elif WUXING_SHENG.get(g_wx,'') == day_wx: helper += 0.5
        for cg in ZHI_CANGGAN.get(gz[1], []):
            cg_wx = GAN_WUXING.get(cg, '')
            if cg_wx == day_wx:     helper += 0.3
    de_shi = helper >= 3
    if de_ling and (de_di or de_shi):   strong = '身旺'
    elif not de_ling and not de_di and not de_shi: strong = '身弱'
    else:                               strong = '中和'
    return {'de_ling':'得令' if de_ling else '失令',
            'de_di':  '得地' if de_di   else '失地',
            'de_shi': '得势' if de_shi  else '失势',
            'strong': strong}

def analyze_xiyongshen(wuxing_full, rizhu_strong, day_wx):
    ke_day    = WUXING_KE.get(day_wx, '土')
    sheng_day = WUXING_SHENG_BY.get(day_wx, '土')
    xie_day   = WUXING_SHENG.get(day_wx, '火')
    if   rizhu_strong == '身旺': xi = [ke_day, xie_day]
    elif rizhu_strong == '身弱': xi = [sheng_day, day_wx]
    else:
        min_wx = min(wuxing_full, key=wuxing_full.get)
        xi = [min_wx, WUXING_SHENG.get(min_wx, '木')]
    return xi

# ============ 格局判定 ============
def get_geju(month_zhi, day_gan, all_gans):
    # [修复4] 删除从未使用的 geju_map 废代码
    day_wx         = GAN_WUXING.get(day_gan, '土')
    yue_ling_cg    = ZHI_CANGGAN.get(month_zhi, [])
    for cg in yue_ling_cg:
        cg_wx = GAN_WUXING.get(cg, '')
        if not cg_wx or cg not in all_gans:
            continue
        same_yy = (TIANGAN.index(cg) % 2) == (TIANGAN.index(day_gan) % 2)
        if WUXING_KE.get(cg_wx,'') == day_wx:
            return '七杀格' if same_yy else '正官格'
        if WUXING_KE.get(day_wx,'') == cg_wx:
            return '偏财格' if same_yy else '正财格'
        if WUXING_SHENG.get(cg_wx,'') == day_wx:
            return '偏印格' if same_yy else '正印格'
        if WUXING_SHENG.get(day_wx,'') == cg_wx:
            return '伤官格' if same_yy else '食神格'
    base_wx = ZHI_WUXING.get(month_zhi,'土')
    if WUXING_KE.get(base_wx,'') == day_wx: return '正官格'
    if WUXING_KE.get(day_wx,'') == base_wx: return '正财格'
    if WUXING_SHENG.get(base_wx,'') == day_wx: return '正印格'
    if WUXING_SHENG.get(day_wx,'') == base_wx: return '食神格'
    return '建禄格'

# ============ 调候用神 ============
TIAOHOU = {
    ('甲','寅'):"丙火温暖，癸水滋润",('甲','卯'):"癸水为主，庚金辅之",
    ('甲','辰'):"庚金劈甲，壬水淘洗",('甲','巳'):"癸水为主，庚金辅之",
    ('甲','午'):"癸水优先，庚金次之",('甲','未'):"癸水为主，丙火辅之",
    ('甲','申'):"丁火克金，庚金相辅",('甲','酉'):"丁火为主，庚金次之",
    ('甲','戌'):"壬水为主，甲木辅之",('甲','亥'):"庚金优先，丁火次之",
    ('甲','子'):"丁火解冻，庚金辅之",('甲','丑'):"丙火温暖，庚金辅之",
    ('乙','寅'):"丙火优先，癸水辅之",('乙','卯'):"丙火为主，癸水次之",
    ('丙','巳'):"壬水制火为先，庚金辅之",('丙','午'):"壬水调候，庚金辅之",
    ('丁','巳'):"甲木生丁，庚金辅之",('丁','午'):"壬水克火，甲木辅之",
    ('戊','午'):"壬水为先，甲木辅之",('戊','巳'):"甲木疏土，壬水润之",
    ('己','午'):"癸水调候，丙火辅之",('己','巳'):"癸水为主，丙火次之",
    ('庚','申'):"丁火制金，甲木辅之",('庚','酉'):"丁火为主，甲木次之",
    ('辛','申'):"壬水淘金，甲木疏之",('辛','酉'):"壬水为主，甲木辅之",
    ('壬','亥'):"戊土制水，丙火温暖",('壬','子'):"戊土为先，丙火次之",
    ('癸','亥'):"庚辛生水，丙火解冻",('癸','子'):"丙火解冻，辛金生水",
}

# ============ 十神 ============
def get_shishen(gan, day_gan):
    # [修复13] 删除从未使用的 diff 变量
    if gan not in TIANGAN or day_gan not in TIANGAN:
        return ''
    g_idx, d_idx = TIANGAN.index(gan), TIANGAN.index(day_gan)
    same_yy = (g_idx % 2) == (d_idx % 2)
    wx_d, wx_g = GAN_WUXING[day_gan], GAN_WUXING[gan]
    if wx_g == wx_d:                             return '比肩' if same_yy else '劫财'
    if WUXING_SHENG.get(wx_d,'') == wx_g:        return '食神' if same_yy else '伤官'
    if WUXING_KE.get(wx_d,'') == wx_g:           return '偏财' if same_yy else '正财'
    if WUXING_KE.get(wx_g,'') == wx_d:           return '七杀' if same_yy else '正官'
    if WUXING_SHENG.get(wx_g,'') == wx_d:        return '偏印' if same_yy else '正印'
    return ''

SHISHEN_CHARS = {
    '比肩':'独立自主、坚韧不拔、有领导力、竞争心强',
    '劫财':'冲动豪爽、热情好胜、善于社交',
    '食神':'温和包容、才华横溢、思维活跃、善于表达',
    '伤官':'聪明机智、创意丰富、叛逆个性、表现欲强',
    '偏财':'慷慨灵活、理财能力强、投机心理',
    '正财':'稳重务实、勤劳节俭、责任心强',
    '七杀':'果断刚毅、执行力强、魄力十足',
    '正官':'正直稳重、遵纪守法、有责任感',
    '偏印':'聪慧敏感、领悟力强、思维独特',
    '正印':'智慧善良、仁慈宽厚、善于学习',
}

# ============ 起运年龄 ============
def calc_qiyun_age(year, month, day, gender):
    year_gan   = get_ganzhi_year(year)[0]
    year_yy    = '阳' if TIANGAN.index(year_gan) % 2 == 0 else '阴'
    is_forward = (year_yy == '阳' and gender == '男') or (year_yy == '阴' and gender == '女')
    jieqi_day  = JIEQI_MONTH[month]['day']
    if is_forward:
        if day < jieqi_day:
            days_gap = jieqi_day - day
        else:
            next_m = month % 12 + 1
            days_gap = 30 - day + JIEQI_MONTH[next_m]['day']
    else:
        if day >= jieqi_day:
            days_gap = day - jieqi_day
        else:
            prev_m   = (month - 2) % 12 + 1
            # [修复10] 用 abs() 防负数
            days_gap = abs(day + 30 - JIEQI_MONTH[prev_m]['day'])
    return max(1, round(days_gap / 3))

# ============ 八字分析 ============
def generate_bazi_detail(name, birth_info, gender, date_type='阳历', lunar_date=''):
    year, month, day, hour = birth_info['year'], birth_info['month'], birth_info['day'], birth_info['hour']
    year_gz  = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz   = get_ganzhi_day(year, month, day)
    hour_gz  = get_ganzhi_hour(year, month, day, hour)
    pillars  = [year_gz, month_gz, day_gz, hour_gz]
    all_gans = [gz[0] for gz in pillars]
    year_gan, year_zhi   = year_gz[0], year_gz[1]
    month_gan, month_zhi = month_gz[0], month_gz[1]
    day_gan,   day_zhi   = day_gz[0],   day_gz[1]
    hour_gan,  hour_zhi  = hour_gz[0],  hour_gz[1]

    wuxing_full  = get_wuxing_full(*pillars)
    wuxing_disp  = {k: round(v, 1) for k, v in wuxing_full.items()}
    rizhu_info   = analyze_rizhu_wangshui(day_gan, month_gz, pillars)
    rizhu_strong = rizhu_info['strong']
    day_wx       = GAN_WUXING.get(day_gan, '土')
    geju         = get_geju(month_zhi, day_gan, all_gans)
    xiyong       = analyze_xiyongshen(wuxing_full, rizhu_strong, day_wx)
    tiaohou_key  = (day_gan, month_zhi)
    tiaohou_ys   = TIAOHOU.get(tiaohou_key, "以喜用神为主")
    year_ss  = get_shishen(year_gan, day_gan)
    month_ss = get_shishen(month_gan, day_gan)
    hour_ss  = get_shishen(hour_gan, day_gan)
    chong_he = analyze_chong_he(pillars)
    zodiac   = get_zodiac(year)
    qiyun_age  = calc_qiyun_age(year, month, day, gender)
    qiyun_year = year + qiyun_age
    lucky_dir  = FAVORABLE_DIR.get(xiyong[0], '东')
    lucky_color = LUCKY_COLOR_MAP.get(xiyong[0], '白色')

    if '官' in geju or '杀' in geju: career_dir = "行政管理、公务员、企业管理、法律"
    elif '财' in geju:               career_dir = "商业贸易、金融投资、财务管理"
    elif '印' in geju:               career_dir = "教育培训、科研学术、文化传媒"
    elif '食' in geju or '伤' in geju: career_dir = "艺术创作、演艺设计、技术研发"
    else:                            career_dir = "综合发展，适合多领域尝试"

    current_year = datetime.now().year
    liunian_gz   = get_ganzhi_year(current_year)
    ln_wx        = GAN_WUXING.get(liunian_gz[0], '土')
    if   ln_wx == xiyong[0]:                       liunian_tip = "流年逢喜用，事业财运有利"
    elif WUXING_SHENG.get(ln_wx,'') == xiyong[0]:  liunian_tip = "流年相生，整体平稳顺遂"
    elif WUXING_KE.get(ln_wx,'') == day_wx:         liunian_tip = "流年克日主，需注意健康与稳定"
    else:                                           liunian_tip = "流年平和，稳步经营"

    base         = 70 + (10 if rizhu_strong == '身旺' else 0)
    if   ln_wx == xiyong[0]:                       base += 10
    elif WUXING_SHENG.get(ln_wx,'') == xiyong[0]:  base += 5
    career_score = min(99, base + (5 if '官' in geju or '杀' in geju else 0))
    wealth_score = min(99, base + (5 if '财' in geju else 0))
    love_score   = min(99, base + random.randint(-3, 5))
    health_score = min(99, base + (5 if not any('冲' in c for c in chong_he) else -5))

    safe_name = md_escape(name)
    result = f"""🔮 **{safe_name} 完整八字命理分析**

━━━━━━━━━━━━━━━━━━━━━━
📥 基本信息
• 出生：{year}年{month}月{day}日 {hour:02d}:00
• 性别：{gender} ｜ 生肖：{zodiac}
• 阳历：{year}年{month}月{day}日
• 阴历：{lunar_date if lunar_date else '（未提供）'}

🗓️ 四柱八字
| 年柱 | 月柱 | 日柱 | 时柱 |
| {year_gz} | {month_gz} | {day_gz} | {hour_gz} |
| {year_ss or '—'} | {month_ss or '—'} | 日主 | {hour_ss or '—'} |

⚖️ 五行配置（含藏干权重）
• 木：{wuxing_disp['木']} │ 火：{wuxing_disp['火']} │ 土：{wuxing_disp['土']}
• 金：{wuxing_disp['金']} │ 水：{wuxing_disp['水']}

🔗 冲合刑害
{chr(10).join(f'• {c}' for c in chong_he)}

⏰ 日主旺衰（滴天髓）
• 得令：{rizhu_info['de_ling']} ｜ 得地：{rizhu_info['de_di']} ｜ 得势：{rizhu_info['de_shi']}
• 日主强弱：{rizhu_strong}（日干：{day_gan} {day_wx}）

📊 格局判定（子平真诠）
• 格局：{geju}
• 喜用神：{xiyong[0]}、{xiyong[1]}
• 调候用神：{tiaohou_ys}（穷通宝鉴）

💎 十神性格分析
• 年柱{year_ss}（{SHISHEN_CHARS.get(year_ss,'')}）
• 月柱{month_ss}（{SHISHEN_CHARS.get(month_ss,'')}）
• 时柱{hour_ss}（{SHISHEN_CHARS.get(hour_ss,'')}）

💼 事业：{career_score}% ｜ 💰 财运：{wealth_score}%
💘 感情：{love_score}%  ｜ 🏃 健康：{health_score}%

📈 事业方向与行业建议
• 适合行业：{career_dir}
• 吉祥方位：{lucky_dir}
• 幸运颜色：{lucky_color}

⏳ 大运起运
• 起运年龄：约{qiyun_age}岁（{qiyun_year}年起）

🪯 流年（{current_year}年 {liunian_gz}年）
• {liunian_tip}

━━━━━━━━━━━━━━━━━━━━━━
📌 *进阶服务入口*\n💡 如需深度流年分析（未来10年每年详细运势），可直接回复「流年」或「大运」"""
    return result, {}

# ============ 姻缘测算 ============
def generate_yinyuan_detail(name, birth_info, gender):
    year, month, day = birth_info['year'], birth_info['month'], birth_info['day']
    hour   = birth_info.get('hour', 12)
    minute = birth_info.get('minute', 0)
    year_gz  = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz   = get_ganzhi_day(year, month, day)
    hour_gz  = get_ganzhi_hour(year, month, day, hour)
    zodiac   = get_zodiac(year)
    lunar_info = solar_to_lunar_info(year, month, day)
    day_gan, day_zhi = day_gz[0], day_gz[1]
    day_wx   = GAN_WUXING.get(day_gan, '土')
    wuxing_full = get_wuxing_full(year_gz, month_gz, day_gz, hour_gz)
    rizhu_info  = analyze_rizhu_wangshui(day_gan, month_gz, [year_gz, month_gz, day_gz, hour_gz])
    xiyong = analyze_xiyongshen(wuxing_full, rizhu_info['strong'], day_wx)

    if gender == '男':
        fuke_wx   = WUXING_KE.get(day_wx, '土')
        fuke_star = f"正财星（{fuke_wx}行）"
    else:
        fuke_wx   = next((k for k, v in WUXING_KE.items() if v == day_wx), '金')
        fuke_star = f"正官星（{fuke_wx}行）"

    spouse_zhi_desc = {
        '子': "配偶温和聪慧，夫妻宫主沟通，宜坦诚表达",
        '丑': "配偶务实稳重，适合同频成长型伴侣",
        '寅': "夫妻宫主动热情，先热后稳，需经营耐心",
        '卯': "夫妻宫温柔细腻，感情细水长流",
        '辰': "配偶重承诺，婚后以家庭建设为核心",
        '巳': "夫妻宫热烈吸引，需防情绪化争执",
        '午': "夫妻宫外向活跃，宜建立共同目标",
        '未': "配偶顾家重情，重生活品质",
        '申': "夫妻宫理性务实，适合价值观一致的伴侣",
        '酉': "夫妻宫重仪式感，关系中需要被肯定",
        '戌': "配偶重担当，适合晚些定婚更稳",
        '亥': "夫妻宫包容度高，但要避免过度迁就",
    }

    taohua_map = {'子':'酉','午':'卯','卯':'子','酉':'午',
                  '寅':'亥','申':'巳','巳':'申','亥':'寅',
                  '辰':'酉','戌':'卯','丑':'午','未':'子'}
    year_zhi   = year_gz[1]
    taohua_zhi = taohua_map.get(year_zhi, day_zhi)
    has_taohua = taohua_zhi in [day_gz[1], month_gz[1], hour_gz[1]]

    sanhe_map  = {'子':['申','辰'],'丑':['巳','酉'],'寅':['午','戌'],
                  '卯':['亥','未'],'辰':['申','子'],'巳':['酉','丑'],
                  '午':['寅','戌'],'未':['亥','卯'],'申':['子','辰'],
                  '酉':['巳','丑'],'戌':['午','寅'],'亥':['卯','未']}
    sanhe_zhis = sanhe_map.get(year_zhi, [])
    liuhe_zhi  = ZHI_LIUHE.get(year_zhi, '')
    best_zodiac = [SHENGXIAO[DIZHI.index(z)] for z in sanhe_zhis if z in DIZHI]
    if liuhe_zhi and liuhe_zhi in DIZHI:
        best_zodiac.insert(0, SHENGXIAO[DIZHI.index(liuhe_zhi)])
    best_zodiac = best_zodiac[:3]

    taohua_base = 65 + (20 if has_taohua else 0) + (5 if xiyong[0] in ['木','火'] else 0)
    taohua_strength = min(95, taohua_base)

    current_year = datetime.now().year
    good_years   = [y for i in range(1,9) if (y := current_year+i) and
                    GAN_WUXING.get(get_ganzhi_year(y)[0],'') in [fuke_wx, WUXING_SHENG_BY.get(fuke_wx,'')]]
    if len(good_years) < 2:
        good_years = [current_year+2, current_year+4]

    love_style = "主动积极，追求浪漫，重视外貌与内涵" if gender == '男' else "含蓄内敛，期待被追求，重视安全感"
    ideal_type = "温柔贤淑、善解人意、内外兼修"       if gender == '男' else "成熟稳重、有责任感、细心体贴"
    if   taohua_strength > 80: advice = "桃花旺盛，建议理性选择，避免冲动决定"
    elif taohua_strength > 60: advice = "桃花平稳，建议主动出击，把握机会"
    else:                      advice = "桃花较弱，建议扩大社交圈，增加认识新人的机会"

    safe_name = md_escape(name)
    result = f"""💕 **{safe_name} 姻缘深度分析**

━━━━━━━━━━━━━━━━━━━━━━
📥 基础信息
• 出生：{year}年{month}月{day}日 {hour:02d}:{minute:02d}
• 性别：{gender} ｜ 生肖：{zodiac}
• 阴历：{lunar_info['text']}

💑 配偶星与配偶宫
• 配偶星：{fuke_star}
• 配偶宫：日支{day_zhi}（{spouse_zhi_desc.get(day_zhi,'宜坦诚沟通')}）
• 桃花星：{'命中有桃花（' + taohua_zhi + '）' if has_taohua else '桃花在外，需主动扩圈'}
• 桃花运强度：{taohua_strength}%

🐾 最佳配对生肖
{chr(10).join(f'• {z}：与{zodiac}三合/六合，缘分深厚' for z in best_zodiac) or '• 以日柱相合为准'}

🏠 配偶宫详解
{spouse_zhi_desc.get(day_zhi,'夫妻宫平稳，重在沟通与信任')}

☯️ 性格与恋爱观
• 恋爱风格：{love_style}
• 理想对象：{ideal_type}

📅 婚恋时机
• 最佳婚期：{', '.join(map(str, good_years[:3]))}年
• 建议：{advice}

🎈 提升桃花运建议
• 喜用五行：{xiyong[0]}（对应{LUCKY_COLOR_MAP.get(xiyong[0],'白色')}）
• 佩戴：{xiyong[0]}属性宝石
• 方位：{FAVORABLE_DIR.get(xiyong[0],'东南')}方

━━━━━━━━━━━━━━━━━━━━━━
📌 *进阶服务入口*\n💡 如需双方八字合婚详细分析，可直接回复「合婚」"""
    return result

# ============ 紫微斗数 ============
def generate_ziwei_detail(name, birth_info, gender, date_type='阳历', original_input=None):
    year, month, day = birth_info['year'], birth_info['month'], birth_info['day']
    hour   = birth_info.get('hour', 12)
    minute = birth_info.get('minute', 0)
    lunar_info    = solar_to_lunar_info(year, month, day)
    lunar_month   = lunar_info['month']
    hour_zhi_idx  = ((hour + 1) // 2) % 12
    mingong_zhi_idx = (2 + lunar_month - 1 - hour_zhi_idx) % 12
    mingong_zhi   = DIZHI[mingong_zhi_idx]
    ziwei_shift   = lunar_info['day'] % 12
    ziwei_zhi_idx = (mingong_zhi_idx + ziwei_shift) % 12

    MAIN_STARS = ['紫微','天机','太阳','武曲','天同','廉贞',
                  '天府','太阴','贪狼','巨门','天相','天梁','七杀','破军']
    MAIN_STAR_DESC = {
        '紫微':'帝王星，象征尊贵与领导力，适合管理职位',
        '天机':'智慧星，象征机敏与谋略，适合策划参谋',
        '太阳':'光明星，象征热情与事业，适合公众服务',
        '武曲':'财星，象征刚毅与决断，适合金融商贸',
        '天同':'福星，象征温和与享受，适合服务业',
        '廉贞':'次桃花星，象征清廉刚直，多才艺',
        '天府':'财库星，象征稳重保守，宜稳健投资',
        '太阴':'田宅星，象征温柔内敛，感情细腻',
        '贪狼':'欲望星，象征才能多元，宜艺术',
        '巨门':'是非星，象征口才极佳，宜传播法律',
        '天相':'辅弼星，象征忠诚助人，宜公职',
        '天梁':'寿星，象征正直仁厚，宜医疗教育',
        '七杀':'将星，象征威猛冲动，宜军警创业',
        '破军':'耗星，象征开创变动，宜改革突破',
    }
    main_star      = MAIN_STARS[ziwei_zhi_idx % len(MAIN_STARS)]
    main_star_desc = MAIN_STAR_DESC.get(main_star, '多才多艺，命运多变')

    # [修复2] AUX_DESC 必须在 result 字符串使用前定义
    AUXILIARY_STARS = ['左辅','右弼','文昌','文曲','天魁','天钺','火星','铃星','擎羊','陀罗']
    AUX_DESC = {
        '左辅':'利于得贵人相助，人缘佳',
        '右弼':'协调配合能力强，善辅助他人',
        '文昌':'有利学业功名，思维清晰',
        '文曲':'才艺出众，口才好',
        '天魁':'贵人运强，逢凶化吉',
        '天钺':'权贵助力，地位稳固',
        '火星':'性格急躁，冲劲十足',
        '铃星':'暗中积累，爆发力强',
        '擎羊':'是非较多，需防外伤',
        '陀罗':'遇事多困扰，需耐心化解',
    }
    aux_idx  = (month + day + hour_zhi_idx) % len(AUXILIARY_STARS)
    aux_star = AUXILIARY_STARS[aux_idx]

    if main_star in ['紫微','天府','七杀','武曲']:
        career_desc = "适合管理、金融、创业，领导才能突出"
        wealth_desc = "财运较好，善于理财，正财偏财皆有"
    elif main_star in ['天机','巨门']:
        career_desc = "适合策划、传播、法律、教育等脑力工作"
        wealth_desc = "财运平稳，靠技能积累财富"
    elif main_star in ['太阳','天梁','天相']:
        career_desc = "适合公职、医疗、教育、社会服务"
        wealth_desc = "财运稳健，重视储蓄"
    else:
        career_desc = "适合艺术、服务业、自由职业"
        wealth_desc = "财运起伏，宜稳健理财"

    zodiac = get_zodiac(year)
    safe_name = md_escape(name)
    result = f"""🔮 **{safe_name} 紫微斗数命宫分析**

━━━━━━━━━━━━━━━━━━━━━━
📥 基础信息
• 出生：{year}年{month}月{day}日 {hour:02d}:{minute:02d}
• 性别：{gender} ｜ 生肖：{zodiac}
• 农历：{lunar_info['text']}

🪐 命宫主星（命宫：{mingong_zhi}宫）
• 主星：{main_star}
• 星性：{main_star_desc}
• 辅星：{aux_star}（{AUX_DESC.get(aux_star,'')}）

🏠 十二宫位概览
• 命宫（{mingong_zhi}）：主星{main_star}，主本人性格命运
• 夫妻宫（{DIZHI[(mingong_zhi_idx+5)%12]}）：婚恋与配偶缘分
• 财帛宫（{DIZHI[(mingong_zhi_idx+4)%12]}）：财运与理财能力
• 官禄宫（{DIZHI[(mingong_zhi_idx+9)%12]}）：事业与功名

💼 事业分析
• {career_desc}

💰 财运分析
• {wealth_desc}

🎭 性格特质
• {main_star_desc.split('，')[1] if '，' in main_star_desc else main_star_desc}

━━━━━━━━━━━━━━━━━━━━━━
🙏 详批需结合大运流年综合分析"""
    return result

# ============ 今日运势 ============
def generate_today_fortune(name, birth_info, gender):
    today_dt = datetime.now()
    today    = today_dt.strftime("%Y年%m月%d日")
    year, month, day = birth_info['year'], birth_info['month'], birth_info['day']
    hour  = birth_info.get('hour', 12)
    year_gz  = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz   = get_ganzhi_day(year, month, day)
    hour_gz  = get_ganzhi_hour(year, month, day, hour)
    day_gan, day_zhi = day_gz[0], day_gz[1]
    day_wx   = GAN_WUXING.get(day_gan, '土')
    wuxing_full = get_wuxing_full(year_gz, month_gz, day_gz, hour_gz)
    rizhu_info  = analyze_rizhu_wangshui(day_gan, month_gz, [year_gz, month_gz, day_gz, hour_gz])
    xiyong = analyze_xiyongshen(wuxing_full, rizhu_info['strong'], day_wx)

    today_year  = today_dt.year
    today_gz    = get_ganzhi_year(today_year)
    today_wx    = GAN_WUXING.get(today_gz[0], '土')

    sanhe_zhi = {'子':['申','辰'],'午':['寅','戌'],'卯':['亥','未'],'酉':['巳','丑'],
                 '寅':['午','戌'],'申':['子','辰'],'巳':['酉','丑'],'亥':['卯','未'],
                 '辰':['子','申'],'戌':['午','寅'],'丑':['巳','酉'],'未':['亥','卯']}
    good_zhi_list = list(sanhe_zhi.get(day_zhi, []))
    lh = ZHI_LIUHE.get(day_zhi, '')
    if lh: good_zhi_list.append(lh)
    ZHI_TO_HOUR = {'子':'23:00-01:00','丑':'01:00-03:00','寅':'03:00-05:00',
                   '卯':'05:00-07:00','辰':'07:00-09:00','巳':'09:00-11:00',
                   '午':'11:00-13:00','未':'13:00-15:00','申':'15:00-17:00',
                   '酉':'17:00-19:00','戌':'19:00-21:00','亥':'21:00-23:00'}
    good_hours = [ZHI_TO_HOUR[z] for z in good_zhi_list if z in ZHI_TO_HOUR] or ['09:00-11:00','15:00-17:00']

    jianchu_map = ['建','除','满','平','定','执','破','危','成','收','开','闭']
    today_day_gz   = get_ganzhi_day(today_dt.year, today_dt.month, today_dt.day)
    today_zhi_idx  = DIZHI.index(today_day_gz[1])
    jianchu = jianchu_map[today_zhi_idx % 12]
    yi_ji = {
        '建':(['出行','求职','立志'],['动土','安床','嫁娶']),
        '除':(['求医','扫舍','沐浴'],['嫁娶','开市','移居']),
        '满':(['开市','纳财','入宅'],['求医','诉讼','出行']),
        '平':(['出行','会友','洽谈'],['嫁娶','入宅','安葬']),
        '定':(['祭祀','会亲','订盟'],['出行','破土','诉讼']),
        '执':(['纳采','安床','入仓'],['开市','出行','嫁娶']),
        '破':(['求医','拆卸','解除'],['出行','嫁娶','开市']),
        '危':(['祭祀','祈福','求医'],['出行','开市','嫁娶']),
        '成':(['嫁娶','开市','立约'],['诉讼','动土','出行']),
        '收':(['纳财','收货','开仓'],['嫁娶','出行','开市']),
        '开':(['开市','出行','入宅'],['安葬','破土','诉讼']),
        '闭':(['安葬','立券','纳财'],['嫁娶','出行','开市']),
    }
    yi, ji = yi_ji.get(jianchu, (['出行','洽谈'],['动土','破坏']))

    base   = 72
    if   today_wx == xiyong[0]:                       base += 12
    elif WUXING_SHENG.get(today_wx,'') == xiyong[0]:  base += 6
    elif WUXING_KE.get(today_wx,'') == day_wx:         base -= 8
    overall = min(98, max(55, base))
    career  = min(98, overall + random.randint(-5, 5))
    wealth  = min(98, overall + random.randint(-5, 5))
    love    = min(98, overall + random.randint(-5, 5))
    health  = min(98, overall + random.randint(-3, 7))
    lucky_dir = FAVORABLE_DIR.get(xiyong[0], '东')

    safe_name = md_escape(name)
    result = f"""🌤️ **{safe_name} 今日运势详解**

━━━━━━━━━━━━━━━━━━━━━━
📆 {today} ｜ 今日日辰：{today_day_gz} ｜ 日建：{jianchu}日
八字：{year_gz} {month_gz} {day_gz} {hour_gz}

🎰 综合运势：{overall}%
💼事业 {career}% ｜ 💰财运 {wealth}% ｜ 💞感情 {love}% ｜ 🏃健康 {health}%

🖲 五行磁场
• 今日天干五行：{today_wx}
• 喜用神：{xiyong[0]}、{xiyong[1]}
• 幸运方位：{lucky_dir}

🏮 今日吉时
{chr(10).join(f'• {h}' for h in good_hours[:3])}

☯️ 今日宜忌（{jianchu}日）
• 宜：{', '.join(yi)}
• 忌：{', '.join(ji)}

🧭 幸运元素
• 颜色：{LUCKY_COLOR_MAP.get(xiyong[0],'白色')}
• 数字：{TIANGAN.index(day_gz[0])+1}, {DIZHI.index(day_gz[1])+1}

━━━━━━━━━━━━━━━━━━━━━━"""
    return result

# ============ 取名分析（初步）============
def generate_qiming_detail(name, birth_info, gender):
    year, month, day = birth_info['year'], birth_info['month'], birth_info['day']
    hour = birth_info.get('hour', 12)
    year_gz  = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz   = get_ganzhi_day(year, month, day)
    hour_gz  = get_ganzhi_hour(year, month, day, hour)
    wuxing_full = get_wuxing_full(year_gz, month_gz, day_gz, hour_gz)
    day_gan = day_gz[0]
    day_wx  = GAN_WUXING.get(day_gan, '土')
    rizhu_info = analyze_rizhu_wangshui(day_gan, month_gz, [year_gz, month_gz, day_gz, hour_gz])
    xiyong = analyze_xiyongshen(wuxing_full, rizhu_info['strong'], day_wx)

    RECOMMENDED_CHARS = {
        '木': (['梓','涵','林','森','萱','菲','岚','桐','楠','榆'], '木能生火，寓意生机勃发、向上成长'),
        '火': (['炎','烨','灿','耀','炅','旭','晗','曦','骞','熠'], '火能生土，寓意光明炽热、照亮前路'),
        '土': (['垚','磊','怡','岩','岱','坤','城','轩','钧','嵩'], '土能生金，寓意稳重厚德、承载万物'),
        '金': (['鑫','铭','锋','锐','铖','钰','锦','铎','镇','钧'], '金能生水，寓意刚健锐利、锋芒毕露'),
        '水': (['涛','浩','瀚','澜','泉','泽','沐','沛','浚','潇'], '水能生木，寓意聪慧灵动、润物无声'),
    }
    chars, meaning = RECOMMENDED_CHARS.get(xiyong[0], RECOMMENDED_CHARS['水'])
    LUCKY_GE_LIST  = [1,3,5,6,7,8,11,13,15,16,17,18,21,23,24,25,29,31,32,33,35,37,38,39,41,45,47,48]

    safe_name = md_escape(name)
    result = f"""🍼 **{safe_name} 取名深度分析**

━━━━━━━━━━━━━━━━━━━━━━
🧮 宝宝八字
• 出生：{year}年{month}月{day}日 {hour}:00
• 四柱：{year_gz} {month_gz} {day_gz} {hour_gz}
• 日主：{day_gan}（{day_wx}）{rizhu_info['strong']}

⚖️ 五行缺补分析
• 木：{round(wuxing_full['木'],1)} │ 火：{round(wuxing_full['火'],1)} │ 土：{round(wuxing_full['土'],1)}
• 金：{round(wuxing_full['金'],1)} │ 水：{round(wuxing_full['水'],1)}
• 喜用神：{xiyong[0]}（补{xiyong[0]}）、{xiyong[1]}（辅{xiyong[1]}）

🔤 推荐用字（按喜用神 {xiyong[0]} 行）
{chr(10).join(f'• {c}' for c in chars[:6])}

💡 取名原则
• {meaning}
• 推荐笔画吉数：{', '.join(map(str,LUCKY_GE_LIST[:8]))}…
• 名字三才五格需结合姓氏综合分析

━━━━━━━━━━━━━━━━━━━━━━
📌 请回复「姓氏」进行深度三才五格分析"""
    return result

# ============ 流年大运 ============
def generate_liunian_dayun(name, birth_info, gender, lunar_date=''):
    year, month, day = birth_info['year'], birth_info['month'], birth_info['day']
    hour = birth_info.get('hour', 12)
    year_gz  = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz   = get_ganzhi_day(year, month, day)
    hour_gz  = get_ganzhi_hour(year, month, day, hour)
    pillars  = [year_gz, month_gz, day_gz, hour_gz]
    day_gan  = day_gz[0];  day_wx = GAN_WUXING.get(day_gan, '土')
    wuxing_full = get_wuxing_full(*pillars)
    rizhu_info  = analyze_rizhu_wangshui(day_gan, month_gz, pillars)
    xiyong = analyze_xiyongshen(wuxing_full, rizhu_info['strong'], day_wx)
    qiyun_age       = calc_qiyun_age(year, month, day, gender)
    dayun_start_year = year + qiyun_age

    year_gan   = get_ganzhi_year(year)[0]
    year_yy    = '阳' if TIANGAN.index(year_gan) % 2 == 0 else '阴'
    is_forward = (year_yy == '阳' and gender == '男') or (year_yy == '阴' and gender == '女')

    # [修复12] 删除 month_gz_idx（计算后从未使用）
    dayun_list = []
    for i in range(10):
        offset      = (i+1) if is_forward else -(i+1)
        dz_gan_idx  = (TIANGAN.index(month_gz[0]) + offset) % 10
        dz_zhi_idx  = (DIZHI.index(month_gz[1]) + offset) % 12
        dz_gz       = TIANGAN[dz_gan_idx] + DIZHI[dz_zhi_idx]
        start_y     = dayun_start_year + i * 10
        dz_wx  = GAN_WUXING.get(dz_gz[0], '土')
        zhi_wx = ZHI_WUXING.get(dz_gz[1], '土')
        if   dz_wx == xiyong[0] or zhi_wx == xiyong[0]:        luck = "逢喜用，运势大好 ⭐⭐⭐"
        elif WUXING_SHENG.get(dz_wx,'') == xiyong[0]:          luck = "相生喜用，较为顺遂 ⭐⭐"
        elif WUXING_KE.get(dz_wx,'') == day_wx:                luck = "官杀来克，需稳重应对 ⚠️"
        else:                                                   luck = "平稳运势 ⭐"
        dayun_list.append((start_y, start_y+9, dz_gz, luck))

    current_year = datetime.now().year
    liunian_list = []
    for i in range(10):
        y     = current_year + i
        lz    = get_ganzhi_year(y)
        lz_wx = GAN_WUXING.get(lz[0], '土')
        score = 70
        if   lz_wx == xiyong[0]:                        score += 15
        elif WUXING_SHENG.get(lz_wx,'') == xiyong[0]:   score += 8
        elif WUXING_KE.get(lz_wx,'') == day_wx:          score -= 10
        if ZHI_CHONG.get(lz[1],'') in [day_gz[1], month_gz[1]]:  score -= 8
        if ZHI_LIUHE.get(lz[1],'') in [day_gz[1], month_gz[1]]:  score += 5
        score = min(97, max(52, score + random.randint(-3, 3)))
        if   score >= 85: nianyun = "大吉之年，诸事顺遂"
        elif score >= 72: nianyun = "吉利之年，稳步前进"
        else:             nianyun = "需谨慎行事，避免冒进"
        liunian_list.append((y, lz, nianyun, score))

    if   xiyong[0] in ['土','金']: career_detail = "适合稳定发展、管理岗位，有望升职"; industry = "金融、企业管理、顾问咨询"
    elif xiyong[0] in ['木','火']: career_detail = "适合创新突破、创业发展";           industry = "科技、创意产业、艺术设计"
    else:                          career_detail = "适合专业技能、技术领域";            industry = "医疗、教育、工程技术"

    yearly_detail = ""
    for y, lz, nianyun, score in liunian_list[:10]:
        yearly_detail += f"\n• {y}年 {lz}：{nianyun}（{score}%）"

    # [修复9] 修正感情运势 or 表达式歧义
    taohua_years = [str(y) for y, lz, _, s in liunian_list if ZHI_LIUHE.get(lz[1],'') == day_gz[1]]
    love_line = f"桃花年：{', '.join(taohua_years)}" if taohua_years else "需主动把握机缘"

    safe_name = md_escape(name)
    result = f"""📈 **{safe_name} 流年大运深度分析**

━━━━━━━━━━━━━━━━━━━━━━
📌 基础信息
• 四柱：{year_gz} {month_gz} {day_gz} {hour_gz}
• 日主：{day_gan}（{day_wx}）{rizhu_info['strong']}
• 喜用神：{xiyong[0]}、{xiyong[1]}
• 起运年龄：约{qiyun_age}岁（{dayun_start_year}年起运）
• 大运顺逆：{'顺排' if is_forward else '逆排'}

📊 十年大运详解
{chr(10).join(f'• {y1}-{y2}年（{gz}）：{luck}' for y1,y2,gz,luck in dayun_list[:8])}

📆 未来十年流年预测
{yearly_detail}

💼 事业运势
• {career_detail}
• 适合行业：{industry}

💰 财富运势
• 喜用{xiyong[0]}年财运旺，{WUXING_SHENG.get(xiyong[0],'木')}年次之

🌹 感情运势
• {love_line}

🔰 改运建议
• 喜用五行：{xiyong[0]}（{LUCKY_COLOR_MAP.get(xiyong[0],'白色')}）
• 方位：{FAVORABLE_DIR.get(xiyong[0],'东')}方
• 宜佩戴：{xiyong[0]}属性宝石或饰品

━━━━━━━━━━━━━━━━━━━━━━
🙏 命理分析仅供参考，祝您诸事顺利！"""
    return result

# ============ 合婚分析 ============
def generate_hehun_detail(male_info, female_info):
    def bazi_of(info):
        y, m, d, h = info['year'], info['month'], info['day'], info.get('hour',12)
        return (get_ganzhi_year(y), get_ganzhi_month(y,m,d),
                get_ganzhi_day(y,m,d), get_ganzhi_hour(y,m,d,h))

    m_ygz, m_mgz, m_dgz, m_hgz = bazi_of(male_info)
    f_ygz, f_mgz, f_dgz, f_hgz = bazi_of(female_info)
    male_zodiac   = get_zodiac(male_info['year'])
    female_zodiac = get_zodiac(female_info['year'])
    male_zhi      = m_ygz[1];  female_zhi = f_ygz[1]

    sanhe_groups = [{'申','子','辰'},{'寅','午','戌'},{'巳','酉','丑'},{'亥','卯','未'}]
    is_sanhe = any(male_zhi in g and female_zhi in g for g in sanhe_groups)
    is_liuhe = ZHI_LIUHE.get(male_zhi,'') == female_zhi
    is_chong = ZHI_CHONG.get(male_zhi,'') == female_zhi
    is_xing  = ZHI_XING.get(male_zhi,'') == female_zhi

    if   is_liuhe: zodiac_score=97; zodiac_desc="六合，天作之合"
    elif is_sanhe: zodiac_score=92; zodiac_desc="三合，相辅相成"
    elif is_chong: zodiac_score=45; zodiac_desc="相冲，需多磨合"
    elif is_xing:  zodiac_score=55; zodiac_desc="相刑，需包容理解"
    else:          zodiac_score=72; zodiac_desc="普通配对，后天经营"

    male_day_gan   = m_dgz[0]; female_day_gan = f_dgz[0]
    male_day_zhi   = m_dgz[1]; female_day_zhi = f_dgz[1]
    is_gan_he = GAN_HE.get(male_day_gan,'') == female_day_gan
    is_zhi_he = ZHI_LIUHE.get(male_day_zhi,'') == female_day_zhi
    gan_he_score = 20 if is_gan_he else 0
    zhi_he_score = 15 if is_zhi_he else 0

    male_wx   = get_wuxing_full(m_ygz, m_mgz, m_dgz, m_hgz)
    female_wx = get_wuxing_full(f_ygz, f_mgz, f_dgz, f_hgz)
    complementary = sum(1 for k in male_wx if abs(male_wx[k]-female_wx[k]) < 1.5)
    wx_score  = min(20, complementary * 4)
    total_score = min(100, max(40, int(zodiac_score*0.5 + gan_he_score + zhi_he_score + wx_score)))

    if   total_score >= 90: jianyi = "天作之合，极为般配，婚后幸福美满 💝"
    elif total_score >= 78: jianyi = "佳偶天成，较为般配，婚后运势互补 💖"
    elif total_score >= 65: jianyi = "中等匹配，需要相互包容理解 💛"
    else:                   jianyi = "需慎重考虑，建议多了解后再决定 💬"

    result = f"""💑 **{male_zodiac}男 × {female_zodiac}女 合婚深度分析**

━━━━━━━━━━━━━━━━━━━━━━
🈴 双方八字
• 男方：{m_ygz} {m_mgz} {m_dgz} {m_hgz}（{male_zodiac}）
• 女方：{f_ygz} {f_mgz} {f_dgz} {f_hgz}（{female_zodiac}）

🐾 生肖配合
• {male_zodiac}与{female_zodiac}：{zodiac_desc}（{zodiac_score}分）

🔗 八字合婚
• 日干{male_day_gan}/{female_day_gan}：{'天干五合 ✨' if is_gan_he else '天干未合'}
• 日支{male_day_zhi}/{female_day_zhi}：{'日支六合 ✨' if is_zhi_he else '日支未合'}
• 五行互补：{'较为互补' if complementary >= 3 else '稍有差异，需磨合'}

💯 综合匹配度：{total_score}分

💡 婚姻建议
• {jianyi}

⚠️ 注意事项
• {'男女生肖相冲，婚前建议择吉日化解' if is_chong else '感情用心经营，婚后相互包容理解'}

🏠 婚后预测
• 财运：{'互补双旺' if wx_score >= 15 else '需共同规划'}
• 感情：{'相合度高，细水长流' if is_gan_he or is_zhi_he else '需要用心经营'}

━━━━━━━━━━━━━━━━━━━━━━"""
    return result

# ============ 取名（带姓氏）============
STROKE_DICT = {
    '王':4,'李':7,'张':11,'刘':6,'陈':16,'赵':9,'黄':12,'周':8,
    '吴':7,'徐':10,'孙':6,'马':10,'朱':6,'胡':11,'郭':15,'林':8,
    '何':7,'高':10,'罗':20,'郑':19,'谢':17,'宋':7,'唐':10,'韩':12,
    '冯':12,'曹':11,'彭':12,'曾':12,'肖':7,'田':5,'董':12,'袁':10,
    '邓':16,'许':11,'傅':12,'沈':10,'吕':7,'苏':7,'卢':7,'蒋':15,
    '蔡':17,'丁':2,'韦':9,'贾':10,'夏':10,'付':5,'江':7,'尹':4,
    '段':9,'雷':13,'汤':12,'黎':15,'温':12,'施':9,'牛':4,
    '洪':10,'石':5,'崔':11,'吉':6,'龚':11,'程':12,
    '梓':11,'涵':11,'林':8,'萱':12,'菲':11,'桐':10,'楠':13,'榆':12,
    '炎':8,'烨':10,'灿':7,'耀':20,'炅':8,'旭':6,'晗':11,'骞':13,
    '磊':15,'鑫':24,'岚':12,'岩':8,'岱':8,'坤':8,'城':10,'轩':10,
    '铭':14,'锋':16,'锐':12,'钧':13,'铖':14,'钰':13,
    '涛':13,'浩':11,'瀚':20,'澜':20,'泉':9,'泽':8,'沐':8,'沛':8,
    '浚':11,'潇':14,'安':6,'宁':5,'瑞':13,'祺':13,'福':13,'宸':10,
    '睿':14,'朗':10,'杰':8,'可':5,'禾':5,'一':1,'嵩':13,'垚':13,
    '怡':8,'锦':13,'欣':8,'思':9,'芯':8,'琳':12,'汐':7,'诺':10,
}
LUCKY_GE = {1,3,5,6,7,8,11,13,15,16,17,18,21,23,24,25,29,31,32,33,35,37,38,39,41,45,47,48}

def stroke_of_char(ch):
    return STROKE_DICT.get(ch, 10)

def numerology_level(value):
    if value in LUCKY_GE: return '吉'
    if value % 2 == 1:    return '中吉'
    return '平'

def generate_qiming_with_surname(name, birth_info, gender, surname):
    year, month, day = birth_info['year'], birth_info['month'], birth_info['day']
    hour = birth_info.get('hour', 12)
    year_gz  = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz   = get_ganzhi_day(year, month, day)
    hour_gz  = get_ganzhi_hour(year, month, day, hour)
    pillars  = [year_gz, month_gz, day_gz, hour_gz]
    wuxing_full = get_wuxing_full(*pillars)
    day_gan = day_gz[0]; day_wx = GAN_WUXING.get(day_gan,'土')
    rizhu_info = analyze_rizhu_wangshui(day_gan, month_gz, pillars)
    xiyong = analyze_xiyongshen(wuxing_full, rizhu_info['strong'], day_wx)

    RECOMMENDED_CHARS = {
        '木':['梓','涵','林','萱','菲','桐','楠','榆','森','岚'],
        '火':['炎','烨','灿','耀','炅','旭','晗','骞','熠','曦'],
        '土':['磊','怡','岩','岱','坤','城','轩','嵩','钧','垚'],
        '金':['鑫','铭','锋','锐','铖','钰','锦','铎','镇','钧'],
        '水':['涛','浩','瀚','澜','泉','泽','沐','沛','浚','潇'],
    }
    name_chars = RECOMMENDED_CHARS.get(xiyong[0], RECOMMENDED_CHARS['水'])
    strokes    = sum(stroke_of_char(c) for c in surname)
    surname_yy = '阳' if strokes % 2 == 1 else '阴'

    second_pool = ['宸','睿','朗','轩','杰','安','宁','瑞','祺','福']
    third_pool  = ['涵','欣','怡','思','芯','琳','瑞','汐','诺','可']

    names_fame, names_lucky, names_simple = [], [], []

    for c1 in name_chars[:5]:
        for c2 in second_pool:
            g1, g2 = stroke_of_char(c1), stroke_of_char(c2)
            renge  = strokes + g1   # 人格 = 姓 + 名首字
            if numerology_level(renge) == '吉' and len(names_fame) < 3:
                names_fame.append((f"{surname}{c1}{c2}", renge, g1+g2, strokes+g1+g2))

    for c1 in name_chars[2:7]:
        for c2 in third_pool:
            g1, g2 = stroke_of_char(c1), stroke_of_char(c2)
            # [修复3] 原代码误用上轮 renge，改为正确计算 strokes+g1
            renge  = strokes + g1
            total  = strokes + g1 + g2
            if numerology_level(total) == '吉' and len(names_lucky) < 3:
                names_lucky.append((f"{surname}{c1}{c2}", renge, g1+g2, total))

    for c1 in name_chars[:4]:
        for c2 in ['可','禾','宁','安','一']:
            g1, g2 = stroke_of_char(c1), stroke_of_char(c2)
            if len(names_simple) < 3:
                names_simple.append((f"{surname}{c1}{c2}", strokes+g1, g1+g2, strokes+g1+g2))

    def pad_names(lst, pool1, pool2):
        while len(lst) < 3:
            c1 = pool1[len(lst) % len(pool1)]; c2 = pool2[len(lst) % len(pool2)]
            g1, g2 = stroke_of_char(c1), stroke_of_char(c2)
            lst.append((f"{surname}{c1}{c2}", strokes+g1, g1+g2, strokes+g1+g2))
        return lst
    names_fame   = pad_names(names_fame,   name_chars, second_pool)
    names_lucky  = pad_names(names_lucky,  name_chars, third_pool)
    names_simple = pad_names(names_simple, name_chars, ['可','宁','安'])

    def fmt(t):
        n, rg, dg, zg = t
        return f"• {n}（人格{rg}{numerology_level(rg)} 地格{dg}{numerology_level(dg)} 总格{zg}{numerology_level(zg)}）"

    result = f"""🍼 **{surname}姓 宝宝取名深度分析**

━━━━━━━━━━━━━━━━━━━━━━
㊙️ 八字信息
• 四柱：{year_gz} {month_gz} {day_gz} {hour_gz}
• 喜用神：{xiyong[0]}、{xiyong[1]}
• 日主：{day_gan}（{day_wx}）{rizhu_info['strong']}

🏠 姓氏分析
• 姓氏：{surname}（{strokes}画，{surname_yy}性）

🔤 推荐名字（含五格笔画）

🏆 成名型：
{chr(10).join(fmt(n) for n in names_fame[:5])}

🍀 吉祥型：
{chr(10).join(fmt(n) for n in names_lucky[:5])}

✨ 简洁型：
{chr(10).join(fmt(n) for n in names_simple[:5])}

📖 五格说明
• 天格（祖辈）= 姓氏 {strokes}画
• 人格（主运）= 姓氏 + 名首字
• 地格（基础）= 名首字 + 名末字
• 总格（一生）= 姓名总笔画

💡 综合建议
• 推荐优先选用「成名型」名字
• 五行补{xiyong[0]}，寓意吉祥，数理协调

━━━━━━━━━━━━━━━━━━━━━━"""
    return result

# ============ 吉时查询 ============
def generate_jishi_detail(birth_info, gender):
    today_dt = datetime.now()
    today    = today_dt.strftime("%Y年%m月%d日")
    year, month, day = birth_info['year'], birth_info['month'], birth_info['day']
    hour = birth_info.get('hour', 12)
    year_gz  = get_ganzhi_year(year)
    month_gz = get_ganzhi_month(year, month, day)
    day_gz   = get_ganzhi_day(year, month, day)
    hour_gz  = get_ganzhi_hour(year, month, day, hour)

    today_day_gz = get_ganzhi_day(today_dt.year, today_dt.month, today_dt.day)
    today_zhi    = today_day_gz[1]; today_gan = today_day_gz[0]

    jianchu_map  = ['建','除','满','平','定','执','破','危','成','收','开','闭']
    jianchu      = jianchu_map[DIZHI.index(today_zhi) % 12]
    yi_ji = {
        '建':(['出行','求职','立志','求医'],['动土','安床','嫁娶','开张']),
        '除':(['求医','扫舍','沐浴','解除'],['嫁娶','开市','移居','入宅']),
        '满':(['开市','纳财','入宅','装修'],['求医','诉讼','远行','诞子']),
        '平':(['出行','会友','洽谈','求学'],['嫁娶','入宅','安葬','开凿']),
        '定':(['祭祀','会亲','订盟','纳采'],['出行','破土','诉讼','开渠']),
        '执':(['纳采','安床','入仓','捕猎'],['开市','出行','嫁娶','移居']),
        '破':(['求医','拆卸','解除'],['出行','嫁娶','开市','安葬']),
        '危':(['祭祀','祈福','求医','登高'],['出行','开市','嫁娶','入宅']),
        '成':(['嫁娶','开市','立约','入宅'],['诉讼','动土','出行']),
        '收':(['纳财','收货','开仓','订婚'],['嫁娶','出行','开市']),
        '开':(['开市','出行','入宅','嫁娶'],['安葬','破土','诉讼']),
        '闭':(['安葬','立券','纳财','立基'],['嫁娶','出行','开市','入宅']),
    }
    yi, ji = yi_ji.get(jianchu, (['出行','洽谈'],['动土','破坏']))

    ZHI_TO_HOUR = {'子':'23:00-01:00','丑':'01:00-03:00','寅':'03:00-05:00',
                   '卯':'05:00-07:00','辰':'07:00-09:00','巳':'09:00-11:00',
                   '午':'11:00-13:00','未':'13:00-15:00','申':'15:00-17:00',
                   '酉':'17:00-19:00','戌':'19:00-21:00','亥':'21:00-23:00'}
    sanhe = {'子':['申','辰'],'午':['寅','戌'],'卯':['亥','未'],'酉':['巳','丑'],
             '寅':['午','戌'],'申':['子','辰'],'巳':['酉','丑'],'亥':['卯','未'],
             '辰':['子','申'],'戌':['午','寅'],'丑':['巳','酉'],'未':['亥','卯']}
    best_zhis  = list(sanhe.get(today_zhi, []))
    liuhe_zhi  = ZHI_LIUHE.get(today_zhi, '')
    if liuhe_zhi: best_zhis.insert(0, liuhe_zhi)
    best_times = [ZHI_TO_HOUR[z] for z in best_zhis if z in ZHI_TO_HOUR]

    today_wx  = GAN_WUXING.get(today_gan,'土')
    sheng_wx  = WUXING_SHENG_BY.get(today_wx, '金')
    second_zhis  = [z for z in DIZHI if ZHI_WUXING.get(z,'') == sheng_wx and z not in best_zhis]
    second_times = [ZHI_TO_HOUR[z] for z in second_zhis[:2] if z in ZHI_TO_HOUR] or ['09:00-11:00','15:00-17:00']

    chong_zhi    = ZHI_CHONG.get(today_zhi, '')
    chong_zodiac = SHENGXIAO[DIZHI.index(chong_zhi)] if chong_zhi in DIZHI else '无'

    hour_fortune = []
    for zhi in DIZHI:
        t = ZHI_TO_HOUR[zhi]
        if   zhi in best_zhis or zhi == liuhe_zhi:  level = "大吉"
        elif zhi in second_zhis:                     level = "吉"
        elif ZHI_CHONG.get(zhi,'') == today_zhi or ZHI_XING.get(zhi,'') == today_zhi: level = "凶"
        else:                                        level = "平"
        hour_fortune.append(f"• {t}（{zhi}时）：{level}")

    result = f"""🕐 **{gender} 今日吉时查询**

━━━━━━━━━━━━━━━━━━━━━━
📆 {today}
• 今日日柱：{today_day_gz} ｜ 日建：{jianchu}日
• 命主八字：{year_gz} {month_gz} {day_gz} {hour_gz}

❤️ 最佳吉时（六合/三合）
{chr(10).join(f'• {t}' for t in best_times) or '• 09:00-11:00（辰时）'}

💚 次吉时段（相生时辰）
{chr(10).join(f'• {t}' for t in second_times)}

☯️ 今日宜忌（{jianchu}日）
• 宜：{', '.join(yi)}
• 忌：{', '.join(ji)}

⚠️ 冲煞提醒
• 今日冲{chong_zhi}（{chong_zodiac}）生肖需注意
• 宜避开冲煞方向

⏰ 今日十二时辰吉凶
{chr(10).join(hour_fortune)}

━━━━━━━━━━━━━━━━━━━━━━
🙏 建议在吉时进行重要事务"""
    return result

# ============ 今日运势（直接输出，无需生辰）============
def generate_today_fortune_direct():
    """基于今日干支直接生成通用运势，用户无需输入生辰"""
    today_dt   = datetime.now()
    today      = today_dt.strftime("%Y年%m月%d日")
    today_gz   = get_ganzhi_year(today_dt.year)
    today_mgz  = get_ganzhi_month(today_dt.year, today_dt.month, today_dt.day)
    today_dgz  = get_ganzhi_day(today_dt.year, today_dt.month, today_dt.day)
    today_gan  = today_dgz[0]
    today_zhi  = today_dgz[1]
    today_wx   = GAN_WUXING.get(today_gan, '土')
    year_wx    = GAN_WUXING.get(today_gz[0], '土')

    # 五行推算今日大势
    sheng_today = WUXING_SHENG.get(today_wx, '火')
    ke_today    = WUXING_KE.get(today_wx, '土')
    favorable   = FAVORABLE_DIR.get(today_wx, '东')
    lucky_color = LUCKY_COLOR_MAP.get(today_wx, '白色')

    # 今日吉时（基于日支三合六合）
    sanhe_zhi = {
        '子':['申','辰'],'午':['寅','戌'],'卯':['亥','未'],'酉':['巳','丑'],
        '寅':['午','戌'],'申':['子','辰'],'巳':['酉','丑'],'亥':['卯','未'],
        '辰':['子','申'],'戌':['午','寅'],'丑':['巳','酉'],'未':['亥','卯'],
    }
    ZHI_TO_HOUR = {
        '子':'23:00-01:00','丑':'01:00-03:00','寅':'03:00-05:00',
        '卯':'05:00-07:00','辰':'07:00-09:00','巳':'09:00-11:00',
        '午':'11:00-13:00','未':'13:00-15:00','申':'15:00-17:00',
        '酉':'17:00-19:00','戌':'19:00-21:00','亥':'21:00-23:00',
    }
    good_zhis  = list(sanhe_zhi.get(today_zhi, []))
    liuhe_zhi  = ZHI_LIUHE.get(today_zhi, '')
    if liuhe_zhi: good_zhis.insert(0, liuhe_zhi)
    good_hours = [ZHI_TO_HOUR[z] for z in good_zhis if z in ZHI_TO_HOUR] or ['09:00-11:00','15:00-17:00']

    # 日建十二神宜忌
    jianchu_map = ['建','除','满','平','定','执','破','危','成','收','开','闭']
    jianchu     = jianchu_map[DIZHI.index(today_zhi) % 12]
    yi_ji = {
        '建':(['出行','求职','立志'],['动土','安床','嫁娶']),
        '除':(['求医','扫舍','沐浴'],['嫁娶','开市','移居']),
        '满':(['开市','纳财','入宅'],['求医','诉讼','出行']),
        '平':(['出行','会友','洽谈'],['嫁娶','入宅','安葬']),
        '定':(['祭祀','会亲','订盟'],['出行','破土','诉讼']),
        '执':(['纳采','安床','入仓'],['开市','出行','嫁娶']),
        '破':(['求医','拆卸','解除'],['出行','嫁娶','开市']),
        '危':(['祭祀','祈福','求医'],['出行','开市','嫁娶']),
        '成':(['嫁娶','开市','立约'],['诉讼','动土','出行']),
        '收':(['纳财','收货','开仓'],['嫁娶','出行','开市']),
        '开':(['开市','出行','入宅'],['安葬','破土','诉讼']),
        '闭':(['安葬','立券','纳财'],['嫁娶','出行','开市']),
    }
    yi, ji = yi_ji.get(jianchu, (['出行','洽谈'],['动土','破坏']))

    # 今日综合能量评级（基于流年/日干五行关系）
    if year_wx == today_wx:
        energy = "强 ⚡ 适合主动出击"
        overall_tip = "流年日干同气，能量充足，宜大胆行事"
    elif WUXING_SHENG.get(year_wx,'') == today_wx:
        energy = "旺 ✨ 顺势而为"
        overall_tip = "流年生日干，整体顺遂，适合推进重要事项"
    elif WUXING_KE.get(year_wx,'') == today_wx:
        energy = "弱 ⚠️ 宜稳不宜动"
        overall_tip = "流年克日干，今日宜守不宜攻，注意情绪稳定"
    else:
        energy = "平 ☯️ 稳步前行"
        overall_tip = "五行平和，适合处理日常事务，按部就班"

    # 流年干支
    chong_today = ZHI_CHONG.get(today_zhi, '')
    chong_z     = SHENGXIAO[DIZHI.index(chong_today)] if chong_today in DIZHI else '无'

    return f"""🌤️ *今日运势*

━━━━━━━━━━━━━━━━━━━━━━
📆 {today}
• 流年：{today_gz} ｜ 月柱：{today_mgz} ｜ 日柱：{today_dgz}
• 今日天干五行：{today_wx} ｜ 日建：{jianchu}日

⚡ 今日能量：{energy}
• {overall_tip}

🏮 今日吉时
{chr(10).join(f'• {h}' for h in good_hours[:3])}

☯️ 今日宜忌（{jianchu}日）
• 宜：{', '.join(yi)}
• 忌：{', '.join(ji)}

🧭 今日幸运元素
• 幸运方位：{favorable}
• 幸运颜色：{lucky_color}
• 幸运五行：{today_wx}（生{today_wx}者今日运势更旺）

⚠️ 冲煞提醒
• 今日冲{chong_today}（{chong_z}）生肖，该属相宜低调行事

━━━━━━━━━━━━━━━━━━━━━━
📌 需要个人专属运势？
💡 回复「流年」或「大运」直接进入深度分析"""

# ============ 吉时查询（直接输出今日结果，无需生辰）============
def generate_jishi_today():
    """基于今日干支直接生成吉时，用户无需输入生辰"""
    today_dt = datetime.now()
    today    = today_dt.strftime("%Y年%m月%d日")
    today_day_gz = get_ganzhi_day(today_dt.year, today_dt.month, today_dt.day)
    today_month_gz = get_ganzhi_month(today_dt.year, today_dt.month, today_dt.day)
    today_zhi = today_day_gz[1]
    today_gan = today_day_gz[0]

    jianchu_map = ['建','除','满','平','定','执','破','危','成','收','开','闭']
    jianchu     = jianchu_map[DIZHI.index(today_zhi) % 12]

    yi_ji = {
        '建':(['出行','求职','立志','求医'],['动土','安床','嫁娶','开张']),
        '除':(['求医','扫舍','沐浴','解除'],['嫁娶','开市','移居','入宅']),
        '满':(['开市','纳财','入宅','装修'],['求医','诉讼','远行','诞子']),
        '平':(['出行','会友','洽谈','求学'],['嫁娶','入宅','安葬','开凿']),
        '定':(['祭祀','会亲','订盟','纳采'],['出行','破土','诉讼','开渠']),
        '执':(['纳采','安床','入仓','捕猎'],['开市','出行','嫁娶','移居']),
        '破':(['求医','拆卸','解除'],['出行','嫁娶','开市','安葬']),
        '危':(['祭祀','祈福','求医','登高'],['出行','开市','嫁娶','入宅']),
        '成':(['嫁娶','开市','立约','入宅'],['诉讼','动土','出行']),
        '收':(['纳财','收货','开仓','订婚'],['嫁娶','出行','开市']),
        '开':(['开市','出行','入宅','嫁娶'],['安葬','破土','诉讼']),
        '闭':(['安葬','立券','纳财','立基'],['嫁娶','出行','开市','入宅']),
    }
    yi, ji = yi_ji.get(jianchu, (['出行','洽谈'],['动土','破坏']))

    ZHI_TO_HOUR = {
        '子':'23:00-01:00','丑':'01:00-03:00','寅':'03:00-05:00',
        '卯':'05:00-07:00','辰':'07:00-09:00','巳':'09:00-11:00',
        '午':'11:00-13:00','未':'13:00-15:00','申':'15:00-17:00',
        '酉':'17:00-19:00','戌':'19:00-21:00','亥':'21:00-23:00',
    }
    sanhe = {
        '子':['申','辰'],'午':['寅','戌'],'卯':['亥','未'],'酉':['巳','丑'],
        '寅':['午','戌'],'申':['子','辰'],'巳':['酉','丑'],'亥':['卯','未'],
        '辰':['子','申'],'戌':['午','寅'],'丑':['巳','酉'],'未':['亥','卯'],
    }
    best_zhis  = list(sanhe.get(today_zhi, []))
    liuhe_zhi  = ZHI_LIUHE.get(today_zhi, '')
    if liuhe_zhi: best_zhis.insert(0, liuhe_zhi)
    best_times = [ZHI_TO_HOUR[z] for z in best_zhis if z in ZHI_TO_HOUR]

    today_wx    = GAN_WUXING.get(today_gan, '土')
    sheng_wx    = WUXING_SHENG_BY.get(today_wx, '金')
    second_zhis = [z for z in DIZHI if ZHI_WUXING.get(z,'') == sheng_wx and z not in best_zhis]
    second_times= [ZHI_TO_HOUR[z] for z in second_zhis[:2] if z in ZHI_TO_HOUR] or ['09:00-11:00','15:00-17:00']

    chong_zhi    = ZHI_CHONG.get(today_zhi, '')
    chong_zodiac = SHENGXIAO[DIZHI.index(chong_zhi)] if chong_zhi in DIZHI else '无'

    hour_fortune = []
    for zhi in DIZHI:
        t = ZHI_TO_HOUR[zhi]
        if   zhi in best_zhis or zhi == liuhe_zhi: level = "大吉"
        elif zhi in second_zhis:                    level = "吉"
        elif ZHI_CHONG.get(zhi,'') == today_zhi or ZHI_XING.get(zhi,'') == today_zhi: level = "凶"
        else:                                       level = "平"
        hour_fortune.append(f"• {t}（{zhi}时）：{level}")

    return f"""🕐 *今日吉时查询*

━━━━━━━━━━━━━━━━━━━━━━
📆 {today}
• 今日日柱：{today_day_gz} ｜ 月柱：{today_month_gz}
• 日建：{jianchu}日

❤️ 最佳吉时（六合/三合）
{chr(10).join(f'• {t}' for t in best_times) or '• 09:00-11:00（辰时）'}

💚 次吉时段（相生时辰）
{chr(10).join(f'• {t}' for t in second_times)}

☯️ 今日宜忌（{jianchu}日）
• 宜：{', '.join(yi)}
• 忌：{', '.join(ji)}

⚠️ 冲煞提醒
• 今日冲{chong_zhi}（{chong_zodiac}）生肖需注意

⏰ 今日十二时辰吉凶
{chr(10).join(hour_fortune)}

━━━━━━━━━━━━━━━━━━━━━━
🙏 建议在吉时进行重要事务"""

# ============================================================
# SBTI 测试模块 v1.0 — 2026 全球发疯指数测试
# ============================================================
# 功能：
# 1. AI 动态出题：前3题固定，后3题由 LLM 根据前3题得分动态生成
# 2. SBTI 梗图生成器：生成含2026流行词的中英双语结果文字卡
# 3. 群组性格图谱：统计群成员性格分布并生成"本群战斗力分布图"
# ============================================================

# SBTI 用户状态存储
sbti_context = {}   # uid -> {step, answers, scores, questions}

# SBTI 维度定义（得分维度 -> 中文含义）
SBTI_DIMS = {
    'apathy':  {'cn': '躺平指数', 'en': 'ZZZZ', 'emoji': '😴'},
    'ego':     {'cn': '自我中心值', 'en': 'MALO', 'emoji': '🪞'},
    'chaos':   {'cn': '发疯浓度', 'en': 'FUCK', 'emoji': '🌀'},
    'grind':   {'cn': '卷王系数', 'en': 'GRND', 'emoji': '💼'},
    'vibe':    {'cn': '氛围感知力', 'en': 'VIBE', 'emoji': '✨'},
    'lore':    {'cn': '人设稳定度', 'en': 'LORE', 'emoji': '🎭'},
}

# 固定前3题（保证基础维度覆盖）
SBTI_FIXED_QUESTIONS = [
    {
        "id": 1,
        "text": "当你发现群聊有 99+ 未读消息，你的第一反应是？",
        "options": [
            {"text": "右键全部已读，继续摸鱼 🤫", "score": {"apathy": 10}},
            {"text": "爬楼找有没有人提到自己 🧐", "score": {"ego": 10}},
            {"text": "直接退群，人间不值得 🚪", "score": {"chaos": 10}},
            {"text": "认真看完，生怕错过重要信息 👀", "score": {"grind": 10}},
        ]
    },
    {
        "id": 2,
        "text": "朋友发了条 2 分钟的语音，你会？",
        "options": [
            {"text": "1.5x 速度播完，笑着回 \'好的\'", "score": {"grind": 8, "apathy": 2}},
            {"text": "截图发给另一个朋友问啥意思 😈", "score": {"ego": 7, "chaos": 3}},
            {"text": "听完深感共鸣，写了一大段回复", "score": {"vibe": 10}},
            {"text": "挂着语音睡着了，明天再说", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 3,
        "text": "你的社交媒体主页风格是？",
        "options": [
            {"text": "精心策划的人设，每条都有主题色 🎨", "score": {"lore": 10}},
            {"text": "一年发三条，且全是转发", "score": {"apathy": 10}},
            {"text": "随机发癫内容，粉丝看不懂就对了", "score": {"chaos": 10}},
            {"text": "成就卡合集 + 工作打卡，绩效全公开", "score": {"grind": 10}},
        ]
    },
    {
        "id": 4,
        "text": "工作群凌晨2点弹出消息，你会？",
        "options": [
            {"text": "静音睡觉，明天再说 😊", "score": {"apathy": 10}},
            {"text": "内心纠结3分钟，然后继续睡", "score": {"vibe": 8, "apathy": 2}},
            {"text": "立刻回复，证明自己是卷王 💪", "score": {"grind": 10}},
            {"text": "截图发朋友圈：这就是打工人的命运", "score": {"lore": 7, "chaos": 3}},
        ]
    },
    {
        "id": 5,
        "text": "朋友找你吐槽，你一般会？",
        "options": [
            {"text": "认真倾听，给出分析建议 📋", "score": {"grind": 10}},
            {"text": "共情满分，同步进入悲伤模式 🥲", "score": {"vibe": 10}},
            {"text": "听完立刻转移话题，不想被负能量影响", "score": {"apathy": 8, "chaos": 2}},
            {"text": "记下来，以后写进段子 🤔", "score": {"ego": 7, "lore": 3}},
        ]
    },
    {
        "id": 6,
        "text": "你去唱卡拉OK，一般会？",
        "options": [
            {"text": "抢麦 DJ 台，主导全场 🎤", "score": {"ego": 10, "chaos": 2}},
            {"text": "角落里当气氛组，偶尔配合 🎶", "score": {"apathy": 8, "vibe": 2}},
            {"text": "提前点好歌单，严格按歌单唱", "score": {"lore": 10}},
            {"text": "麦克风递过来就假装唱歌，实际上是听歌", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 7,
        "text": "当你听到一个重大八卦，你的反应是？",
        "options": [
            {"text": "第一时间转发给最铁的朋友 😱", "score": {"chaos": 10}},
            {"text": "表面平静，内心已经开始分析高铁", "score": {"vibe": 8, "grind": 2}},
            {"text": "假装不知道，但已经截图存档 📸", "score": {"lore": 10}},
            {"text": "哦。真的吗。", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 8,
        "text": "周末你一般怎么过？",
        "options": [
            {"text": "加班 or 搞副业，躺平是对生命的浪费", "score": {"grind": 10}},
            {"text": "自然醒，点外卖，刷剧到天黑 📺", "score": {"apathy": 10}},
            {"text": "约朋友探店拍照，发精心编辑的朋友圈", "score": {"lore": 8, "vibe": 2}},
            {"text": "随机触发：临时约局，目的地看心情", "score": {"chaos": 10}},
        ]
    },
    {
        "id": 9,
        "text": "你被当众表扬了，你的内心戏是？",
        "options": [
            {"text": "：）表面淡定，实际已经在想获奖感言", "score": {"ego": 10}},
            {"text": "能不能快点结束，我想静静 😇", "score": {"apathy": 10}},
            {"text": "这内容要更新到下个月的人设帖子里", "score": {"lore": 10}},
            {"text": "感谢团队，这不是我一个人的功劳 📝", "score": {"vibe": 10}},
        ]
    },
    {
        "id": 10,
        "text": "你和朋友吵架了，你会？",
        "options": [
            {"text": "先发一条长消息解释清楚，不留误会", "score": {"grind": 10, "vibe": 2}},
            {"text": "拉黑删除，三天后当无事发生", "score": {"apathy": 10}},
            {"text": "发一条意味深长的朋友圈内涵对方", "score": {"chaos": 10}},
            {"text": "想想这段关系在人设里的位置，再决定", "score": {"lore": 10}},
        ]
    },
    {
        "id": 11,
        "text": "你做选择的风格，更接近哪个？",
        "options": [
            {"text": "利弊分析表格，量化评分决策 📊", "score": {"grind": 10}},
            {"text": "感觉对了就冲，逻辑是后来的事 ✨", "score": {"vibe": 10}},
            {"text": "随机数生成器，命运交给算法 🎲", "score": {"chaos": 10}},
            {"text": "先想想这个选择是否符合人设定位", "score": {"lore": 10}},
        ]
    },
    {
        "id": 12,
        "text": "你在一个陌生领域里，会怎么做？",
        "options": [
            {"text": "先搜索50篇相关文章，理论先行 📚", "score": {"grind": 10}},
            {"text": "假装很懂，先入场再说 🎭", "score": {"ego": 10}},
            {"text": "等朋友带路，不想自己踩坑", "score": {"apathy": 10}},
            {"text": "乱闯，踩坑了就是最好的学习", "score": {"chaos": 10}},
        ]
    },
    {
        "id": 13,
        "text": "你理想的退休生活是？",
        "options": [
            {"text": "周游世界，打卡所有顶级目的地 🌍", "score": {"grind": 10}},
            {"text": "回乡下种地，社交媒体偶尔发发日常", "score": {"lore": 8, "apathy": 2}},
            {"text": "什么都不做，就是躺着 💤", "score": {"apathy": 10}},
            {"text": "不知道，退休的事退休再说 🤷", "score": {"chaos": 8, "vibe": 2}},
        ]
    },
    {
        "id": 14,
        "text": "你的聊天记录风格更像？",
        "options": [
            {"text": "能发表情包绝不打字 🎭", "score": {"chaos": 10}},
            {"text": "回复永远在5分钟内，效率至上 ⚡", "score": {"grind": 10}},
            {"text": "长篇大论，认真到对方已读不回", "score": {"vibe": 10}},
            {"text": "只回有必要回复的，其他装作没看到 🙈", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 15,
        "text": "你被别人模仿了，你会？",
        "options": [
            {"text": "暗中观察，看TA模仿得像不像 👀", "score": {"lore": 10}},
            {"text": "有点不爽，但懒得计较 😑", "score": {"apathy": 10}},
            {"text": "直接当面质问，你在搞什么？🔥", "score": {"ego": 10}},
            {"text": "觉得好笑，甚至想教TA几招 🧑‍🏫", "score": {"vibe": 10}},
        ]
    },
    {
        "id": 16,
        "text": "朋友晒了一张精修自拍，你会？",
        "options": [
            {"text": "认真夸赞，分析哪里修得好 📸", "score": {"vibe": 10}},
            {"text": "怀疑是不是同一个人，不敢认 🙈", "score": {"ego": 8, "chaos": 2}},
            {"text": "点个赞划走，不想多看 👆", "score": {"apathy": 10}},
            {"text": "思考自己下次拍照怎么构图 🤳", "score": {"grind": 8, "ego": 2}},
        ]
    },
    {
        "id": 17,
        "text": "你写朋友圈的频率是？",
        "options": [
            {"text": "有主题系列更新，定期营业 📅", "score": {"lore": 10}},
            {"text": "想发就发，不考虑数据反馈 📝", "score": {"chaos": 10}},
            {"text": "一年不超过5条，珍惜羽毛 🪶", "score": {"apathy": 10}},
            {"text": "每次发完都会看阅读量 📊", "score": {"grind": 10}},
        ]
    },
    {
        "id": 18,
        "text": "遇到选择困难时，你一般会？",
        "options": [
            {"text": "列个Excel表格分析利弊 🧮", "score": {"grind": 10}},
            {"text": "让别人替自己选，反正后果一起扛 🤝", "score": {"apathy": 10}},
            {"text": "掷骰子或抛硬币，让命运决定 🎲", "score": {"chaos": 10}},
            {"text": "跟着感觉走，感觉对了就是对了 ✨", "score": {"vibe": 10}},
        ]
    },
    {
        "id": 19,
        "text": "你参加聚会的目的是？",
        "options": [
            {"text": "认识新人，扩展社交网络 🌐", "score": {"ego": 8, "grind": 2}},
            {"text": "和老朋友叙旧，珍惜老伙计 👯", "score": {"lore": 8, "vibe": 2}},
            {"text": "为了吃顿好的，仅此而已 🍖", "score": {"apathy": 10}},
            {"text": "万一遇到有趣的人呢，随缘 🚶", "score": {"chaos": 10}},
        ]
    },
    {
        "id": 20,
        "text": "你给自己贴的标签是？",
        "options": [
            {"text": "这也不能，那也不能，反正不是普通人 🚫", "score": {"ego": 10}},
            {"text": "没有标签，我就是一个没有标签的人 🏷️", "score": {"lore": 8, "ego": 2}},
            {"text": "随心情切换，每天不一样 🌈", "score": {"chaos": 10}},
            {"text": "专注搞钱，其他都是浮云 💰", "score": {"grind": 10}},
        ]
    },
    {
        "id": 21,
        "text": "你通常怎么应对负面情绪？",
        "options": [
            {"text": "写长文发在只有自己可见的地方 📝", "score": {"lore": 10}},
            {"text": "找人倾诉，一定要把情绪倒干净 🗣️", "score": {"vibe": 10}},
            {"text": "刷短视频逃避，等它自己消失 🌀", "score": {"apathy": 10}},
            {"text": "跑步或健身，物理消化情绪 🏃", "score": {"grind": 10}},
        ]
    },
    {
        "id": 22,
        "text": "你更愿意成为哪种关系的中心？",
        "options": [
            {"text": "朋友圈的信息枢纽，谁的事都知道 🕸️", "score": {"vibe": 10}},
            {"text": "家人离不开的那种，无可替代 🏠", "score": {"lore": 8, "grind": 2}},
            {"text": "工作群的红人，有事第一个想到 👑", "score": {"ego": 10}},
            {"text": "小圈子的灵魂人物，质量大于数量 🎭", "score": {"ego": 8, "lore": 2}},
        ]
    },
    {
        "id": 23,
        "text": "当有人说「你怎么变了」，你的反应是？",
        "options": [
            {"text": "我就是变了，你跟得上吗 😎", "score": {"ego": 10}},
            {"text": "变？我一直是这样啊 🤨", "score": {"lore": 8, "vibe": 2}},
            {"text": "没变啊，你的感觉不准 👀", "score": {"apathy": 10}},
            {"text": "可能吧，但我不在乎别人怎么说 🤷", "score": {"chaos": 8, "ego": 2}},
        ]
    },
    {
        "id": 24,
        "text": "你更享受哪种独处方式？",
        "options": [
            {"text": "关掉手机，躺尸到天荒地老 🛋️", "score": {"apathy": 10}},
            {"text": "学习新技能，让时间更有价值 📚", "score": {"grind": 10}},
            {"text": "整理回忆，编排自己的人生剧本 📖", "score": {"lore": 10}},
            {"text": "发呆幻想，脑内剧场无限精彩 🎬", "score": {"ego": 8, "chaos": 2}},
        ]
    },
    {
        "id": 25,
        "text": "你如何看待「躺平」这个词？",
        "options": [
            {"text": "我的终极人生哲学，非常认同 🛌", "score": {"apathy": 10}},
            {"text": "不过是自嘲罢了，该卷还是卷 💪", "score": {"grind": 10}},
            {"text": "躺不平的，你看房贷答应吗 🏦", "score": {"vibe": 8, "grind": 2}},
            {"text": "一种人设标签，适合某些场合 🎪", "score": {"lore": 10}},
        ]
    },
    {
        "id": 26,
        "text": "你的工作风格更接近？",
        "options": [
            {"text": "Deadline是第一生产力，拖到最后一秒 ⏰", "score": {"chaos": 10}},
            {"text": "提前规划，任务分解，日清日结 📋", "score": {"grind": 10}},
            {"text": "看心情，心情好效率高，心情差摆烂 🌊", "score": {"apathy": 10}},
            {"text": "让老板满意是核心，其他都是浮云 👔", "score": {"ego": 10}},
        ]
    },
    {
        "id": 27,
        "text": "你如何处理好友列表里的人？",
        "options": [
            {"text": "定期清理，不适合就删，社交要断舍离 🧹", "score": {"ego": 10}},
            {"text": "从来不删，万一哪天需要呢 📋", "score": {"grind": 8, "apathy": 2}},
            {"text": "分组管理，不同的人给不同的权限 🔐", "score": {"lore": 10}},
            {"text": "根本不在乎列表，反正也不怎么聊天 💬", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 28,
        "text": "你对自己未来的期待是？",
        "options": [
            {"text": "财务自由，提前退休，周游世界 🌍", "score": {"grind": 10}},
            {"text": "成为一个传说，有故事可以说 📖", "score": {"ego": 8, "lore": 2}},
            {"text": "活在当下，想那么远干嘛 🦋", "score": {"chaos": 10}},
            {"text": "找到几个知心人，岁月静好 🌙", "score": {"vibe": 10}},
        ]
    },
    {
        "id": 29,
        "text": "职场中你属于哪种类型？",
        "options": [
            {"text": "准时打卡，绩效A，朋友圈都是工作打卡 📊", "score": {"grind": 10}},
            {"text": "踩点下班，工作只是生活的一部分 ⏰", "score": {"apathy": 10}},
            {"text": "办公室政治专家，谁和谁不对付都门清 🕵️", "score": {"lore": 8, "vibe": 2}},
            {"text": "开会时内心戏丰富，表面点头如捣蒜 👔", "score": {"ego": 8, "chaos": 2}},
        ]
    },
    {
        "id": 30,
        "text": "恋爱关系中你更接近？",
        "options": [
            {"text": "每日汇报行程，安全感来自于掌控 📱", "score": {"ego": 10}},
            {"text": "各玩各的，信任是给对方自由 🦋", "score": {"apathy": 8, "chaos": 2}},
            {"text": "发朋友圈必带对象，营造幸福人设 📸", "score": {"lore": 10}},
            {"text": "情绪跟着对方走，TA开心我就开心 😊", "score": {"vibe": 10}},
        ]
    },
    {
        "id": 31,
        "text": "社交媒体上你更在意？",
        "options": [
            {"text": "点赞数，数据证明存在感 📊", "score": {"grind": 10}},
            {"text": "评论区互动，社交不能断 🔥", "score": {"vibe": 10}},
            {"text": "粉丝增长曲线，数字让我兴奋 📈", "score": {"ego": 8, "grind": 2}},
            {"text": "收藏量，关注但不点赞是我的风格 💾", "score": {"lore": 8, "apathy": 2}},
        ]
    },
    {
        "id": 32,
        "text": "你发朋友圈的真实目的是？",
        "options": [
            {"text": "记录生活，若干年后翻看 📖", "score": {"lore": 8, "vibe": 2}},
            {"text": "立人设，让别人羡慕去吧 😏", "score": {"ego": 10}},
            {"text": "单纯想发，发完就不管了 🙌", "score": {"chaos": 8, "apathy": 2}},
            {"text": "工作需要，维持形象分 👔", "score": {"grind": 10}},
        ]
    },
    {
        "id": 33,
        "text": "以下哪种情况最让你崩溃？",
        "options": [
            {"text": "精心拍的照片只有12个赞 😱", "score": {"grind": 10}},
            {"text": "被朋友当众揭短，社死现场 💀", "score": {"ego": 10}},
            {"text": "计划全部打乱，从头再来 💔", "score": {"lore": 10}},
            {"text": "和谁都不熟，尴尬的空气 🫠", "score": {"vibe": 10}},
        ]
    },
    {
        "id": 34,
        "text": "「收到请回复」对你来说意味着？",
        "options": [
            {"text": "必须秒回，否则会焦虑不安 📱", "score": {"grind": 10}},
            {"text": "看心情，决定回不回 🎲", "score": {"chaos": 8, "apathy": 2}},
            {"text": "为什么要回复？我已读了不是吗 👀", "score": {"apathy": 10}},
            {"text": "先看看别人回什么，跟风党 🐑", "score": {"vibe": 8, "grind": 2}},
        ]
    },
    {
        "id": 35,
        "text": "你排队时一般会？",
        "options": [
            {"text": "研究怎么缩短排队时间，效率至上 ⏱️", "score": {"grind": 10}},
            {"text": "和前后的人聊天，社交无处不在 💬", "score": {"vibe": 10}},
            {"text": "刷手机发呆，时间自动流逝 📱", "score": {"apathy": 10}},
            {"text": "内心编剧：前面的人会不会突然闹事 🎬", "score": {"chaos": 10}},
        ]
    },
    {
        "id": 36,
        "text": "你相册里数量最多的照片类型是？",
        "options": [
            {"text": "自拍，每个角度都要收集 📸", "score": {"ego": 10}},
            {"text": "食物拍，美食当前先喂手机 🍜", "score": {"lore": 8, "vibe": 2}},
            {"text": "截图，合集可以出一本书 📚", "score": {"grind": 10}},
            {"text": "没什么照片，定期清理是习惯 🧹", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 37,
        "text": "你如何应对群聊里的冲突？",
        "options": [
            {"text": "截图保存，以后万一用得上 📸", "score": {"lore": 10}},
            {"text": "发表情包化解，幽默是武器 🎭", "score": {"chaos": 10}},
            {"text": "潜水围观，内心写好了剧本 📝", "score": {"ego": 8, "vibe": 2}},
            {"text": "直接退出，眼不见为净 🚪", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 38,
        "text": "你更愿意为什么内容付费？",
        "options": [
            {"text": "知识付费课程，升值自己 💰", "score": {"grind": 10}},
            {"text": "情绪价值产品，我快乐最重要 🎵", "score": {"vibe": 8, "chaos": 2}},
            {"text": "社交会员，圈子决定阶层 🌐", "score": {"ego": 10}},
            {"text": "无所谓，有免费的就用 🙌", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 39,
        "text": "反问：你其实是个很卷的人吗？（诚实作答）",
        "options": [
            {"text": "是的，我很努力，我要出人头地 💪", "score": {"grind": 10}},
            {"text": "不是，我只是假装很忙 😅", "score": {"lore": 8, "apathy": 2}},
            {"text": "看情况，被逼急了也会卷起来 🔥", "score": {"chaos": 8, "vibe": 2}},
            {"text": "我躺得很平，但偶尔也会焦虑 🛌", "score": {"apathy": 8, "grind": 2}},
        ]
    },
    {
        "id": 40,
        "text": "反问：你在意别人对你的评价吗？",
        "options": [
            {"text": "完全不在意，我的人生我说了算 🙌", "score": {"ego": 10}},
            {"text": "表面不在意，内心已经分析了三遍 🧠", "score": {"lore": 10}},
            {"text": "会在意，但不会表现出来 🎭", "score": {"vibe": 10}},
            {"text": "无所谓，反正大家都在忙自己的事 👀", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 41,
        "text": "反问：你是朋友圈的中心人物吗？",
        "options": [
            {"text": "必须是，有我在气氛就不会冷 🎉", "score": {"ego": 10}},
            {"text": "不是，我是幕后玩家 👻", "score": {"lore": 10}},
            {"text": "看场合，有时候我只想安静 🎧", "score": {"apathy": 8, "vibe": 2}},
            {"text": "我负责制造氛围，不是主角 ✨", "score": {"chaos": 8, "vibe": 2}},
        ]
    },
    {
        "id": 42,
        "text": "反问：你真的能接受躺平吗？",
        "options": [
            {"text": "躺平是梦想，但钱包不允许 💸", "score": {"grind": 8, "apathy": 2}},
            {"text": "可以，我已经躺平很久了 😴", "score": {"apathy": 10}},
            {"text": "嘴上躺平，身体很诚实 🏃", "score": {"chaos": 10}},
            {"text": "间歇性躺平，持续性焦虑 🔄", "score": {"vibe": 8, "grind": 2}},
        ]
    },
    {
        "id": 43,
        "text": "你在以下哪个场景最自在？",
        "options": [
            {"text": "一个人在家，完全不用社交 🏠", "score": {"apathy": 10}},
            {"text": "会议室，所有的目光都聚焦在我身上 👑", "score": {"ego": 10}},
            {"text": "深夜的便利店，安静治愈 🌙", "score": {"lore": 8, "vibe": 2}},
            {"text": "音乐节，人浪涌动，释放自我 🎸", "score": {"chaos": 10}},
        ]
    },
    {
        "id": 44,
        "text": "你的消费观更接近？",
        "options": [
            {"text": "该花花该省省，每分钱都要花在刀刃上 🗡️", "score": {"grind": 10}},
            {"text": "今天心情好，买！明天再说 💳", "score": {"chaos": 10}},
            {"text": "买什么都像在构建人设的一部分 🎭", "score": {"lore": 10}},
            {"text": "买之前先看测评，不交智商税 📱", "score": {"vibe": 8, "grind": 2}},
        ]
    },
    {
        "id": 45,
        "text": "当朋友突然找你借钱，你会？",
        "options": [
            {"text": "直接问要多少，转账不废话 💰", "score": {"vibe": 10}},
            {"text": "先发个表情包拖延，再想办法 😅", "score": {"chaos": 10}},
            {"text": "编个理由婉拒，关系没到那份上 🚫", "score": {"ego": 10}},
            {"text": "假装没看到，过几天再说 🙈", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 46,
        "text": "你更相信什么？",
        "options": [
            {"text": "努力就会有回报，天道酬勤 📈", "score": {"grind": 10}},
            {"text": "运气，选择大于努力 🍀", "score": {"chaos": 10}},
            {"text": "关系，有人脉走遍天下 🌐", "score": {"ego": 10}},
            {"text": "缘分，命里有时终须有 🕊️", "score": {"lore": 8, "vibe": 2}},
        ]
    },
    {
        "id": 47,
        "text": "你更愿意为什么花时间？",
        "options": [
            {"text": "自我提升，学习新技能永远不亏 📚", "score": {"grind": 10}},
            {"text": "维护关系，情感投资很重要 💕", "score": {"vibe": 10}},
            {"text": "经营人设，每个细节都要完美 🎨", "score": {"lore": 10}},
            {"text": "发呆放空，让大脑彻底休息 🧘", "score": {"apathy": 10}},
        ]
    },
    {
        "id": 48,
        "text": "你在群里最常扮演的角色是？",
        "options": [
            {"text": "气氛组，发表情包我最强 🎭", "score": {"chaos": 10}},
            {"text": "信息枢纽，有事找我准没错 📡", "score": {"vibe": 10}},
            {"text": "潜水员，默默观察一切 👀", "score": {"apathy": 8, "lore": 2}},
            {"text": "话题发起者，带节奏我在行 🚀", "score": {"ego": 10}},
        ]
    },
    {
        "id": 49,
        "text": "反问：你觉得自己是个有特点的人吗？",
        "options": [
            {"text": "必须有，我的存在就是特点 ✨", "score": {"ego": 10}},
            {"text": "特点不明显，但有一点点 🦋", "score": {"lore": 8, "vibe": 2}},
            {"text": "我不是人民币，做不到人人喜欢 🤷", "score": {"apathy": 10}},
            {"text": "特点这种东西是可以打造的 🎭", "score": {"lore": 10}},
        ]
    },
    {
        "id": 50,
        "text": "你希望别人记住你的是什么？",
        "options": [
            {"text": "我取得的成就，站C位的资本 🏆", "score": {"ego": 10}},
            {"text": "我是个有趣的人，和我聊天很快乐 😄", "score": {"chaos": 8, "vibe": 2}},
            {"text": "我对朋友很好，值得深交 🤝", "score": {"vibe": 10}},
            {"text": "没什么希望，被记住也累 🙈", "score": {"apathy": 10}},
        ]
    },
]

# 2026 流行词库（用于生成梗图标题）
VIRAL_WORDS_2026 = [
    # 躺平系
    ("完全静止体", "Full Static Mode", "apathy"),
    ("核心沉默主义者", "Core Silence Enjoyer", "apathy"),
    ("零耗能生物", "Zero-Energy Entity", "apathy"),
    # 发疯系
    ("量子发癫体", "Quantum Unhinged", "chaos"),
    ("混沌魅力体", "Chaos Charisma Core", "chaos"),
    ("全员情绪污染源", "Emotional Hazard Unit", "chaos"),
    # 自我系
    ("主角光环认证人", "Main Character Certified", "ego"),
    ("个人叙事构建师", "Personal Lore Architect", "ego"),
    ("视角霸主", "POV Monopolist", "ego"),
    # 卷王系
    ("效率怪物进化体", "Efficiency Monster EVO", "grind"),
    ("时间密度最大化者", "Time Density Maximizer", "grind"),
    ("全栈人生CEO", "Full-Stack Life CEO", "grind"),
    # 氛围系
    ("氛围感过载实体", "Vibe Overload Entity", "vibe"),
    ("共情辐射源", "Empathy Radiation Core", "vibe"),
    ("情绪天气预报员", "Emotional Weather Anchor", "vibe"),
    # 人设系
    ("人设钢铁侠", "Personal Lore Ironman", "lore"),
    ("叙事连贯性冠军", "Narrative Consistency Champ", "lore"),
    ("角色扮演终身会员", "Lifelong Character Player", "lore"),
]

# 群组性格图谱存储
sbti_group_stats = {}  # chat_id -> {uid: dominant_dim, ...}


def sbti_get_dominant_dim(scores: dict) -> str:
    """返回得分最高的维度key"""
    if not scores:
        return 'chaos'
    return max(scores, key=scores.get)


def sbti_get_viral_title(dominant_dim: str) -> tuple:
    """根据主维度随机选一个2026流行词，返回(中文, 英文)"""
    matches = [(cn, en) for cn, en, dim in VIRAL_WORDS_2026 if dim == dominant_dim]
    if not matches:
        matches = [(cn, en) for cn, en, dim in VIRAL_WORDS_2026]
    return random.choice(matches)


def sbti_build_result_card(name: str, scores: dict) -> str:
    """
    生成 SBTI 结果文字卡（中英双语梗图文本）
    支持一键转发到 Telegram Story / Channel
    """
    dominant = sbti_get_dominant_dim(scores)
    title_cn, title_en = sbti_get_viral_title(dominant)
    dim_info = SBTI_DIMS.get(dominant, {'cn': '神秘体', 'en': 'MYSTIC', 'emoji': '🔮'})

    # 构建得分条形图并计算总分
    total = max(sum(scores.values()), 1)
    score_bars = []
    for dim_key, info in SBTI_DIMS.items():
        val = scores.get(dim_key, 0)
        # 每维度最高10分，bar_len为0-10格的进度条
        bar_len = round(val / 10 * 10)  # val=0→0格, val=10→10格
        bar_len = max(0, min(10, bar_len))  # 确保在0-10范围内
        bar = '█' * bar_len + '░' * (10 - bar_len)
        score_bars.append(f"{info['emoji']} {info['cn']:6s} [{bar}] {val:3.0f}pt")
    
    # 计算六维总分
    six_dim_total = sum(scores.values())
    # 百分制换算
    max_possible = 60  # 6题 x 每题最高10分
    percent_score = min(100, int(six_dim_total / max_possible * 100))
    
    # 疯狂指数评级
    if percent_score >= 90:
        madness_level = "🌀 疯狂模式全开"
    elif percent_score >= 75:
        madness_level = "🔥 高度活跃状态"
    elif percent_score >= 50:
        madness_level = "✨ 正常偏疯癫"
    elif percent_score >= 25:
        madness_level = "😌 佛系养生型"
    else:
        madness_level = "😴 完全静止体"

    # 性格短评模板（按主维度）
    CHAR_DESC = {
        'apathy': "能量守恒大师，用最少的投入换取最大的精神安宁。不是不爱，是爱得太累了。",
        'ego':    "宇宙中心候选人，世界是你的镜子，每面都在反射你的高光时刻。",
        'chaos':  "人间搅局艺术家，你的出现让世界的信噪比直线下降，但也充满了惊喜。",
        'grind':  "卷王王中王，你把「内卷」升华成了一种美学，效率是你的信仰。",
        'vibe':   "氛围感知雷达，你能在0.5秒内读懂房间里所有人的微表情，然后精准破防。",
        'lore':   "人设工程师，你的每一条发言都是精心设计的叙事碎片，粉丝们正在拼图。",
    }
    char_desc = CHAR_DESC.get(dominant, "宇宙级神秘体，数据不足以描述你的复杂程度。")

    card = f"""
=================================
🔮 🧬 【SBTI 2026 发疯指数测试】 🧬 🔮
=================================
📕 {md_escape(name)} 的专属档案

📌 类型认证
  【{title_cn}】
  [{title_en}]
  核心维度：{dim_info['emoji']} {dim_info['cn']} ({dim_info['en']})

📊 六维雷达数据
{chr(10).join(score_bars)}

🎯 六维总分：{six_dim_total}pt / {max_possible}pt ({percent_score}%)
   {madness_level}

🧠 AI 诊断报告
{char_desc}

━━━━━━━━━━━━━━━━━━━━━━
🎯 *你可能还会喜欢*

🔮 *八字算命* — 了解你的命理格局
   /bazi

💕 *姻缘测算* — 看看你的桃花和伴侣
   /yinyuan

✨ *紫微斗数* — 完整星盘十二宫解读
   /ziwei

🌤️ *今日运势* — 每日吉凶早知道
   /today

🧬 *再来一次SBTI* — 换套题再测
   /sbti

📊 *查看本群战斗力* — 参与群排行
   /sbti_group

#SBTI2026 #发疯指数 #{title_en.replace(' ','_')}
"""
    return card.strip()


def sbti_build_group_chart(chat_id: str, chat_title: str = "本群") -> str:
    """
    统计群组 SBTI 性格分布，生成"本群战斗力分布图"
    """
    stats = sbti_group_stats.get(str(chat_id), {})
    if not stats:
        return "📊 本群暂无 SBTI 测试数据，快来 /sbti 参与测试！"

    dim_count = {}
    for uid, dom in stats.items():
        dim_count[dom] = dim_count.get(dom, 0) + 1

    total = len(stats)
    lines = [f"📊 *{md_escape(chat_title)} 战斗力分布图*\n", f"共 {total} 人参与测试\n", "━━━━━━━━━━━━━━━━━━━━━━"]

    # 按人数排序
    for dim_key, info in sorted(SBTI_DIMS.items(), key=lambda x: dim_count.get(x[0], 0), reverse=True):
        cnt = dim_count.get(dim_key, 0)
        if cnt == 0:
            continue
        pct = cnt / total * 100
        bar_len = round(pct / 10)
        bar = '▓' * bar_len + '░' * (10 - bar_len)
        lines.append(f"{info['emoji']} {info['cn']:6s} [{bar}] {cnt}人 ({pct:.0f}%)")

    # 趣味总结
    top_dim = max(dim_count, key=dim_count.get) if dim_count else 'chaos'
    GROUP_SUMMARY = {
        'apathy': "🏆 本群荣获「集体躺平认证」，生产力指数：负无穷。",
        'ego':    "🏆 本群是主角光环密度最高的宇宙区域，碰撞危险。",
        'chaos':  "🏆 本群发疯浓度超标，建议全员补充电解质。",
        'grind':  "🏆 本群卷王密度突破物理极限，HR已拉黑群主。",
        'vibe':   "🏆 本群氛围感溢出屏幕，连机器人都被感染了。",
        'lore':   "🏆 本群人设工程量庞大，建议申报世界文化遗产。",
    }
    lines.append("\n" + GROUP_SUMMARY.get(top_dim, "本群充满未知能量。"))
    lines.append(f"\n📤 分享本群战报：#SBTI2026 #{md_escape(chat_title)}战斗力图谱")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("\n🎯 *更多玄学服务*")
    lines.append("\n🔮 八字算命：/bazi")
    lines.append("\n💕 姻缘测算：/yinyuan")
    lines.append("\n✨ 紫微斗数：/ziwei")
    lines.append("\n🌤️ 今日运势：/today")
    lines.append("\n🧬 性格测试：/sbti")
    return "\n".join(lines)


def sbti_generate_dynamic_questions(scores: dict) -> list:
    """
    根据前3题得分，动态生成后3道题（LLM-style本地规则引擎）
    针对得分最高的2个维度深挖，探索边界情景
    """
    sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_dims = [d[0] for d in sorted_dims[:2]] if len(sorted_dims) >= 2 else ['chaos', 'apathy']

    # 动态题库（按维度组合）
    DYNAMIC_POOL = {
        ('apathy', 'ego'): [
            {
                "id": 4,
                "text": "有人在群里@你，你会？",
                "options": [
                    {"text": "已读不回，他们会理解的 👻", "score": {"apathy": 10}},
                    {"text": "先点赞，过三小时再回 😌", "score": {"ego": 8, "apathy": 2}},
                    {"text": "立刻回复，展示在线存在感 📱", "score": {"vibe": 10}},
                    {"text": "回复一个表情包代替所有文字", "score": {"chaos": 8}},
                ]
            },
            {
                "id": 5,
                "text": "你的人生 BGM 是？",
                "options": [
                    {"text": "寂静之声（白噪音升华版）", "score": {"apathy": 10}},
                    {"text": "史诗级主角入场曲", "score": {"ego": 10}},
                    {"text": "随机播放，拒绝被定义", "score": {"chaos": 8, "vibe": 2}},
                    {"text": "高效工作纯音乐，节奏120BPM", "score": {"grind": 10}},
                ]
            },
            {
                "id": 6,
                "text": "朋友说「你变了」，你的内心OS是？",
                "options": [
                    {"text": "是的，我进化了，你落后了", "score": {"ego": 10}},
                    {"text": "没有，我只是懒得装了", "score": {"apathy": 10}},
                    {"text": "（微笑）谢谢夸奖", "score": {"lore": 8}},
                    {"text": "开始反思自己的人设是否崩塌", "score": {"lore": 6, "ego": 4}},
                ]
            },
        ],
        ('chaos', 'vibe'): [
            {
                "id": 4,
                "text": "凌晨3点，你最可能在干什么？",
                "options": [
                    {"text": "研究一个没有意义但极其有趣的冷知识", "score": {"chaos": 10}},
                    {"text": "刷内容刷到天亮，拒绝睡眠", "score": {"vibe": 8, "apathy": 2}},
                    {"text": "做明天的计划，优化日程表", "score": {"grind": 10}},
                    {"text": "给消失了3个月的朋友发消息", "score": {"chaos": 6, "vibe": 4}},
                ]
            },
            {
                "id": 5,
                "text": "你如何解读「人生意义」这个问题？",
                "options": [
                    {"text": "是个 bug，不建议深想", "score": {"chaos": 10}},
                    {"text": "就是此刻的感受，其他都是多余", "score": {"vibe": 10}},
                    {"text": "=工资/996，可量化", "score": {"grind": 10}},
                    {"text": "正在构建中，敬请期待", "score": {"lore": 10}},
                ]
            },
            {
                "id": 6,
                "text": "在一个陌生聚会上，你是？",
                "options": [
                    {"text": "制造混乱，让大家记住你", "score": {"chaos": 10}},
                    {"text": "精准捕捉每个人的情绪，成为中心", "score": {"vibe": 10}},
                    {"text": "角落处理邮件，效率不打折", "score": {"grind": 8, "apathy": 2}},
                    {"text": "表演一个特别的自己，维持人设", "score": {"lore": 10}},
                ]
            },
        ],
        ('grind', 'lore'): [
            {
                "id": 4,
                "text": "你对「工作与生活平衡」的理解是？",
                "options": [
                    {"text": "工作就是生活，没有边界才是真热爱", "score": {"grind": 10}},
                    {"text": "生活是工作的素材，都是内容", "score": {"lore": 8, "grind": 2}},
                    {"text": "完全分离，下班后不看消息", "score": {"apathy": 10}},
                    {"text": "随心情，今天摸鱼明天疯狂", "score": {"chaos": 10}},
                ]
            },
            {
                "id": 5,
                "text": "你的「品牌故事」是什么？",
                "options": [
                    {"text": "从0到1，每天进步1%，复利奇迹", "score": {"grind": 10}},
                    {"text": "神秘感是最好的流量密码", "score": {"lore": 10}},
                    {"text": "我没有故事，我只有现在", "score": {"vibe": 8, "apathy": 2}},
                    {"text": "还没想好，可能是随机事件的集合", "score": {"chaos": 10}},
                ]
            },
            {
                "id": 6,
                "text": "五年后的你在做什么？",
                "options": [
                    {"text": "已完成阶段性目标，正在迭代下一版计划", "score": {"grind": 10}},
                    {"text": "活成了自己想象中那个最厉害的人", "score": {"lore": 8, "ego": 2}},
                    {"text": "躺在某个海边，已经不在乎了", "score": {"apathy": 10}},
                    {"text": "不知道，但一定很有意思", "score": {"vibe": 6, "chaos": 4}},
                ]
            },
        ],
    }

    # 选择最匹配的题组
    key = tuple(top_dims[:2])
    reverse_key = tuple(reversed(top_dims[:2]))

    if key in DYNAMIC_POOL:
        return DYNAMIC_POOL[key]
    elif reverse_key in DYNAMIC_POOL:
        return DYNAMIC_POOL[reverse_key]
    else:
        # 默认随机组合
        all_sets = list(DYNAMIC_POOL.values())
        return random.choice(all_sets)


def sbti_process_answer(uid: str, answer_idx: int) -> tuple:
    """
    处理用户答案，返回(是否完成, 下一题文本或结果卡文本)
    返回: (done: bool, message: str, keyboard_options: list or None)
    """
    ctx = sbti_context.get(uid)
    if not ctx:
        return True, "⚠️ 测试会话已过期，请发送 /sbti 重新开始", None

    questions = ctx['questions']
    step = ctx['step']

    if step >= len(questions):
        return True, "⚠️ 测试已完成", None

    current_q = questions[step]
    options = current_q.get('options', [])

    if answer_idx < 0 or answer_idx >= len(options):
        return False, "⚠️ 无效选项，请重新选择", [opt['text'] for opt in options]

    # 累加得分
    chosen = options[answer_idx]
    for dim, pts in chosen.get('score', {}).items():
        ctx['scores'][dim] = ctx['scores'].get(dim, 0) + pts

    ctx['step'] += 1
    ctx['ts'] = time.time()

    # 检查是否全部完成（6题）
    if ctx['step'] >= len(ctx['questions']):
        result_card = sbti_build_result_card(ctx.get('name', '测试者'), ctx['scores'])
        # 更新群组统计
        chat_id = ctx.get('chat_id', uid)
        if chat_id not in sbti_group_stats:
            sbti_group_stats[chat_id] = {}
        sbti_group_stats[chat_id][uid] = sbti_get_dominant_dim(ctx['scores'])
        sbti_context.pop(uid, None)
        return True, result_card, None

    # 返回下一题
    next_q = ctx['questions'][ctx['step']]
    opts = next_q.get('options', [])
    return False, _sbti_format_question(next_q, ctx['step'] + 1), [o['text'] for o in opts]


def _sbti_format_question(q: dict, step_num: int) -> str:
    """格式化题目文本"""
    lines = [f"🧬 *SBTI 发疯指数测试* — 第 {step_num}/6 题\n"]
    if step_num > 3:
        lines[0] += "\n_(🤖 AI 已根据你的前3题答案动态生成本题)_\n"
    lines.append(f"*{md_escape(q['text'])}*\n")
    for i, opt in enumerate(q.get('options', []), 1):
        # 选项文字也需转义，防止 _ * [ ` 触发 Markdown 格式
        lines.append(f"{i}️⃣ {md_escape(opt['text'])}")
    lines.append("\n请回复数字 1-{} 选择答案".format(len(q.get('options', []))))
    return "\n".join(lines)


def sbti_start_test(uid: str, name: str, chat_id: str) -> tuple:
    """
    初始化 SBTI 测试，返回第一题文本和选项列表
    """
    sbti_context[uid] = _stamp({
        'step': 0,
        'scores': {'apathy': 0, 'ego': 0, 'chaos': 0, 'grind': 0, 'vibe': 0, 'lore': 0},
        'questions': random.sample(SBTI_FIXED_QUESTIONS, min(6, len(SBTI_FIXED_QUESTIONS))),
        'name': name,
        'chat_id': chat_id,
    })
    first_q = sbti_context[uid]['questions'][0]
    opts = [o['text'] for o in first_q.get('options', [])]
    return _sbti_format_question(first_q, 1), opts


# ============ UI ============
def main_menu():
    kb = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    kb.add("🔮 八字算命", "💕 姻缘测算")
    kb.add("✨ 紫微斗数", "🌤️ 今日运势")
    kb.add("🕐 吉时查询", "🍼 取名能手")
    kb.add("🧬 SBTI测试", "📚 帮助")
    return kb

HELP_TEXT = """📚 玄学大师使用帮助

📌 输入格式
• 姓名 1990年5月15日 10:00 男
• 1990-5-15 10:00 女

📋 服务功能
• 🔮 八字算命：四柱五行、格局、喜用神
• 💕 姻缘测算：配偶星、桃花
• ✨ 紫微斗数：命宫主星+十二宫位详批
• 🌤️ 今日运势：日建宜忌、吉时
• 🕐 吉时查询：十二时辰吉凶
• 🍼 取名能手：八字五行取名+数理分析
• 📈 流年大运：未来10年每年详细运势
• 💑 合婚分析：双方命盘详细对比
• 🧬 SBTI测试：2026发疯指数六维人格测试 🔥推荐

🧬 SBTI 专属命令
• 🔮 /sbti —开始个人发疯指数测试
• 👬 /sbti_group —查看本群战斗力分布图

🎯 *服务推荐*：测完SBTI后可以试试八字算命、姻缘测算等板块，Bot会指引你！

⚠️ 注意事项
• 需要完整生辰信息（年月日时）
• 阴阳历请明确说明
• 发送 /start 重新开始"""

MENU_ITEMS = {"🔮 八字算命","💕 姻缘测算","✨ 紫微斗数","🌤️ 今日运势",
              "🕐 吉时查询","🍼 取名能手","🧬 SBTI测试","📚 帮助"}

# ============ 消息处理 ============
@tb.message_handler(commands=['start'])
def start_cmd(msg):
    uid = str(msg.chat.id)
    user_service.pop(uid, None)
    for store in (date_type_wait, bazi_context, yinyuan_context, qiming_context, sbti_context):
        store.pop(uid, None)
    tb.send_message(msg.chat.id,
        "🏛️ *欢迎来到玄学大师*\n\n智能命理分析系统\n\n请选择服务：",
        reply_markup=main_menu(), parse_mode='Markdown')

# ── 命令别名：让 BotCommand 菜单里的 /bazi /yinyuan 等也能触发对应功能 ──
@tb.message_handler(commands=['bazi'])
def bazi_slash_cmd(msg):
    user_service[str(msg.chat.id)] = "bazi"
    tb.send_message(msg.chat.id, "🔮 *八字算命*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(commands=['yinyuan'])
def yinyuan_slash_cmd(msg):
    user_service[str(msg.chat.id)] = "yinyuan"
    tb.send_message(msg.chat.id, "💕 *姻缘测算*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(commands=['ziwei'])
def ziwei_slash_cmd(msg):
    user_service[str(msg.chat.id)] = "ziwei"
    tb.send_message(msg.chat.id, "✨ *紫微斗数*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(commands=['today'])
def today_slash_cmd(msg):
    try:
        result = generate_today_fortune_direct()
        tb.send_message(msg.chat.id, result, parse_mode='Markdown')
    except Exception as e:
        logger.exception(f"今日运势出错: {e}")
        tb.send_message(msg.chat.id, "⚠️ 获取运势时出错，请稍后重试。")

@tb.message_handler(commands=['jishi'])
def jishi_slash_cmd(msg):
    try:
        result = generate_jishi_today()
        tb.send_message(msg.chat.id, result, parse_mode='Markdown')
    except Exception as e:
        logger.exception(f"吉时查询出错: {e}")
        tb.send_message(msg.chat.id, "⚠️ 查询吉时时出错，请稍后重试。")

@tb.message_handler(commands=['qiming'])
def qiming_slash_cmd(msg):
    user_service[str(msg.chat.id)] = "qiming"
    tb.send_message(msg.chat.id, "🍼 *取名能手*\n\n请输入：出生年月日时 性别\n例：2020年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(commands=['help'])
def help_slash_cmd(msg):
    tb.send_message(msg.chat.id, HELP_TEXT)

@tb.message_handler(func=lambda m: m.text == "🔮 八字算命")
def bazi_cmd(msg):
    user_service[str(msg.chat.id)] = "bazi"
    tb.send_message(msg.chat.id, "🔮 *八字算命*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(func=lambda m: m.text == "💕 姻缘测算")
def yinyuan_cmd(msg):
    user_service[str(msg.chat.id)] = "yinyuan"
    tb.send_message(msg.chat.id, "💕 *姻缘测算*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(func=lambda m: m.text == "✨ 紫微斗数")
def ziwei_cmd(msg):
    user_service[str(msg.chat.id)] = "ziwei"
    tb.send_message(msg.chat.id, "✨ *紫微斗数*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(func=lambda m: m.text == "🌤️ 今日运势")
def today_cmd(msg):
    # 直接输出今日运势，无需输入生辰
    try:
        result = generate_today_fortune_direct()
        tb.send_message(msg.chat.id, result, parse_mode='Markdown')
    except Exception as e:
        logger.exception(f"今日运势出错: {e}")
        tb.send_message(msg.chat.id, "⚠️ 获取运势时出错，请稍后重试。")

@tb.message_handler(func=lambda m: m.text == "🕐 吉时查询")
def jishi_cmd(msg):
    # 直接输出今日吉时，无需输入生辰
    try:
        result = generate_jishi_today()
        tb.send_message(msg.chat.id, result, parse_mode='Markdown')
    except Exception as e:
        logger.exception(f"吉时查询出错: {e}")
        tb.send_message(msg.chat.id, "⚠️ 查询吉时时出错，请稍后重试。")

@tb.message_handler(func=lambda m: m.text == "🍼 取名能手")
def qiming_cmd(msg):
    user_service[str(msg.chat.id)] = "qiming"
    tb.send_message(msg.chat.id, "🍼 *取名能手*\n\n请输入：出生年月日时 性别\n例：2020年5月15日 10:00 男", parse_mode='Markdown')

@tb.message_handler(func=lambda m: m.text == "📚 帮助")
def help_cmd(msg):
    # HELP_TEXT 含 /sbti_group 等下划线字符，改为纯文本发送彻底避免 Markdown 解析错误
    tb.send_message(msg.chat.id, HELP_TEXT)

@tb.message_handler(commands=['sbti'])
def sbti_cmd(msg):
    """开始 SBTI 发疯指数测试"""
    uid = str(msg.chat.id)
    chat_id = str(msg.chat.id)
    # 安全获取用户名（频道消息 from_user 可能为 None）
    name = (msg.from_user.first_name if msg.from_user else None) or "测试者"
    intro = (
        "🧬 *SBTI 2026 全球发疯指数测试*\n\n"
        "共 6 题，从题库随机抽取，防背答案 📝\n"
        "测试完成后生成专属梗图卡，可一键转发 ✨\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 *测完还可以试试这些*\n"
        "🔮 /bazi — 八字算命\n"
        "💕 /yinyuan — 姻缘测算\n"
        "✨ /ziwei — 紫微斗数\n\n"
        "现在开始第一题 👇"
    )
    tb.send_message(msg.chat.id, intro, parse_mode='Markdown')
    first_q_text, options = sbti_start_test(uid, name, chat_id)

    kb = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    for i, opt in enumerate(options, 1):
        kb.add(f"{i}. {opt[:40]}")
    tb.send_message(msg.chat.id, first_q_text, parse_mode='Markdown', reply_markup=kb)

@tb.message_handler(func=lambda m: m.text == "🧬 SBTI测试")
def sbti_menu_cmd(msg):
    """菜单按钮触发 SBTI 测试"""
    sbti_cmd(msg)

@tb.message_handler(commands=['sbti_group'])
def sbti_group_cmd(msg):
    """查看本群 SBTI 战斗力分布图"""
    chat_id = str(msg.chat.id)
    chat_title = getattr(msg.chat, 'title', None) or "本群"
    result = sbti_build_group_chart(chat_id, chat_title)
    tb.send_message(msg.chat.id, result, parse_mode='Markdown')

@tb.message_handler(func=lambda m: True)
def handle(msg):
    uid  = str(msg.chat.id)
    text = msg.text.strip() if msg.text else ''
    if not text: return

    # 定期清理过期状态（防内存泄漏）
    for store in (date_type_wait, bazi_context, yinyuan_context, qiming_context, sbti_context):
        _clean_stale(store)

    if text.startswith('/') or text in MENU_ITEMS:
        return

    # ── SBTI 测试进行中：处理答案 ─────────────────────
    if uid in sbti_context:
        # 支持数字答案 "1" / "1. xxx" 两种格式
        num_match = re.match(r'^(\d+)[.\s]?', text)
        if num_match:
            answer_idx = int(num_match.group(1)) - 1
            done, response, next_opts = sbti_process_answer(uid, answer_idx)
            if done:
                # 结果卡含 ╔╗║ 等特殊字符及 [] () 括号，用纯文本避免 Markdown 解析失败
                tb.send_message(msg.chat.id, response,
                                reply_markup=main_menu())
            else:
                if next_opts:
                    kb = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
                    for i, opt in enumerate(next_opts, 1):
                        kb.add(f"{i}. {opt[:40]}")
                    tb.send_message(msg.chat.id, response, parse_mode='Markdown', reply_markup=kb)
                else:
                    tb.send_message(msg.chat.id, response, parse_mode='Markdown')
        else:
            # 用户输入非数字时提示
            ctx = sbti_context.get(uid, {})
            current_step = ctx.get('step', 0)
            if current_step < len(ctx.get('questions', [])):
                q = ctx['questions'][current_step]
                opts = [o['text'] for o in q.get('options', [])]
                kb = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
                for i, opt in enumerate(opts, 1):
                    kb.add(f"{i}. {opt[:40]}")
                tb.send_message(msg.chat.id,
                    f"请回复数字 1-{len(opts)} 选择答案哦～",
                    reply_markup=kb)
        return

    # ── 等待日期类型确认 ─────────────────────────────
    if uid in date_type_wait:
        if   any(w in text for w in ['阳历','公历','新历']): date_type = '阳历'
        elif any(w in text for w in ['阴历','农历','旧历']): date_type = '阴历'
        else:
            tb.send_message(msg.chat.id, "请回复「阳历」或「阴历」")
            return

        ctx = date_type_wait.pop(uid)
        birth_info = ctx['birth_info']
        name, gender, svc = ctx['name'], ctx['gender'], ctx['svc']
        original_input = ctx.get('original_input', birth_info.copy())

        lunar_date = ""
        if date_type == "阳历":
            lunar_date = solar_to_lunar(birth_info['year'], birth_info['month'], birth_info['day'])
        else:
            sd = lunar_to_solar(birth_info['year'], birth_info['month'], birth_info['day'])
            lunar_date = solar_to_lunar(sd['year'], sd['month'], sd['day'])
            birth_info = {'year':sd['year'],'month':sd['month'],'day':sd['day'],
                          'hour':birth_info['hour'],'minute':birth_info.get('minute',0)}

        try:
            if   svc == "bazi":
                result, _ = generate_bazi_detail(name, birth_info, gender, date_type, lunar_date)
                tb.send_message(msg.chat.id, result, parse_mode='Markdown')
                bazi_context[uid] = _stamp({'name':name,'birth_info':birth_info,'gender':gender,
                                            'date_type':date_type,'lunar_date':lunar_date})
            elif svc == "yinyuan":
                result = generate_yinyuan_detail(name, birth_info, gender)
                tb.send_message(msg.chat.id, result, parse_mode='Markdown')
                yinyuan_context[uid] = _stamp({'name':name,'birth_info':birth_info,'gender':gender})
            elif svc == "ziwei":
                result = generate_ziwei_detail(name, birth_info, gender, date_type, original_input)
                tb.send_message(msg.chat.id, result, parse_mode='Markdown')
            elif svc == "today":
                result = generate_today_fortune(name, birth_info, gender)
                tb.send_message(msg.chat.id, result, parse_mode='Markdown')
            elif svc == "qiming":
                result = generate_qiming_detail(name, birth_info, gender)
                tb.send_message(msg.chat.id, result, parse_mode='Markdown')
                qiming_context[uid] = _stamp({'name':name,'birth_info':birth_info,'gender':gender})
            elif svc == "liunian":
                result = generate_liunian_dayun(name, birth_info, gender, lunar_date)
                tb.send_message(msg.chat.id, result, parse_mode='Markdown')
                # 保留基础上下文，便于后续再次触发流年/大运时直接复用
                bazi_context[uid] = _stamp({'name':name,'birth_info':birth_info,'gender':gender,
                                            'date_type':date_type,'lunar_date':lunar_date})
            elif svc == "jishi":
                result = generate_jishi_detail(birth_info, gender)
                tb.send_message(msg.chat.id, result, parse_mode='Markdown')
        except Exception as e:
            logger.exception(f"生成分析时出错: {e}")
            tb.send_message(msg.chat.id, "⚠️ 分析时发生错误，请检查输入格式后重试。")

        user_service.pop(uid, None)
        return

    # ── 流年大运 / 合婚分析（VIP版直接开放）─────────────
    if text in ["流年大运", "流年", "大运"]:
        # 若已有八字上下文，直接输出流年大运，避免重复索要生辰
        if uid in bazi_context:
            ctx = bazi_context[uid]
            result = generate_liunian_dayun(
                ctx.get('name', '缘主'),
                ctx['birth_info'],
                ctx.get('gender', '男'),
                ctx.get('lunar_date', '')
            )
            tb.send_message(msg.chat.id, result, parse_mode='Markdown')
            return
        user_service[uid] = "liunian"
        tb.send_message(msg.chat.id, "📈 *流年大运分析*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')
        return
    if text in ["合婚分析", "合婚", "合八字"]:
        user_service[uid] = "hehun"
        yinyuan_context[uid] = _stamp({'waiting_hehun': True})
        tb.send_message(msg.chat.id, "💑 *合婚分析*\n\n请输入双方 姓名 出生年月日时 性别，例如：\n张三 1996年5月15日 10:00 男\n李丽 2000年8月26日 18:00 女", parse_mode='Markdown')
        return

    # ── 合婚：输入双方生辰 ───────────────────────────
    if uid in yinyuan_context and yinyuan_context[uid].get('waiting_hehun'):
        lines = [ln.strip() for ln in re.split(r'[\n\r]+', text) if ln.strip()]
        if len(lines) == 2:
            pattern = r'^(\S+)\s+(.+?)\s+(男|女)$'
            m1 = re.match(pattern, lines[0])
            m2 = re.match(pattern, lines[1])
            if m1 and m2:
                b1 = parse_date_flexible(m1.group(2))
                b2 = parse_date_flexible(m2.group(2))
                g1, g2 = m1.group(3), m2.group(3)
                if b1 and b2 and g1 != g2:
                    male_info = b1 if g1 == '男' else b2
                    female_info = b2 if g2 == '女' else b1
                    result = generate_hehun_detail(male_info, female_info)
                    tb.send_message(msg.chat.id, result, parse_mode='Markdown')
                    yinyuan_context.pop(uid, None)
                    user_service.pop(uid, None)
                    return
        tb.send_message(msg.chat.id, "请按格式输入双方信息：\n张三 1996年5月15日 10:00 男\n李丽 2000年8月26日 18:00 女\n（必须一男一女）")
        return

    # ── 取名：输入姓氏 ───────────────────────────────
    # [修复18] 加纯汉字+长度限制，避免普通文本误入姓氏流程
    if uid in qiming_context and not parse_date_flexible(text):
        if re.fullmatch(r'[\u4e00-\u9fff]{1,4}', text):
            ctx = qiming_context.pop(uid)
            result = generate_qiming_with_surname(ctx['name'], ctx['birth_info'], ctx['gender'], text)
            tb.send_message(msg.chat.id, result, parse_mode='Markdown')
            return

    # ── 关键词全局检测（VIP版：改为直接引导功能）──────────
    svc = user_service.get(uid)
    if not parse_date_flexible(text):
        paid_key = get_paid_key(text)
        if paid_key:
            service_map = {'liunian': 'liunian', 'hehun': 'yinyuan', 'qiming': 'qiming', 'ziwei': 'ziwei'}
            user_service[uid] = service_map.get(paid_key, 'bazi')
            tb.send_message(msg.chat.id, "✅ 已为您开启对应功能，请输入：姓名 出生年月日时 性别", parse_mode='Markdown')
            return

    # ── 正常生辰输入流程 ─────────────────────────────
    birth_info = parse_date_flexible(text)
    if not birth_info:
        if svc:
            tb.send_message(msg.chat.id, "⚠️ 未能识别生辰信息，请按格式输入：\n1990年5月15日 10:00 男")
        return

    gender = parse_gender(text)
    name   = "缘主"
    for part in text.split():
        if part and not re.search(r'\d', part) and part not in ['男','女','阳历','阴历','她','她们']:
            if 1 <= len(part) <= 6:
                name = part; break

    date_type_wait[uid] = _stamp({
        'birth_info': birth_info,
        'original_input': birth_info.copy(),
        'name': name, 'gender': gender,
        'svc': svc or 'bazi'
    })
    tb.send_message(msg.chat.id,
        f"📅 *日期类型确认*\n\n您输入的是「阳历」还是「阴历」？\n请回复：阳历 或 阴历\n\n"
        f"原始输入：{birth_info['year']}年{birth_info['month']}月{birth_info['day']}日 {birth_info['hour']:02d}:00",
        parse_mode='Markdown')



# ============================================================
# Webhook 服务器 — 使用 Flask（修复 Render 部署无回复问题）
# ============================================================
# 【根本原因】
# 1. 原代码用 http.server.HTTPServer 手写服务器，在 Render 上
#    必须通过 gunicorn/uvicorn 启动，导致 if __name__=='__main__'
#    块完全不执行 → set_webhook() 从未被调用 → Telegram 不知道
#    往哪里推消息。
# 2. 没有根路径 "/" 的健康检查端点 → Render 认为服务不健康反复重启。
# 3. WEBHOOK_URL 若未设置，Telegram 推送无目标。
# 4. Render 免费版 15 分钟休眠 → 用 Flask + 启动时立即注册 Webhook
#    解决，并提供 keep-alive 端点。
#
# 【修复方案】
# - 改用 Flask 作为 HTTP 服务器（Render 原生支持）
# - 启动时自动调用 set_webhook（不依赖 __main__ 块）
# - 添加 "/" 健康检查端点，返回 200
# - WEBHOOK_URL 从环境变量读取（Render 环境变量面板配置）
# - requirements.txt 中需要加入 flask
# ============================================================

try:
    from flask import Flask, request, abort
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logger.warning("Flask 未安装，将回退到 polling 模式。生产环境请安装 flask。")

# ---- Flask 应用 ----
if FLASK_AVAILABLE:
    app = Flask(__name__)

    @app.route('/', methods=['GET', 'POST'])
    def root_handler():
        """
        根路径兼容处理：
        - GET：健康检查
        - POST：兼容把 WEBHOOK_URL 配成根路径 "/" 的场景
        """
        if request.method == 'GET':
            return '{"status":"ok","service":"FortuneMaster Bot v3.1"}', 200, {'Content-Type': 'application/json'}
        return _process_telegram_update()

    def _process_telegram_update():
        """统一处理 Telegram Update，供 / 与 /webhook 复用。"""
        ctype = request.headers.get('content-type', '').lower()
        if 'application/json' not in ctype:
            abort(403)
        json_str = request.get_data(as_text=True)
        try:
            update = Update.de_json(json_str)
            tb.process_new_updates([update])
        except Exception as e:
            logger.exception(f"处理 update 失败: {e}")
        return '{"ok":true}', 200, {'Content-Type': 'application/json'}

    @app.route('/webhook', methods=['POST'])
    def webhook():
        """接收 Telegram 推送的更新"""
        return _process_telegram_update()

    @app.route('/set_webhook', methods=['GET'])
    def manual_set_webhook():
        """手动触发重新注册 Webhook（调试用）"""
        webhook_url = os.getenv('WEBHOOK_URL', '')
        if not webhook_url:
            return '{"error":"WEBHOOK_URL not set"}', 400
        tb.remove_webhook()
        result = tb.set_webhook(webhook_url)
        return f'{{"ok":{str(result).lower()},"url":"{webhook_url}"}}', 200


def register_webhook():
    """启动时注册 Webhook 并同步 Bot 菜单命令（兼容 gunicorn 和直接运行两种方式）"""
    # ── 注册 Bot 命令菜单（Telegram 左下角 "/" 按钮里显示的命令列表）──
    bot_commands = [
        BotCommand("start",      "🏛️ 开始 / 返回主菜单"),
        BotCommand("bazi",       "🔮 八字算命"),
        BotCommand("yinyuan",    "💕 姻缘测算"),
        BotCommand("ziwei",      "✨ 紫微斗数"),
        BotCommand("today",      "🌤️ 今日运势"),
        BotCommand("jishi",      "🕐 吉时查询"),
        BotCommand("qiming",     "🍼 取名能手"),
        BotCommand("sbti",       "🧬 SBTI性格测试 — 2026发疯指数"),
        BotCommand("sbti_group", "📊 本群战斗力分布图"),
        BotCommand("help",       "📚 帮助说明"),
    ]
    try:
        tb.set_my_commands(bot_commands)
        logger.info("✅ Bot 命令菜单注册成功（含 /sbti、/sbti_group）")
    except Exception as e:
        logger.warning(f"⚠️ Bot 命令菜单注册失败（不影响功能）: {e}")

    # ── 注册 Webhook ──────────────────────────────────────────────
    webhook_url = os.getenv('WEBHOOK_URL', '')
    if not webhook_url:
        logger.warning("⚠️  WEBHOOK_URL 未设置！Bot 将无法接收消息。")
        logger.warning("    请在 Render 环境变量中添加：WEBHOOK_URL=https://你的域名.onrender.com/webhook")
        return
    try:
        tb.remove_webhook()
        ok = tb.set_webhook(webhook_url)
        if ok:
            logger.info(f"✅ Webhook 注册成功: {webhook_url}")
        else:
            logger.error(f"❌ Webhook 注册失败，请检查 TOKEN 和 URL")
    except Exception as e:
        logger.exception(f"注册 Webhook 时出错: {e}")


# 模块加载时即注册 Webhook
# gunicorn 导入此模块时会执行这里，确保 Webhook 在任何启动方式下都会注册
register_webhook()


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))

    if FLASK_AVAILABLE and os.getenv('WEBHOOK_URL'):
        # Webhook 模式（生产环境）
        logger.info(f"🚀 玄学大师 Bot v3.1 启动（Webhook 模式），端口 {PORT}")
        # 直接运行时用 Flask 内置服务器（生产建议用 gunicorn）
        app.run(host='0.0.0.0', port=PORT, debug=False)
    else:
        # Polling 模式（本地开发 / 未配置 WEBHOOK_URL 时自动回退）
        logger.info("🔄 启动 Polling 模式（本地开发）")
        tb.remove_webhook()
        tb.infinity_polling(timeout=20, long_polling_timeout=10)


# ============ 玄学行业&用户痛点整改方案（用户收费版）============
XUAN_VIP_RECTIFICATION_PLAN = {
    "用户可见升级": [
        "报告结构升级：先给结论，再解释原因，最后给出可执行建议。",
        "交付标准透明：下单前明确服务内容、交付时效、售后方式。",
        "建议落地化：每条建议附使用场景和时间窗口，减少“听完不会做”。",
        "响应提速：先返回快速摘要，再补充完整深度报告。",
        "隐私保护：用户资料仅用于本次分析，不对外展示。"
    ],
    "服务承诺": [
        "不使用“绝对保证”类表述，提供风险与条件提示。",
        "涉及健康/财务/法律内容，统一增加理性决策提醒。"
    ]
}


def generate_vip_rectification_text() -> str:
    """收费版：输出用户可见整改说明。"""
    lines = ["🌟 服务升级公告（VIP收费版）", "\n【用户可见升级】"]
    lines.extend([f"{i+1}. {x}" for i, x in enumerate(XUAN_VIP_RECTIFICATION_PLAN["用户可见升级"])])
    lines.append("\n【服务承诺】")
    lines.extend([f"{i+1}. {x}" for i, x in enumerate(XUAN_VIP_RECTIFICATION_PLAN["服务承诺"])])
    return "\n".join(lines)
