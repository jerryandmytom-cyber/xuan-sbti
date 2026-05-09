import json
import os
from datetime import date, datetime
from typing import Any, Dict, Optional

SESSION_DIR = os.path.dirname(os.path.abspath(__file__))

class SessionManager:
    """
    管理不同用戶或聊天 ID 的會話（Session）狀態的中央管理器。
    它為每個獨立使用者提供了一個原子化的、隔離的上下文空間，
    避免了全局狀態帶來的數據污染和並發風險。
    """
    _sessions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def initialize(cls):
        """初始化 SessionManager 結構（如果需要持久化到文件）。"""
        print("SessionManager initialized. Context will be managed in memory for the current process.")

    @classmethod
    def _get_session_key(cls, user_id: str) -> str:
        """生成用於 session 的唯一鍵。"""
        return f"user_{user_id}"

    @classmethod
    def get_session(cls, user_id: str) -> Dict[str, Any]:
        """
        獲取或創建一個用戶的會話上下文。如果不存在，則返回一個預設空上下文。

        Args:
            user_id: 用戶唯一標識符（例如 chat_id）。

        Returns:
            該用戶的活動上下文字典。
        """
        session_key = cls._get_session_key(user_id)
        if session_key not in cls._sessions:
            cls._sessions[session_key] = {
                "chat_id": user_id,
                "history": [],
                "metadata": {},
                "calculated_results": {}
            }
            print(f"[SessionManager] Created new, isolated session for {user_id}.")
        
        return cls._sessions[session_key]

    @classmethod
    def _get_session_file(cls, user_id: str) -> str:
        """获取session文件路径"""
        session_key = cls._get_session_key(user_id)
        return os.path.join(SESSION_DIR, f"session_{session_key}.json")

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        """JSON序列化时转换不可直接序列化的类型"""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: cls._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [cls._serialize_value(v) for v in value]
        return value

    @classmethod
    def _deserialize_value(cls, value: Any) -> Any:
        """反序列化时还原日期等类型"""
        if isinstance(value, str):
            if len(value) == 10 and value[4] == '-' and value[7] == '-':
                try:
                    return date.fromisoformat(value)
                except:
                    pass
        elif isinstance(value, dict):
            return {k: cls._deserialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [cls._deserialize_value(v) for v in value]
        return value

    @classmethod
    def save_session(cls, user_id: str, updates: Dict[str, Any]) -> bool:
        """更新并保存用户会话上下文（内存+文件持久化）"""
        session = cls.get_session(user_id)
        for key, value in updates.items():
            if key not in session:
                session[key] = value
            else:
                session[key].update(value) if isinstance(session[key], dict) else setattr(session, key, value)

        try:
            session_file = cls._get_session_file(user_id)
            serializable_session = cls._serialize_value(session)
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_session, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SessionManager] Warning: Failed to persist session: {e}")

        return True

    @classmethod
    def load_session(cls, user_id: str) -> bool:
        """从文件加载session（进程重启后恢复）"""
        try:
            session_file = cls._get_session_file(user_id)
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                session_key = cls._get_session_key(user_id)
                cls._sessions[session_key] = cls._deserialize_value(data)
                return True
        except Exception as e:
            print(f"[SessionManager] Warning: Failed to load session: {e}")
        return False

    @classmethod
    def clear_session(cls, user_id: str) -> bool:
        """清除特定用户的上下文（内存+文件）"""
        session_key = cls._get_session_key(user_id)
        if session_key in cls._sessions:
            del cls._sessions[session_key]
        try:
            session_file = cls._get_session_file(user_id)
            if os.path.exists(session_file):
                os.remove(session_file)
        except:
            pass
        return True
