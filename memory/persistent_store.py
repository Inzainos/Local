import sqlite3
import json
import os
import time
from typing import List, Dict, Any, Optional

class PersistentMemoryStore:
    def __init__(self, db_path: str = "data/shared_memory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Tabla de sesiones
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL,
                    title TEXT
                )
            """)
            # Tabla de mensajes conversacionales
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp REAL,
                    role TEXT,
                    content TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            # Tabla de instantáneas de Blackboard (Pizarra Compartida)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blackboard_snapshots (
                    task_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    user_prompt TEXT,
                    consensus_score INTEGER,
                    consensus_reached INTEGER,
                    snapshot_json TEXT,
                    created_at REAL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            # Tabla de hechos y conocimiento persistente
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    key TEXT,
                    value TEXT,
                    source_agent TEXT,
                    created_at REAL
                )
            """)
            conn.commit()

    def save_session(self, session_id: str, title: str = ""):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, created_at, title) VALUES (?, ?, ?)",
                (session_id, time.time(), title)
            )
            conn.commit()

    def save_message(self, session_id: str, role: str, content: str):
        self.save_session(session_id)
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, timestamp, role, content) VALUES (?, ?, ?, ?)",
                (session_id, time.time(), role, content)
            )
            conn.commit()

    def get_recent_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            messages = [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in rows]
            messages.reverse()
            return messages

    def save_blackboard(self, blackboard_dict: Dict[str, Any]):
        task_id = blackboard_dict.get("task_id", "")
        session_id = blackboard_dict.get("session_id", "default")
        user_prompt = blackboard_dict.get("user_prompt", "")
        consensus_score = blackboard_dict.get("consensus_score", 0)
        consensus_reached = 1 if blackboard_dict.get("consensus_reached", False) else 0
        snapshot_json = json.dumps(blackboard_dict, ensure_ascii=False)

        self.save_session(session_id)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO blackboard_snapshots 
                (task_id, session_id, user_prompt, consensus_score, consensus_reached, snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, session_id, user_prompt, consensus_score, consensus_reached, snapshot_json, time.time())
            )
            conn.commit()

    def get_blackboard(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT snapshot_json FROM blackboard_snapshots WHERE task_id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row["snapshot_json"])
            return None

    def get_recent_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT task_id, session_id, user_prompt, consensus_score, consensus_reached, created_at FROM blackboard_snapshots ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def save_fact(self, category: str, key: str, value: str, source_agent: str):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO knowledge_facts (category, key, value, source_agent, created_at) VALUES (?, ?, ?, ?, ?)",
                (category, key, value, source_agent, time.time())
            )
            conn.commit()

    def search_facts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT category, key, value, source_agent FROM knowledge_facts WHERE key LIKE ? OR value LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            )
            return [dict(r) for r in cursor.fetchall()]
