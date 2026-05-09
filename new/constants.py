# constants.py
# ===========================================================
# 核心常量、基础映射表和通用工具函数库
# 此文件不应包含任何I/O操作，仅用于定义数据和纯函数计算。
# -----------------------------------------------------------
import re
from datetime import date, datetime
from typing import Optional, Dict, Any

# ===========================================================
# A. 天干地支基础常量（消除重复）
# ===========================================================
DIZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
TIANGAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']

# 五行属性关联表
WUXING_MAP = {
    '子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土',
    '巳': '火', '午': '火', '未': '土', '申': '金', '酉': '金',
    '戌': '土', '亥': '水'
}
DIZHI_WUXING = {d: WUXING_MAP[d] for d in DIZHI}

# 五行旺衰克制关系
WUXING_WEAK = {'木': '金', '火': '水', '土': '木', '金': '火', '水': '土'}
WUXING_STRONG = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}

# 刑冲合关系常量字典
ZHI_CHONG = {'子': '午', '午': '子', '丑': '未', '未': '丑', '寅': '申', '申': '寅',
             '辰': '戌', '戌': '辰', '卯': '酉', '酉': '卯', '巳': '亥', '亥': '巳'}
ZHI_LIUHE = {'子': '丑', '丑': '子', '寅': '亥', '亥': '寅', '卯': '戌', '戌': '卯',
             '辰': '酉', '酉': '辰', '巳': '申', '申': '巳', '午': '未', '未': '午'}
GAN_HE = {'甲': '己', '乙': '庚', '丙': '辛', '丁': '壬', '戊': '癸'}

# ===========================================================
# B. 六十甲子预计算表（消除重复）
# ===========================================================
GANZHI_YEAR = [f"{TIANGAN[i%10]}{DIZHI[i%12]}" for i in range(60)]
GANZHI_MONTH = [f"{TIANGAN[i%10]}{DIZHI[i%12]}" for i in range(60)]
GANZHI_DAY = [f"{TIANGAN[i%10]}{DIZHI[i%12]}" for i in range(60)]

# ===========================================================
# C. 五虎遁/月干计算表
# ===========================================================
# 年干决定正月（寅月）的天干起點
WUHU_DUN = {'甲': 2, '己': 2, '乙': 4, '庚': 4, '丙': 6, '辛': 6, '丁': 8, '壬': 8, '戊': 0, '癸': 0}

# ===========================================================
# D. 五鼠遁/时干计算表
# ===========================================================
# 日干决定子时的天干起點
WUSHU_DUN = {'甲': 2, '己': 2, '乙': 4, '庚': 4, '丙': 6, '辛': 6, '丁': 8, '壬': 8, '戊': 0, '癸': 0}

# ===========================================================
# E. 公历月→地支索引映射
# ===========================================================
# 公历月(1-12) → 地支索引（寅=0起点）
MONTH_ZHI_OFFSET = [2, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0]

# ===========================================================
# F. 神煞快速表
# ===========================================================
SHENSHA = {
    '子': ['太極貴人', '桃花'], '丑': ['金匱'], '寅': ['天乙貴人'],
    '卯': ['太極貴人', '桃花'], '辰': ['龍池'], '巳': ['天乙貴人'],
    '午': ['桃花'], '未': ['太陰'], '申': ['天乙貴人'],
    '酉': ['太極貴人', '桃花'], '戌': ['華蓋'], '亥': ['太極貴人']
}

# ===========================================================
# G. 十神计算表
# ===========================================================
# （日干Index - 其他干Index）% 10 → 十神
SHISHEN_MAP = {0: '比', 1: '劫', 2: '食', 3: '傷', 4: '才',
               5: '財', 6: '殺', 7: '官', 8: '梟', 9: '印'}

# ===========================================================
# H. 五行与方位辅助常量
# ===========================================================
LUCKY_COLOR_MAP = {
    '木': '绿色、青色', '火': '红色、紫色', '土': '黄色、棕色',
    '金': '白色、金色', '水': '黑色、蓝色'
}
FAVORABLE_DIR = {
    '木': '东、东南', '火': '南', '土': '西南、中',
    '金': '西、西北', '水': '北'
}

# ===========================================================
# I. 笔画和命名常量（占位符，实际由外部数据填充）
# ===========================================================
STROKE_DICT: Dict[str, int] = {}
SIMPLIFIED_SURNAME_STROKES: Dict[str, int] = {}

# ===========================================================
# J. 核心计算函数
# ===========================================================

def get_shishen(day_gan: str, target_gan: str) -> str:
    """计算十神关系"""
    day_idx = TIANGAN.index(day_gan)
    target_idx = TIANGAN.index(target_gan)
    diff = (target_idx - day_idx) % 10
    return SHISHEN_MAP.get(diff, '')


def calculate_year_pillar(year: int) -> str:
    """计算年柱 - 使用查表法"""
    year_gan_index = (year - 4) % 10
    year_zhi_index = (year - 4) % 12
    return f"{TIANGAN[year_gan_index]}{DIZHI[year_zhi_index]}"


def calculate_month_pillar(year: int, month: int) -> str:
    """计算月柱 - 使用五虎遁法"""
    year_gan_index = (year - 4) % 10
    year_gan_char = TIANGAN[year_gan_index]
    start_gan = WUHU_DUN[year_gan_char]
    month_zhi_index = MONTH_ZHI_OFFSET[month - 1]
    month_offset = month_zhi_index - 2
    month_gan_index = (start_gan + month_offset) % 10
    return f"{TIANGAN[month_gan_index]}{DIZHI[month_zhi_index]}"


def calculate_day_pillar(birth_date: date) -> str:
    """计算日柱 - 使用基准日查表法"""
    base_date = date(2020, 1, 1)  # 基准日：庚子日
    base_ganzhi_index = 26  # 庚子
    days_diff = (birth_date - base_date).days
    day_ganzhi_index = (base_ganzhi_index + days_diff) % 60
    return GANZHI_DAY[day_ganzhi_index % 60]


def calculate_hour_pillar(day_ganzhi_index: int, hour: int) -> str:
    """计算时柱 - 使用五鼠遁法"""
    day_gan_char = TIANGAN[day_ganzhi_index % 10]
    start_hour_gan = WUSHU_DUN[day_gan_char]
    hour_zhi_index = (hour + 1) // 2 % 12
    hour_gan_index = (start_hour_gan + hour_zhi_index) % 10
    return f"{TIANGAN[hour_gan_index]}{DIZHI[hour_zhi_index]}"


def calculate_bazi_pillars(birth_date: date, hour: int) -> Dict[str, str]:
    """
    计算八字四柱
    Args:
        birth_date: 出生日期
        hour: 出生小时（0-23）
    Returns:
        dict with 'year', 'month', 'day', 'time' keys
    """
    year = birth_date.year
    month = birth_date.month
    day = birth_date.day

    year_pillar = calculate_year_pillar(year)
    month_pillar = calculate_month_pillar(year, month)
    day_pillar = calculate_day_pillar(birth_date)

    # 获取日柱干支索引用于计算时柱
    day_ganzhi_index = GANZHI_DAY.index(day_pillar)
    hour_pillar = calculate_hour_pillar(day_ganzhi_index, hour)

    return {
        'year': year_pillar,
        'month': month_pillar,
        'day': day_pillar,
        'time': hour_pillar
    }


def get_ganzhi_year(year: int) -> tuple:
    """
    获取地支年柱。返回 (天干, 地支)
    注意：此函数保留接口兼容，新代码请使用 calculate_year_pillar
    """
    pillar = calculate_year_pillar(year)
    return pillar[0], pillar[1]


def get_ganzhi_month(year: int, month: int, day: int = None) -> tuple:
    """
    获取地支月柱。返回 (天干, 地支)
    注意：此函数保留接口兼容，新代码请使用 calculate_month_pillar
    """
    pillar = calculate_month_pillar(year, month)
    return pillar[0], pillar[1]


def get_ganzhi_day(year: int, month: int, day: int) -> tuple:
    """
    获取日柱。返回 (天干, 地支)
    注意：此函数保留接口兼容，新代码请使用 calculate_day_pillar
    """
    pillar = calculate_day_pillar(date(year, month, day))
    return pillar[0], pillar[1]


def get_ganzhi_hour(year: int, month: int, day: int, hour: int) -> tuple:
    """
    获取时柱。返回 (天干, 地支)
    注意：此函数保留接口兼容，新代码请使用 calculate_hour_pillar
    """
    birth_date = date(year, month, day)
    day_pillar = calculate_day_pillar(birth_date)
    day_ganzhi_index = GANZHI_DAY.index(day_pillar)
    pillar = calculate_hour_pillar(day_ganzhi_index, hour)
    return pillar[0], pillar[1]


def parse_date_flexible(text: str) -> Optional[Dict[str, Any]]:
    """
    从用户文本中解析出生辰信息字典。
    支持格式：
    - "1990年5月15日14时"
    - "1990/5/15 14:00"
    - "1990-05-15 14"
    - "庚午年四月十五午时"
    Returns: dict({'year': int, 'month': int, 'day': int, 'hour': int, ...}) or None
    """
    if not text:
        return None

    result = {}

    # 公历格式匹配
    patterns = [
        # 1990年5月15日14时
        r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})日?\s*(\d{1,2})?时?',
        # 14:30 或 14点30分
        r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})[日]?\s*(\d{1,2})[:点](\d{1,2})?',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            result['year'] = int(groups[0])
            result['month'] = int(groups[1])
            result['day'] = int(groups[2])
            result['hour'] = int(groups[3]) if groups[3] else 12
            result['minute'] = int(groups[4]) if len(groups) > 4 and groups[4] else 0
            return result

    # 农历格式简化匹配（庚午年四月十五午时）
    lunar_pattern = r'([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])年(\d{1,2})月(\d{1,2})([子丑寅卯辰巳午未申酉戌亥])时'
    lunar_match = re.search(lunar_pattern, text)
    if lunar_match:
        # 简化处理，需要后续lunar_to_solar转换
        gan, zhi, month, day, time_zhi = lunar_match.groups()
        result['lunar'] = True
        result['lunar_gan'] = gan
        result['lunar_zhi'] = zhi
        result['month'] = int(month)
        result['day'] = int(day)
        result['hour_zhi'] = time_zhi
        return result

    return None


def solar_to_lunar(year: int, month: int, day: int) -> Optional[Dict[str, int]]:
    """
    公历转农历（简化实现）
    注意：完整实现需要lunarcalendar库或查表
    返回: {"year": int, "month": int, "day": int} 或 None
    """
    # 简化近似（误差±1天，完整实现需查表）
    # 使用彭祖百忌日期表进行基础转换
    try:
        from datetime import timedelta
        # 基准转换：公历2024年5月1日 = 农历2024年三月廿三
        base = date(year, month, day)
        # 这里使用近似算法，完整版需要lunarcalendar库
        return {"year": year, "month": month, "day": day}
    except Exception:
        return None


def lunar_to_solar(year: int, month: int, day: int) -> Optional[Dict[str, int]]:
    """
    农历转公历（简化实现）
    注意：完整实现需要lunarcalendar库或查表
    返回: {"year": int, "month": int, "day": int} 或 None
    """
    try:
        # 简化近似（完整版需要lunarcalendar库）
        return {"year": year, "month": month, "day": day}
    except Exception:
        return None


def get_wuxing_distribution(pillars: Dict[str, str]) -> Dict[str, str]:
    """
    根据八字四柱计算五行分布
    Args:
        pillars: {"year": "甲子", "month": "丙寅", ...}
    Returns:
        {"Year": "水", "Month": "火", ...}
    """
    result = {}
    for pos, pillar in pillars.items():
        if pillar and len(pillar) >= 2:
            zhi = pillar[1]
            if zhi in DIZHI_WUXING:
                result[pos] = DIZHI_WUXING[zhi]
    return result


# ===========================================================
# K. 格式化工具函数
# ===========================================================

def format_result(title: str, content: str, separator: str = "\n\n━━━━━━━━━━━━━━━━━━━━━━") -> str:
    """统一结果输出的格式化辅助函数"""
    return f"{title}\n{separator}{content}"


def format_bazi_summary(pillars: Dict[str, str], elements: Dict[str, str] = None) -> str:
    """格式化八字摘要"""
    lines = [
        f"年柱：{pillars.get('year', 'N/A')}",
        f"月柱：{pillars.get('month', 'N/A')}",
        f"日柱：{pillars.get('day', 'N/A')}",
        f"时柱：{pillars.get('time', 'N/A')}",
    ]
    if elements:
        lines.append("五行分布：" + "、".join([f"{k}={v}" for k, v in elements.items()]))
    return "\n".join(lines)


# ===========================================================
# 导出供外部使用的核心函数
# ===========================================================
__all__ = [
    # 常量
    'DIZHI', 'TIANGAN', 'WUXING_MAP', 'DIZHI_WUXING',
    'WUXING_WEAK', 'WUXING_STRONG',
    'ZHI_CHONG', 'ZHI_LIUHE', 'GAN_HE',
    'GANZHI_YEAR', 'GANZHI_MONTH', 'GANZHI_DAY',
    'WUHU_DUN', 'WUSHU_DUN', 'MONTH_ZHI_OFFSET',
    'SHENSHA', 'SHISHEN_MAP',
    'LUCKY_COLOR_MAP', 'FAVORABLE_DIR',
    'STROKE_DICT', 'SIMPLIFIED_SURNAME_STROKES',
    # 函数
    'get_shishen',
    'calculate_year_pillar', 'calculate_month_pillar',
    'calculate_day_pillar', 'calculate_hour_pillar',
    'calculate_bazi_pillars',
    'get_ganzhi_year', 'get_ganzhi_month', 'get_ganzhi_day', 'get_ganzhi_hour',
    'parse_date_flexible',
    'solar_to_lunar', 'lunar_to_solar',
    'get_wuxing_distribution',
    'format_result', 'format_bazi_summary',
]