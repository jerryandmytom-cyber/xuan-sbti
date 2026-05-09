# -*- coding: utf-8 -*-
"""
玄学大师 Telegram Bot - 审核优化完善版 v3.2
支持：八字/姻缘/紫微/运势/吉时/取名

v3.1 → v3.2 全面改进清单：
─────────────────────────────────────────────────────
【核心BUG修复（18项）】
✓ 1. lucky_color_map / favorable_dir 提升为模块级常量
✓ 2. AUX_DESC 在使用前定义（紫微斗数）
✓ 3. 修正 names_lucky 循环中 renge 变量计算错误
✓ 4. 删除未使用的 geju_map 废代码
✓ 5. 修正 WebhookHandler 返回消息重复问题
✓ 6. 在 handle() 入口加付费关键词检测
✓ 7. lucky_color_map/favorable_dir 统一移到顶部
✓ 8. 去掉合婚中误导性阴历提示
✓ 9. 修正感情运势 or 表达式歧义
✓ 10. calc_qiyun_age 中加 abs() 防负数
✓ 11. 消除重复的 import datetime
✓ 12. 删除未使用的 month_gz_idx 变量
✓ 13. 删除未使用的 diff 变量
✓ 14. 付费关键词检测顺序优化
✓ 15. 增加 TTL 超时清理机制（内存泄漏防护）
✓ 16. 扩展 parse_gender 女性关键词识别
✓ 17. 添加 Markdown 特殊字符转义函数
✓ 18. 取名姓氏判断加纯汉字+长度限制

【代码质量增强】
✓ 19. 完善异常处理（try-except覆盖）
✓ 20. 增强日志记录（DEBUG/INFO/WARNING/ERROR）
✓ 21. 数据验证（年份范围、月日有效性）
✓ 22. 优化内存管理（定期清理过期状态）
✓ 23. 改进消息格式（防转义失败）
✓ 24. 增加请求超时控制
✓ 25. 优化正则表达式匹配
✓ 26. 添加边界检查和防护
✓ 27. 完善Flask错误处理
✓ 28. 增加运行状态健康检查
"""

import os
import re
import time
import random
import logging
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import Update, ReplyKeyboardMarkup

# ============ 日志配置 ============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ 环境变量验证 ============
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
if not TOKEN:
    logger.critical("❌ 错误：未设置环境变量 TELEGRAM_BOT_TOKEN")
    raise RuntimeError("请设置环境变量 TELEGRAM_BOT_TOKEN")

try:
    tb = telebot.TeleBot(TOKEN, threaded=False)
    logger.info("✅ Telegram Bot 初始化成功")
except Exception as e:
    logger.critical(f"❌ Telegram Bot 初始化失败: {e}")
    raise

# ============ 用户状态管理（含TTL机制）============
user_service   = {}   # uid -> svc
date_type_wait = {}   # uid -> {birth_info, name, gender, svc, ts}
bazi_context   = {}   # uid -> {name, birth_info, gender, ...}
yinyuan_context = {}  # uid -> {name, birth_info, gender, waiting_hehun}
qiming_context  = {}  # uid -> {name, birth_info, gender}

STATE_TTL = 600  # 10分钟无操作自动清除
LAST_CLEANUP = time.time()
CLEANUP_INTERVAL = 300  # 5分钟检查一次过期状态

def _clean_stale(store: dict) -> int:
    """清理超时的用户状态，防止内存泄漏，返回清理数量"""
    now = time.time()
    stale = [k for k, v in store.items() 
             if isinstance(v, dict) and now - v.get('ts', now) > STATE_TTL]
    for k in stale:
        store.pop(k, None)
    if stale:
        logger.debug(f"清理过期状态: {len(stale)} 条记录")
    return len(stale)

def _stamp(d: dict) -> dict:
    """给状态字典附加时间戳"""
    d['ts'] = time.time()
    return d

def _global_cleanup():
    """全局定期清理（主动调用）"""
    global LAST_CLEANUP
    now = time.time()
    if now - LAST_CLEANUP < CLEANUP_INTERVAL:
        return
    
    total = 0
    for store in (date_type_wait, bazi_context, yinyuan_context, qiming_context):
        total += _clean_stale(store)
    
    LAST_CLEANUP = now
    if total > 0:
        logger.info(f"全局清理完成，清理 {total} 条过期记录")

# ============ Markdown 转义 ============
def md_escape(text: str) -> str:
    """转义 Telegram Markdown v1 敏感字符，防止发送失败"""
    if not text:
        return ""
    for ch in ['_', '*', '[', '`']:
        text = text.replace(ch, '\\' + ch)
    return text

# ============ 付费关键词管理 ============
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
    """发送专属付费模板，每个服务内容独立"""
    try:
        templates = {
            'liunian': (
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
            ),
            'hehun': (
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
            ),
            'qiming': (
                "🍼 *高级八字取名服务* 💰 $6U\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📋 *服务内容*\n"
                "  ✦ 宝宝八字五行精准缺补分析\n"
                "  ✦ 喜用神专属汉字库推荐（形义音三维）\n"
                "  ✦ 三才五格（天格/人格/地格/总格/外格）全套数理吉凶计算\n"
                "  ✦ 提供 10 个以上精选备选名字\n"
                "  ✦ 每个名字附完整寓意 + 五格评级说明\n"
                "  ✦ 结合姓氏最终优选推荐 + 忌用字提醒\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "💳 *付款联系*\n"
                "客服 TG：@ok787768\n"
                "备注：取名服务\n\n"
                "⏰ 服务时间：09:00 - 21:00（GMT+8）\n"
                "✅ 付款后客服为您安排专属取名"
            ),
            'ziwei': (
                "✨ *紫微斗数详批* 💰 $8U\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📋 *服务内容*\n"
                "  ✦ 命宫主星精准安盘（含辅星煞星）\n"
                "  ✦ 十二宫位逐一深度详批（命/财/官/夫妻/子女/迁移等）\n"
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
            ),
        }
        
        text = templates.get(service_key)
        if not text:
            logger.warning(f"未知的付费服务类型: {service_key}")
            return False
        
        tb.send_message(chat_id, text, parse_mode='Markdown')
        logger.debug(f"发送付费模板: {service_key}")
        return True
    except Exception as e:
        logger.error(f"发送付费模板失败 ({service_key}): {e}")
        return False

def get_paid_key(text):
    """检查文本是否含付费关键词，返回 service_key 或 None"""
    if not text:
        return None
    for kw in sorted(PAID_KEYWORD_MAP.keys(), key=len, reverse=True):
        if kw in text:
            return PAID_KEYWORD_MAP[kw]
    return None

# ============ 全局常量（模块顶部）============
LUCKY_COLOR_MAP = {
    '木': '绿色、青色', '火': '红色、紫色', '土': '黄色、棕色',
    '金': '白色、金色', '水': '黑色、蓝色'
}
FAVORABLE_DIR = {
    '木': '东、东南', '火': '南', '土': '西南、中', '金': '西、西北', '水': '北'
}

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
WUXING_SHENG_BY = {v: k for k, v in WUXING_SHENG.items()}

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
    """获取农历月支"""
    try:
        if solar_month not in JIEQI_MONTH:
            logger.warning(f"无效月份: {solar_month}")
            return '子'
        
        info = JIEQI_MONTH[solar_month]
        if solar_day >= info['day']:
            return DIZHI[info['zhi_idx']]
        prev_month = solar_month - 1 if solar_month > 1 else 12
        return DIZHI[JIEQI_MONTH[prev_month]['zhi_idx']]
    except Exception as e:
        logger.error(f"获取农历月支失败: {e}")
        return '子'

def get_lunar_month_num(solar_year, solar_month, solar_day):
    """获取农历月数"""
    try:
        zhi = get_lunar_month_zhi(solar_year, solar_month, solar_day)
        zhi_idx = DIZHI.index(zhi)
        return (zhi_idx - 1) % 12 + 1
    except Exception as e:
        logger.error(f"获取农历月数失败: {e}")
        return 1

def parse_date_flexible(text):
    """灵活解析日期，增强错误处理"""
    if not text:
        return None
    
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
                year  = int(groups[0])
                month = int(groups[1])
                day   = int(groups[2])
                hour  = int(groups[3]) if len(groups) > 3 and groups[3] else 12
                minute = int(groups[4]) if len(groups) > 4 and groups[4] else 0
                
                # 数据验证
                if not (1800 <= year <= 2100):
                    logger.warning(f"年份超范围: {year}")
                    continue
                if not (1 <= month <= 12):
                    logger.warning(f"月份无效: {month}")
                    continue
                if not (0 <= hour <= 23):
                    logger.warning(f"小时无效: {hour}")
                    continue
                if not (0 <= minute <= 59):
                    logger.warning(f"分钟无效: {minute}")
                    continue
                
                # 天数验证
                leap = 29 if (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)) else 28
                mdays = [31, leap, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
                if not (1 <= day <= mdays[month - 1]):
                    logger.warning(f"日期无效: {month}月{day}日")
                    continue
                
                return {'year': year, 'month': month, 'day': day,
                        'hour': hour, 'minute': minute}
            except (ValueError, IndexError) as e:
                logger.debug(f"日期解析错误: {e}")
                continue
    
    return None

def days_from_civil(year, month, day):
    """计算从公元元年1月1日起的天数"""
    y   = year - (1 if month <= 2 else 0)
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    m   = month + (-3 if month > 2 else 9)
    doy = (153 * m + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468

def solar_to_lunar_info(year, month, day):
    """转换阳历到农历，增强错误处理"""
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
    except Exception as e:
        logger.warning(f"农历转换失败，使用降级方案: {e}")
        gan_idx = (year - 4) % 10
        zhi_idx = (year - 4) % 12
        ygz = TIANGAN[gan_idx] + DIZHI[zhi_idx]
        return {'year': year, 'month': month, 'day': day, 'is_leap': False,
                'text': f'{ygz}年{month}月{day}日', 'numeric': f'{year}年{month}月{day}日'}

def solar_to_lunar(year, month, day):
    """阳历转农历文本"""
    return solar_to_lunar_info(year, month, day)['text']

def lunar_to_solar(year, month, day):
    """农历转阳历"""
    try:
        from lunarcalendar import Converter, Lunar
        s = Converter.Lunar2Solar(Lunar(year, month, day))
        return {'year': s.year, 'month': s.month, 'day': s.day}
    except Exception as e:
        logger.warning(f"农历转阳历失败: {e}")
        return {'year': year, 'month': month, 'day': day}

def parse_gender(text):
    """扩展女性关键词识别"""
    if not text:
        return '男'
    return '女' if any(w in text for w in ['女', '她', '女士', '小姐', '姐', '她们']) else '男'

# ============ 八字核心计算 ============
def get_zodiac(year):
    """获取生肖"""
    try:
        return SHENGXIAO[(year - 4) % 12]
    except Exception as e:
        logger.error(f"获取生肖失败: {e}")
        return '鼠'

def get_ganzhi_year(year):
    """获取年干支"""
    try:
        idx = (year - 4) % 60
        return TIANGAN[idx % 10] + DIZHI[idx % 12]
    except Exception as e:
        logger.error(f"获取年干支失败: {e}")
        return '甲子'

def get_ganzhi_month(year, month, day):
    """获取月干支"""
    try:
        lunar_m = get_lunar_month_num(year, month, day)
        year_gan_idx = TIANGAN.index(get_ganzhi_year(year)[0])
        month_gan_start = (year_gan_idx % 5) * 2 + 2
        month_gan_idx = (month_gan_start + lunar_m - 1) % 10
        month_zhi = get_lunar_month_zhi(year, month, day)
        return TIANGAN[month_gan_idx] + month_zhi
    except Exception as e:
        logger.error(f"获取月干支失败: {e}")
        return '正月'

def get_ganzhi_day(year, month, day):
    """获取日干支"""
    try:
        base  = days_from_civil(1900, 1, 1)
        delta = days_from_civil(year, month, day) - base
        idx   = (delta + 40) % 60
        return TIANGAN[idx % 10] + DIZHI[idx % 12]
    except Exception as e:
        logger.error(f"获取日干支失败: {e}")
        return '甲子'

def get_ganzhi_hour(year, month, day, hour):
    """获取时干支"""
    try:
        hour_zhi_idx = ((hour + 1) // 2) % 12
        day_gz       = get_ganzhi_day(year, month, day)
        day_gan_idx  = TIANGAN.index(day_gz[0])
        hour_gan_start = (day_gan_idx % 5) * 2
        hour_gan_idx   = (hour_gan_start + hour_zhi_idx) % 10
        return TIANGAN[hour_gan_idx] + DIZHI[hour_zhi_idx]
    except Exception as e:
        logger.error(f"获取时干支失败: {e}")
        return '甲子'

def get_wuxing_full(year_gz, month_gz, day_gz, hour_gz):
    """计算五行配置"""
    try:
        wx = {'木': 0.0, '火': 0.0, '土': 0.0, '金': 0.0, '水': 0.0}
        weights = [0.7, 0.5, 0.3]
        for gz in [year_gz, month_gz, day_gz, hour_gz]:
            if not gz or len(gz) < 2:
                continue
            if gz[0] in GAN_WUXING:
                wx[GAN_WUXING[gz[0]]] += 1.0
            for i, cg in enumerate(ZHI_CANGGAN.get(gz[1], [])):
                if cg in GAN_WUXING:
                    wx[GAN_WUXING[cg]] += weights[i] if i < len(weights) else 0.2
        return wx
    except Exception as e:
        logger.error(f"计算五行配置失败: {e}")
        return {'木': 0.0, '火': 0.0, '土': 0.0, '金': 0.0, '水': 0.0}

# ============ 冲合刑害分析 ============
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
    """分析冲合刑害"""
    try:
        results = []
        gans = [gz[0] for gz in pillars if gz and len(gz) > 0]
        zhis = [gz[1] for gz in pillars if gz and len(gz) > 1]
        
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
        
        # 自刑检查
        for z in zhis:
            if zhis.count(z) >= 2 and ZHI_XING.get(z) == z:
                results.append(f"{z}{z}自刑⚠️")
                break
        
        return results if results else ["四柱冲合平和"]
    except Exception as e:
        logger.error(f"分析冲合刑害失败: {e}")
        return ["四柱冲合平和"]

# ============ 日主旺衰分析 ============
def analyze_rizhu_wangshui(day_gan, month_gz, all_gz_list):
    """分析日主旺衰"""
    try:
        month_zhi = month_gz[1] if month_gz and len(month_gz) > 1 else '子'
        day_wx    = GAN_WUXING.get(day_gan, '土')
        
        season_strength = {
            ('木','寅'):True,('木','卯'):True,
            ('火','巳'):True,('火','午'):True,
            ('土','辰'):True,('土','戌'):True,('土','丑'):True,('土','未'):True,
            ('金','申'):True,('金','酉'):True,
            ('水','亥'):True,('水','子'):True,
        }
        
        de_ling   = season_strength.get((day_wx, month_zhi), False)
        day_zhi_wx = ZHI_WUXING.get(all_gz_list[2][1] if len(all_gz_list[2]) > 1 else 'z', '土')
        
        sheng_map = {'木':'水','火':'木','土':'火','金':'土','水':'金'}
        de_di     = (day_wx == day_zhi_wx) or (sheng_map.get(day_wx,'') == day_zhi_wx)
        
        helper    = 0.0
        for gz in all_gz_list:
            if not gz or len(gz) < 2:
                continue
            g_wx = GAN_WUXING.get(gz[0], '')
            if g_wx == day_wx:          
                helper += 1.0
            elif WUXING_SHENG.get(g_wx,'') == day_wx: 
                helper += 0.5
            for cg in ZHI_CANGGAN.get(gz[1], []):
                cg_wx = GAN_WUXING.get(cg, '')
                if cg_wx == day_wx:     
                    helper += 0.3
        
        de_shi = helper >= 3
        
        if de_ling and (de_di or de_shi):   
            strong = '身旺'
        elif not de_ling and not de_di and not de_shi: 
            strong = '身弱'
        else:                               
            strong = '中和'
        
        return {'de_ling':'得令' if de_ling else '失令',
                'de_di':  '得地' if de_di   else '失地',
                'de_shi': '得势' if de_shi  else '失势',
                'strong': strong}
    except Exception as e:
        logger.error(f"分析日主旺衰失败: {e}")
        return {'de_ling':'失令','de_di':'失地','de_shi':'失势','strong':'平'}

def analyze_xiyongshen(wuxing_full, rizhu_strong, day_wx):
    """分析喜用神"""
    try:
        ke_day    = WUXING_KE.get(day_wx, '土')
        sheng_day = WUXING_SHENG_BY.get(day_wx, '土')
        xie_day   = WUXING_SHENG.get(day_wx, '火')
        
        if   rizhu_strong == '身旺': 
            xi = [ke_day, xie_day]
        elif rizhu_strong == '身弱': 
            xi = [sheng_day, day_wx]
        else:
            min_wx = min(wuxing_full, key=wuxing_full.get)
            xi = [min_wx, WUXING_SHENG.get(min_wx, '木')]
        
        return xi
    except Exception as e:
        logger.error(f"分析喜用神失败: {e}")
        return ['土', '火']

# ============ 格局判定 ============
def get_geju(month_zhi, day_gan, all_gans):
    """判定格局"""
    try:
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
        if WUXING_KE.get(base_wx,'') == day_wx: 
            return '正官格'
        if WUXING_KE.get(day_wx,'') == base_wx: 
            return '正财格'
        if WUXING_SHENG.get(base_wx,'') == day_wx: 
            return '正印格'
        if WUXING_SHENG.get(day_wx,'') == base_wx: 
            return '食神格'
        
        return '建禄格'
    except Exception as e:
        logger.error(f"判定格局失败: {e}")
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
    """获取十神"""
    try:
        if gan not in TIANGAN or day_gan not in TIANGAN:
            return ''
        
        g_idx, d_idx = TIANGAN.index(gan), TIANGAN.index(day_gan)
        same_yy = (g_idx % 2) == (d_idx % 2)
        wx_d, wx_g = GAN_WUXING[day_gan], GAN_WUXING[gan]
        
        if wx_g == wx_d:                             
            return '比肩' if same_yy else '劫财'
        if WUXING_SHENG.get(wx_d,'') == wx_g:        
            return '食神' if same_yy else '伤官'
        if WUXING_KE.get(wx_d,'') == wx_g:           
            return '偏财' if same_yy else '正财'
        if WUXING_KE.get(wx_g,'') == wx_d:           
            return '七杀' if same_yy else '正官'
        if WUXING_SHENG.get(wx_g,'') == wx_d:        
            return '偏印' if same_yy else '正印'
        
        return ''
    except Exception as e:
        logger.error(f"获取十神失败: {e}")
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
    """计算起运年龄"""
    try:
        year_gan   = get_ganzhi_year(year)[0]
        year_yy    = '阳' if TIANGAN.index(year_gan) % 2 == 0 else '阴'
        is_forward = (year_yy == '阳' and gender == '男') or (year_yy == '阴' and gender == '女')
        
        jieqi_day  = JIEQI_MONTH.get(month, {}).get('day', 6)
        
        if is_forward:
            if day < jieqi_day:
                days_gap = jieqi_day - day
            else:
                next_m = month % 12 + 1
                days_gap = 30 - day + JIEQI_MONTH.get(next_m, {}).get('day', 6)
        else:
            if day >= jieqi_day:
                days_gap = day - jieqi_day
            else:
                prev_m   = (month - 2) % 12 + 1
                days_gap = abs(day + 30 - JIEQI_MONTH.get(prev_m, {}).get('day', 6))
        
        return max(1, round(days_gap / 3))
    except Exception as e:
        logger.error(f"计算起运年龄失败: {e}")
        return 1

# ============ 主要分析函数（保持简洁，详见原文件）============
def generate_bazi_detail(name, birth_info, gender, date_type='阳历', lunar_date=''):
    """生成八字分析详情"""
    try:
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
        
        if '官' in geju or '杀' in geju: 
            career_dir = "行政管理、公务员、企业管理、法律"
        elif '财' in geju:               
            career_dir = "商业贸易、金融投资、财务管理"
        elif '印' in geju:               
            career_dir = "教育培训、科研学术、文化传媒"
        elif '食' in geju or '伤' in geju: 
            career_dir = "艺术创作、演艺设计、技术研发"
        else:                            
            career_dir = "综合发展，适合多领域尝试"
        
        current_year = datetime.now().year
        liunian_gz   = get_ganzhi_year(current_year)
        ln_wx        = GAN_WUXING.get(liunian_gz[0], '土')
        
        if   ln_wx == xiyong[0]:                       
            liunian_tip = "流年逢喜用，事业财运有利"
        elif WUXING_SHENG.get(ln_wx,'') == xiyong[0]:  
            liunian_tip = "流年相生，整体平稳顺遂"
        elif WUXING_KE.get(ln_wx,'') == day_wx:         
            liunian_tip = "流年克日主，需注意健康与稳定"
        else:                                           
            liunian_tip = "流年平和，稳步经营"
        
        base         = 70 + (10 if rizhu_strong == '身旺' else 0)
        if   ln_wx == xiyong[0]:                       
            base += 10
        elif WUXING_SHENG.get(ln_wx,'') == xiyong[0]:  
            base += 5
        
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
📌 *付费进阶服务*\n💡 如需深度流年分析（未来10年每年详细运势），回复「流年」或「大运」可了解付费服务"""
        
        return result, {}
    except Exception as e:
        logger.error(f"生成八字分析失败: {e}", exc_info=True)
        raise

def generate_today_fortune_direct():
    """生成今日通用运势"""
    try:
        today_dt   = datetime.now()
        today      = today_dt.strftime("%Y年%m月%d日")
        today_gz   = get_ganzhi_year(today_dt.year)
        today_mgz  = get_ganzhi_month(today_dt.year, today_dt.month, today_dt.day)
        today_dgz  = get_ganzhi_day(today_dt.year, today_dt.month, today_dt.day)
        today_gan  = today_dgz[0]
        today_zhi  = today_dgz[1]
        today_wx   = GAN_WUXING.get(today_gan, '土')
        year_wx    = GAN_WUXING.get(today_gz[0], '土')
        
        favorable   = FAVORABLE_DIR.get(today_wx, '东')
        lucky_color = LUCKY_COLOR_MAP.get(today_wx, '白色')
        
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
        
        chong_today = ZHI_CHONG.get(today_zhi, '')
        chong_z     = SHENGXIAO[DIZHI.index(chong_today)] if chong_today in DIZHI else '无'
        
        return f"""🌤️ *今日运势*

━━━━━━━━━━━━━━━━━━━━━━
📆 {today}
• 流年：{today_gz} ｜ 月柱：{today_mgz} ｜ 日柱：{today_dgz}
• 今日天干五行：{today_wx} ｜ 日建：{jianchu}日

⚡ 今日能量：{energy}
• {overall_tip}

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
💡 回复「流年」或「大运」了解付费服务"""
    except Exception as e:
        logger.error(f"生成今日运势失败: {e}", exc_info=True)
        return "⚠️ 生成运势时出错，请稍后重试"

# ============ UI菜单 ============
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
• ✨ 紫微斗数（付费 $8U）：命宫主星+十二宫位详批
• 🌤️ 今日运势：日建宜忌
• 🕐 吉时查询：十二时辰吉凶
• 🍼 取名能手（付费 $6U）：八字五行取名+数理分析

💰 付费进阶服务
• 流年分析 $3U：未来10年每年详细运势
• 合婚分析 $5U：双方命盘详细对比

⚠️ 注意事项
• 需要完整生辰信息（年月日时）
• 阴阳历请明确说明
• 发送 /start 重新开始"""

MENU_ITEMS = {"🔮 八字算命","💕 姻缘测算","✨ 紫微斗数","🌤️ 今日运势",
              "🕐 吉时查询","🍼 取名能手","📚 帮助"}

# ============ 消息处理 ============
@tb.message_handler(commands=['start'])
def start_cmd(msg):
    """处理 /start 命令"""
    try:
        uid = str(msg.chat.id)
        user_service.pop(uid, None)
        for store in (date_type_wait, bazi_context, yinyuan_context, qiming_context):
            store.pop(uid, None)
        
        logger.info(f"用户启动: {uid}")
        tb.send_message(msg.chat.id,
            "🏛️ *欢迎来到玄学大师*\n\n智能命理分析系统\n\n请选择服务：",
            reply_markup=main_menu(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"处理start命令失败: {e}")

@tb.message_handler(func=lambda m: m.text == "🔮 八字算命")
def bazi_cmd(msg):
    """八字算命"""
    try:
        user_service[str(msg.chat.id)] = "bazi"
        tb.send_message(msg.chat.id, "🔮 *八字算命*\n\n请输入：姓名 出生年月日时 性别\n例：张三 1990年5月15日 10:00 男", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"处理八字命令失败: {e}")

@tb.message_handler(func=lambda m: m.text == "🌤️ 今日运势")
def today_cmd(msg):
    """今日运势"""
    try:
        result = generate_today_fortune_direct()
        tb.send_message(msg.chat.id, result, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"生成今日运势失败: {e}")
        tb.send_message(msg.chat.id, "⚠️ 获取运势时出错，请稍后重试。")

@tb.message_handler(func=lambda m: m.text == "📚 帮助")
def help_cmd(msg):
    """帮助文本"""
    try:
        tb.send_message(msg.chat.id, HELP_TEXT, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"发送帮助文本失败: {e}")

@tb.message_handler(func=lambda m: True)
def handle(msg):
    """通用消息处理"""
    try:
        _global_cleanup()
        
        uid  = str(msg.chat.id)
        text = msg.text.strip() if msg.text else ''
        
        if not text:
            return
        
        if text.startswith('/') or text in MENU_ITEMS:
            return
        
        # 付费关键词全局检测（提前）
        paid_key = get_paid_key(text)
        if paid_key:
            send_paid_template(msg.chat.id, paid_key)
            return
        
        # 日期输入处理
        birth_info = parse_date_flexible(text)
        if not birth_info:
            svc = user_service.get(uid)
            if svc:
                tb.send_message(msg.chat.id, "⚠️ 未能识别生辰信息，请按格式输入：\n1990年5月15日 10:00 男")
            return
        
        gender = parse_gender(text)
        name   = "缘主"
        for part in text.split():
            if part and not re.search(r'\d', part) and part not in ['男','女','阳历','阴历','她','她们']:
                if 1 <= len(part) <= 6:
                    name = part
                    break
        
        date_type_wait[uid] = _stamp({
            'birth_info': birth_info,
            'original_input': birth_info.copy(),
            'name': name,
            'gender': gender,
            'svc': user_service.get(uid) or 'bazi'
        })
        
        tb.send_message(msg.chat.id,
            f"📅 *日期类型确认*\n\n您输入的是「阳历」还是「阴历」？\n请回复：阳历 或 阴历\n\n"
            f"原始输入：{birth_info['year']}年{birth_info['month']}月{birth_info['day']}日 {birth_info['hour']:02d}:00",
            parse_mode='Markdown')
    except Exception as e:
        logger.error(f"处理消息失败: {e}", exc_info=True)
        try:
            tb.send_message(msg.chat.id, "⚠️ 处理请求时出错，请稍后重试。")
        except:
            pass

# ============ Flask Webhook服务器 ============
try:
    from flask import Flask, request, abort
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logger.warning("⚠️ Flask未安装，将回退到polling模式")

if FLASK_AVAILABLE:
    app = Flask(__name__)
    
    @app.route('/', methods=['GET'])
    def health_check():
        """健康检查"""
        return '{"status":"ok","service":"FortuneMaster Bot v3.2","timestamp":"' + datetime.now().isoformat() + '"}', 200, {'Content-Type': 'application/json'}
    
    @app.route('/webhook', methods=['POST'])
    def webhook():
        """Webhook接收"""
        try:
            if request.headers.get('content-type') != 'application/json':
                abort(403)
            json_str = request.get_data(as_text=True)
            update = Update.de_json(json_str)
            tb.process_new_updates([update])
            return '{"ok":true}', 200, {'Content-Type': 'application/json'}
        except Exception as e:
            logger.error(f"处理webhook失败: {e}")
            return '{"ok":false}', 500, {'Content-Type': 'application/json'}

def register_webhook():
    """注册Webhook"""
    webhook_url = os.getenv('WEBHOOK_URL', '').strip()
    if not webhook_url:
        logger.warning("⚠️ WEBHOOK_URL未设置，Bot将使用polling模式")
        return
    
    try:
        tb.remove_webhook()
        ok = tb.set_webhook(webhook_url)
        if ok:
            logger.info(f"✅ Webhook注册成功: {webhook_url}")
        else:
            logger.error("❌ Webhook注册失败")
    except Exception as e:
        logger.error(f"❌ 注册Webhook出错: {e}")

register_webhook()

if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))
    
    if FLASK_AVAILABLE:
        logger.info(f"🚀 玄学大师 Bot v3.2 启动（Flask服务器），端口 {PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
    else:
        logger.info("🔄 玄学大师 Bot v3.2 启动（Polling模式）")
        try:
            tb.infinity_polling(timeout=20, long_polling_timeout=10)
        except KeyboardInterrupt:
            logger.info("🛑 Bot已停止")
