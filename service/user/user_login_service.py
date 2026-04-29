"""
用户登录服务类 - 负责用户登录相关的业务逻辑
遵循单一职责原则，专注于：
- 用户登录验证
- 用户注册（作为登录流程的一部分）
- 用户登出
- 登录凭据的保存和读取（记住密码功能）
"""

import json
import os
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import logging

from infrastructure.data import DatabaseService


class _CredentialStore:
    def __init__(self, base_path: Path, logger: logging.Logger):
        self._path = base_path
        self._logger = logger

    def get_username(self) -> Optional[str]:
        if not self._path.exists():
            return None
        try:
            config = self._read()
            return config.get('username')
        except Exception as e:
            self._logger.warning(f"读取保存的用户名失败: {e}")
            return None

    def get_password(self) -> Optional[str]:
        if not self._path.exists():
            return None
        try:
            config = self._read()
            if config.get('remember_password', False):
                return config.get('password')
        except Exception as e:
            self._logger.warning(f"读取保存的密码失败: {e}")
        return None

    def has_credentials(self) -> bool:
        if not self._path.exists():
            return False
        try:
            config = self._read()
            return config.get('remember_password', False)
        except Exception:
            return False

    def save(self, username: str, password: str, remember: bool) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        config = {
            'username': username,
            'remember_password': remember
        }
        if remember:
            config['password'] = password
        try:
            self._write(config)
            self._logger.debug(f"保存用户凭据: {username}, remember={remember}")
        except Exception as e:
            self._logger.error(f"保存用户凭据失败: {e}")

    def _read(self) -> Dict[str, Any]:
        with self._path.open('r', encoding='utf-8') as f:
            return json.load(f)

    def _write(self, config: Dict[str, Any]) -> None:
        with self._path.open('w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


class _UserRepository:
    def __init__(self, db: DatabaseService, table: str, logger: logging.Logger):
        self._db = db
        self._table = table
        self._logger = logger

    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        sql = f"SELECT * FROM {self._table} WHERE UserName = ?"
        users = self._db.execute_query(sql, (username,))
        return users[0] if users else None

    def exists_username(self, username: str) -> bool:
        sql = f"SELECT UserId FROM {self._table} WHERE UserName = ?"
        existing = self._db.execute_query(sql, (username,))
        return bool(existing)

    def insert_user(self, username: str, password: str, phone_number: str, user_type: int) -> None:
        sql = f"""
            INSERT INTO {self._table} (UserName, Password, PhoneNumber, UserType)
            VALUES (?, ?, ?, ?)
        """
        self._db.execute_update(sql, (username, password, phone_number, user_type))

    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            sql = f"SELECT UserId, UserName, PhoneNumber, UserType FROM {self._table} WHERE UserId = ?"
            users = self._db.execute_query(sql, (user_id,))
            return dict(users[0]) if users else None
        except Exception as e:
            self._logger.error(f"获取用户信息失败: {e}")
            return None


class UserLoginService:
    """用户登录服务类 - 处理用户登录相关的业务逻辑"""
    
    TABLE_USER = "User"
    CONFIG_DIR = ".bci_hw"
    CONFIG_FILENAME = "user_config.json"

    def __init__(self, db_service: DatabaseService):
        """
        初始化用户登录服务
        
        Args:
            db_service: 数据库服务对象，如果为 None 则自动创建
        """
        
        self.db = db_service
        self.logger = logging.getLogger(__name__)
        self._current_user: Optional[Dict[str, Any]] = None
        self._is_authenticated = False
        self._user_fields = ("UserId", "UserName", "PhoneNumber", "UserType", "Password")
        self._config_path = self._build_config_path()
        self._credential_store = _CredentialStore(self._config_path, self.logger)
        self._user_repo = _UserRepository(self.db, self.TABLE_USER, self.logger)
    
    @property
    def is_authenticated(self) -> bool:
        """是否已认证"""
        return self._is_authenticated
    
    @property
    def current_user(self) -> Optional[Dict[str, Any]]:
        """当前登录用户"""
        return self._current_user
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户登录验证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            Dict[str, Any]: 验证结果
                - success: bool - 是否成功
                - message: str - 消息
                - user: dict - 用户信息（成功时）
        """
        try:
            # 查询用户（使用数据库中的表名和字段名）
            user = self._user_repo.find_by_username(username)
            if not user:
                return {
                    'success': False,
                    'message': '用户名不存在'
                }
            
            # 验证密码（数据库中是明文存储，直接比较）
            if user['Password'] != password:
                return {
                    'success': False,
                    'message': '密码错误'
                }
            
            # 登录成功
            self._current_user = {
                'UserId': user['UserId'],
                'UserName': user['UserName'],
                'PhoneNumber': user.get('PhoneNumber'),
                'UserType': user.get('UserType')
            }
            self._is_authenticated = True
            
            self.logger.info(f"用户登录成功: {username}")
            
            return {
                'success': True,
                'message': '登录成功',
                'user': self._current_user
            }
            
        except Exception as e:
            self.logger.error(f"登录验证失败: {e}")
            return {
                'success': False,
                'message': f'登录失败: {str(e)}'
            }
    
    def register(self, username: str, password: str, phone_number: str = None, user_type: int = 1) -> Dict[str, Any]:
        """
        用户注册（作为登录流程的一部分）
        
        Args:
            username: 用户名
            password: 密码（明文存储）
            phone_number: 电话号码（可选）
            user_type: 用户类型（可选，默认1）
            
        Returns:
            Dict[str, Any]: 注册结果
        """
        try:
            # 检查用户名是否已存在
            if self._user_repo.exists_username(username):
                return {
                    'success': False,
                    'message': '用户名已存在'
                }
            
            # 创建新用户（密码明文存储）
            self._user_repo.insert_user(username, password, phone_number or '', user_type)
            
            self.logger.info(f"用户注册成功: {username}")
            
            return {
                'success': True,
                'message': '注册成功'
            }
            
        except Exception as e:
            self.logger.error(f"用户注册失败: {e}")
            return {
                'success': False,
                'message': f'注册失败: {str(e)}'
            }
    
    def logout(self) -> None:
        """用户登出"""
        self._current_user = None
        self._is_authenticated = False
        self.logger.info("用户已登出")
    
    def get_saved_username(self) -> Optional[str]:
        """
        获取已保存的用户名
        
        Returns:
            Optional[str]: 保存的用户名，不存在返回 None
        """
        return self._credential_store.get_username()
    
    def get_saved_password(self) -> Optional[str]:
        """
        获取已保存的密码
        
        Returns:
            Optional[str]: 保存的密码，不存在返回 None
        """
        return self._credential_store.get_password()
    
    def has_saved_credentials(self) -> bool:
        """
        检查是否有保存的凭据
        
        Returns:
            bool: 是否有保存的凭据
        """
        return self._credential_store.has_credentials()
    
    def save_credentials(self, username: str, password: str, remember: bool) -> None:
        """
        保存用户凭据（记住密码功能）
        
        Args:
            username: 用户名
            password: 密码
            remember: 是否记住密码
        """
        self._credential_store.save(username, password, remember)

    def _build_config_path(self) -> Path:
        home_dir = Path.home()
        config_dir = home_dir / self.CONFIG_DIR
        return config_dir / self.CONFIG_FILENAME
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取用户信息
        
        注意：此方法主要用于登录后获取当前用户信息。
        未来用户管理相关的功能（如查询、修改用户信息等）应移至用户管理服务类。
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[Dict[str, Any]]: 用户信息，不存在返回 None
        """
        return self._user_repo.get_user_info(user_id)

