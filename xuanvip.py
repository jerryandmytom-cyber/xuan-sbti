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
from telebot.types import Update, ReplyKeyboardMarkup

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

# ============ UI ============
def main_menu():
    kb = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    kb.add("🔮 八字算命", "💕 姻缘测算")
    kb.add("✨ 紫微斗数", "🌤️ 今日运势")
    kb.add("🕐 吉时查询", "🍼 取名能手")
    kb.add("📚 帮助")
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
• 📈 流年分析：未来10年每年详细运势
• 💑 合婚分析：双方命盘详细对比

⚠️ 注意事项
• 需要完整生辰信息（年月日时）
• 阴阳历请明确说明
• 发送 /start 重新开始"""

MENU_ITEMS = {"🔮 八字算命","💕 姻缘测算","✨ 紫微斗数","🌤️ 今日运势",
              "🕐 吉时查询","🍼 取名能手","📚 帮助"}

# ============ 消息处理 ============
@tb.message_handler(commands=['start'])
def start_cmd(msg):
    uid = str(msg.chat.id)
    user_service.pop(uid, None)
    for store in (date_type_wait, bazi_context, yinyuan_context, qiming_context):
        store.pop(uid, None)
    tb.send_message(msg.chat.id,
        "🏛️ *欢迎来到玄学大师*\n\n智能命理分析系统\n\n请选择服务：",
        reply_markup=main_menu(), parse_mode='Markdown')

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
    tb.send_message(msg.chat.id, HELP_TEXT, parse_mode='Markdown')

@tb.message_handler(func=lambda m: True)
def handle(msg):
    uid  = str(msg.chat.id)
    text = msg.text.strip() if msg.text else ''
    if not text: return

    # 定期清理过期状态（防内存泄漏）
    for store in (date_type_wait, bazi_context, yinyuan_context, qiming_context):
        _clean_stale(store)

    if text.startswith('/') or text in MENU_ITEMS:
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
    """启动时注册 Webhook（兼容 gunicorn 和直接运行两种方式）"""
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
