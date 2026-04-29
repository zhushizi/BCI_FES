"""
SQLite 连接与数据访问封装。

- `DatabaseConnection` 仅负责连接生命周期管理。
- `DatabaseService` 在此基础上封装常用的 CRUD/事务操作，供上层仓储或服务使用。
"""

import sqlite3
import os
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple, Iterable


class DatabaseConnection:
    """SQLite 数据库连接类"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，如果为 None 则使用默认路径 db/HW_BCI.db
        """
        if db_path is None:
            # 获取项目根目录（假设 infrastructure/data 在项目根目录下）
            current_dir = Path(__file__).parent.parent.parent
            db_path = current_dir / "db" / "HW_BCI.db"
        
        self.db_path = str(db_path)
        self.connection: Optional[sqlite3.Connection] = None
        self.logger = logging.getLogger(__name__)
        
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def connect(self) -> bool:
        """
        连接数据库
        
        Returns:
            bool: 连接是否成功
        """
        try:
            self.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # 允许多线程访问
                timeout=10.0  # 连接超时时间
            )
            # 设置行工厂，返回字典格式的结果
            self.connection.row_factory = sqlite3.Row
            # 启用外键约束
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.logger.info(f"数据库连接成功: {self.db_path}")
            return True
        except sqlite3.Error as e:
            self.logger.error(f"数据库连接失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开数据库连接"""
        if self.connection:
            try:
                self.connection.close()
                self.logger.info("数据库连接已关闭")
            except sqlite3.Error as e:
                self.logger.error(f"关闭数据库连接时发生错误: {e}")
            finally:
                self.connection = None
    
    def is_connected(self) -> bool:
        """
        检查数据库是否已连接
        
        Returns:
            bool: 连接状态
        """
        return self.connection is not None
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()


class DatabaseService:
    """
    数据库服务类
    - 负责执行查询、更新等操作
    - 将连接管理委托给基础设施层的 DatabaseConnection
    """

    def __init__(self, db_connection: Optional[DatabaseConnection] = None):
        self.db_conn = db_connection or DatabaseConnection()
        if not self.db_conn.is_connected():
            self.db_conn.connect()
        self.logger = logging.getLogger(__name__)

    # --- 基础能力 ---
    def _ensure_connected(self) -> None:
        """确保数据库已连接"""
        if not self.db_conn.is_connected():
            if not self.db_conn.connect():
                raise RuntimeError("数据库连接失败")

    # --- 查询与更新 ---
    def execute_query(self, sql: str, parameters: Tuple = None) -> List[Dict[str, Any]]:
        """执行查询语句（SELECT）"""
        self._ensure_connected()
        cursor = self.db_conn.connection.execute(sql, parameters or ())
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def execute_update(self, sql: str, parameters: Tuple = None) -> int:
        """执行更新语句（INSERT/UPDATE/DELETE）"""
        self._ensure_connected()
        try:
            cursor = self.db_conn.connection.execute(sql, parameters or ())
            self.db_conn.connection.commit()
            return cursor.rowcount
        except Exception:
            self.db_conn.connection.rollback()
            raise

    def execute_many(self, sql: str, parameters_list: Iterable[Tuple]) -> int:
        """批量执行更新语句"""
        self._ensure_connected()
        try:
            cursor = self.db_conn.connection.executemany(sql, parameters_list)
            self.db_conn.connection.commit()
            return cursor.rowcount
        except Exception:
            self.db_conn.connection.rollback()
            raise

    def execute_script(self, sql_script: str) -> None:
        """执行多条 SQL 脚本"""
        self._ensure_connected()
        try:
            self.db_conn.connection.executescript(sql_script)
            self.db_conn.connection.commit()
        except Exception:
            self.db_conn.connection.rollback()
            raise

    # --- 辅助方法 ---
    def get_last_insert_id(self) -> int:
        """获取最后插入行 ID"""
        self._ensure_connected()
        cursor = self.db_conn.connection.execute("SELECT last_insert_rowid()")
        return cursor.fetchone()[0]

    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        sql = """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """
        return len(self.execute_query(sql, (table_name,))) > 0

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """获取表结构信息"""
        sql = f"PRAGMA table_info({table_name})"
        return self.execute_query(sql)

    # --- 事务管理 ---
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        self._ensure_connected()
        try:
            yield self
            self.db_conn.connection.commit()
        except Exception:
            self.db_conn.connection.rollback()
            raise

    # --- 连接管理暴露（可选） ---
    def connect(self) -> bool:
        """显式连接"""
        return self.db_conn.connect()

    def disconnect(self) -> None:
        """显式断开"""
        self.db_conn.disconnect()

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.db_conn.is_connected()

