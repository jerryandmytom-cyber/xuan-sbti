# fortunemaster_new.py
"""
新的主入口文件 v2.0 - 優化版

改進點：
1. 使用異步計算引擎
2. 支持快速模式和完整模式
3. 緩存感知
4. 模板預生成
5. Session持久化
6. 異步推送框架
"""

import asyncio
import datetime
from typing import Optional, Dict, Any

try:
    from session_manager import SessionManager
    from constants import parse_date_flexible
    from metaphysics_engine import (
        MetaphysicsEngine, 
        ReportGenerator, 
        calculate_bazi_cached,
        calculate_bazi_full,
        AsyncPushCallback
    )
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    exit()

# 快速模式閾值（秒）
QUICK_MODE_THRESHOLD = 10


class FortuneMasterNew:
    """
    運命主控器 v2.0 - 支援快速模式和完整模式
    """

    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.quick_mode = True  # 默認開啟快速模式
        
        # 尝试恢复已保存的用户信息
        session = SessionManager.get_session(chat_id)
        self._saved_birth_info = session.get('birth_info', {})
        print(f"Initialized FortuneMaster v2 for Chat ID: {chat_id}")

    def _parse_date_time(self, message: str) -> Dict[str, Any]:
        """
        解析用戶消息中的日期和時間。
        支援格式：
        - 1990年5月3日 下午2點30分
        - 1990-05-03 14:30
        - 陽曆1990/5/3 14:30
        - 1990年5月3日14时
        """
        import re
        
        patterns = [
            r'(\d{4})[年\-\/](\d{1,2})[月\-\/](\d{1,2})',
            r'(\d{4})(\d{2})(\d{2})'
        ]
        
        date_match = None
        for pattern in patterns:
            date_match = re.search(pattern, message)
            if date_match:
                break
        
        if not date_match:
            # 返回已保存的信息或默認值
            if self._saved_birth_info:
                return self._saved_birth_info
            return {
                "birth_date": datetime.date(1990, 5, 3),
                "birth_time": "1430"
            }
        
        year, month, day = map(int, date_match.groups())
        birth_date = datetime.date(year, month, day)
        
        # 解析時間
        time_pattern = r'(?:下午|早上|上午|晚上|凌晨)?(\d{1,2})[點时:](\d{0,2})?'
        time_match = re.search(time_pattern, message)
        
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or '0')
            
            # 處理下午
            if '下午' in message or '晚上' in message:
                if hour < 12:
                    hour += 12
            
            birth_time = f"{hour:02d}{minute:02d}"
        else:
            birth_time = "1200"
        
        return {"birth_date": birth_date, "birth_time": birth_time}

    def _process_user_input(self, user_message: str):
        """路由用戶輸入（支持简繁中文）"""
        msg = user_message.lower()
        # 统一简繁中文关键词
        msg_norm = msg.replace('运', '運').replace('势', '勢')
        
        if '八字' in msg or '排盘' in msg or '排盤' in msg:
            return {"action": "bazi", "details": self._parse_date_time(user_message)}
        elif '合婚' in msg or '配對' in msg or '配对' in msg:
            return {"action": "relationship", "details": self._parse_date_time(user_message)}
        elif '運勢' in msg_norm or '流年' in msg_norm:
            topic = user_message.split('的')[-1].strip() if '的' in user_message else "綜合運勢"
            return {"action": "fortune", "details": topic}
        elif '快速' in msg:
            self.quick_mode = True
            return {"action": "bazi", "details": self._parse_date_time(user_message)}
        elif '詳細' in msg or '详细' in msg:
            self.quick_mode = False
            return {"action": "bazi", "details": self._parse_date_time(user_message)}
        elif '保存' in msg or '記住' in msg or '记住' in msg:
            parsed = self._parse_date_time(user_message)
            return {"action": "save_info", "details": parsed}
        else:
            return {"action": "none", "details": None}

    async def run_analysis_async(self, user_message: str) -> str:
        """異步執行分析流程"""
        session = SessionManager.get_session(self.chat_id)
        
        analysis_task = self._process_user_input(user_message)
        action = analysis_task["action"]
        details = analysis_task["details"]
        
        results = None
        report_content = ""
        
        if action == "save_info":
            # 保存生辰信息供后续使用
            SessionManager.save_session(self.chat_id, {"birth_info": details})
            self._saved_birth_info = details
            return f"✅ 已保存您的生辰信息：{details['birth_date']} {details['birth_time'][:2]}時\n下次查詢時可以直接說『排盤』使用此信息。"
        
        if action == "bazi":
            bazi_input = details
            
            # 保存输入信息
            SessionManager.save_session(self.chat_id, {"birth_info": bazi_input})
            
            if self.quick_mode:
                # 快速模式：使用缓存计算，秒回
                results = calculate_bazi_cached(
                    bazi_input["birth_date"], 
                    bazi_input["birth_time"]
                )
                report_content = ReportGenerator.generate_bazi_report(results, include_details=False)
                cache_note = "（命中緩存）" if results.get('from_cache') else ""
                report_content = report_content.replace("✨ **【個人命盘报告】** ✨", 
                    f"✨ **【個人命盘报告】** ✨ {cache_note}")
                
                # 后台异步计算大运流年（不阻塞响应）
                asyncio.create_task(self._background_compute(bazi_input))
            else:
                # 详细模式：等待完整计算
                results = await calculate_bazi_full(
                    bazi_input["birth_date"],
                    bazi_input["birth_time"]
                )
                report_content = ReportGenerator.generate_bazi_report(results, include_details=True)
        
        elif action == "relationship":
            # 合婚分析：支持双方分别输入
            bazi_input = details
            bazi1 = session.get('last_bazi')
            if not bazi1:
                # 如果没有先排盘，引导用户先排盘
                return "💖 合婚分析需要雙方的八字信息。\n請先輸入一方的出生時間進行排盤，再進行合婚匹配。"
            
            bazi2 = calculate_bazi_cached(
                bazi_input["birth_date"],
                bazi_input["birth_time"]
            )
            results = MetaphysicsEngine.calculate_relationship(bazi1, bazi2)
            report_content = self._generate_relationship_report(results)
        
        elif action == "fortune":
            bazi = session.get('last_bazi')
            if not bazi:
                return "🔮 請先進行八字排盤，我才能分析您的運勢。\n輸入『排盤』開始。"
            topic = analysis_task["details"]
            results = MetaphysicsEngine.analyze_fortune(bazi, topic)
            report_content = self._generate_fortune_report(results)
        
        else:
            report_content = "👋 請告訴我您想查詢什麼命理項目，例如：『排盤』、『合婚』或『運勢分析』。\n\n💡 提示：\n• 默認使用快速模式，如需詳細分析請說『詳細模式』\n• 輸入『記住』保存您的生辰信息，下次直接說『排盤』"
        
        # 保存最新八字结果
        if results:
            SessionManager.save_session(self.chat_id, {"last_bazi": results if action == "bazi" else session.get('last_bazi')})

        return report_content

    async def _background_compute(self, bazi_input: dict):
        """後台異步計算大運流年，完成後存入 session"""
        try:
            full_result = await calculate_bazi_full(
                bazi_input["birth_date"],
                bazi_input["birth_time"]
            )
            SessionManager.save_session(self.chat_id, {"background_bazi": full_result})
            print(f"[Background] Full calculation complete for {self.chat_id}")
        except Exception as e:
            print(f"[Background] Calculation failed: {e}")

    def run_analysis(self, user_message: str) -> str:
        """同步接口（保持向後兼容）"""
        return asyncio.get_event_loop().run_until_complete(
            self.run_analysis_async(user_message)
        )

    def _generate_relationship_report(self, result: dict) -> str:
        return f"""💖 **【姻緣匹配报告】**

⭐ 綜合評分：{result['match_score']}/100

匹配重點：{result['compatibility_elements']}

結論：{result['summary']}"""

    def _generate_fortune_report(self, result: dict) -> str:
        advice_text = "\n".join([f"{i+1}. {a}" for i, a in enumerate(result['advice'])])
        return f"""🔮 **【運勢报告】**

主題：{result['topic']}
趨勢：{result['trend']}

建議：
{advice_text}"""


def main_run(chat_id: str, user_input: str) -> str:
    """同步入口"""
    master = FortuneMasterNew(chat_id=chat_id)
    return master.run_analysis(user_input)


async def main_run_async(chat_id: str, user_input: str) -> str:
    """異步入口"""
    master = FortuneMasterNew(chat_id=chat_id)
    return await master.run_analysis_async(user_input)


if __name__ == "__main__":
    # 測試
    print("\n" + "="*50)
    print("測試 v2.0 引擎")
    print("="*50)
    
    TEST_CHAT = "test_001"
    SessionManager.initialize()
    
    # 測試快速模式
    print("\n>>> 測試：八字排盤")
    result = main_run(TEST_CHAT, "1990年5月3日下午2點30分八字")
    print(result)
    
    # 測試詳細模式
    print("\n>>> 測試：詳細模式")
    master = FortuneMasterNew(TEST_CHAT)
    master.quick_mode = False
    import asyncio
    result_detail = asyncio.get_event_loop().run_until_complete(
        master.run_analysis_async("1990年5月3日下午2點30分")
    )
    print(result_detail)
    
    # 測試記住信息
    print("\n>>> 測試：保存信息")
    result_save = main_run(TEST_CHAT, "記住1995年8月15日早上8點")
    print(result_save)
    
    # 測試使用保存的信息
    print("\n>>> 測試：使用保存的信息排盤")
    result_use = main_run(TEST_CHAT, "排盤")
    print(result_use)
    
    # 清理
    SessionManager.clear_session(TEST_CHAT)
