"""
用户应用层 - 连接 UI 层和 Service 层
负责协调用户相关的业务逻辑
"""

from typing import Optional
from service.user import UserLoginService
import logging


class UserApp:
    """用户应用层 - 连接前后端的中间层"""
    
    def __init__(self, user_service: UserLoginService):
        """
        初始化用户应用层
        
        Args:
            user_service: 注入的用户登录服务实例
        """
        if user_service is None:
            raise ValueError("user_service 参数不能为空")
        self.user_service = user_service
        self.logger = logging.getLogger(__name__)
    
    def login(self, username: str, password: str) -> dict:
        """
        用户登录（应用层接口）
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            dict: 登录结果
        """
        return self.user_service.login(username, password)
    
    def register(self, username: str, password: str, phone_number: str = None, user_type: int = 1) -> dict:
        """
        用户注册（应用层接口）
        
        Args:
            username: 用户名
            password: 密码
            phone_number: 电话号码（可选）
            user_type: 用户类型（可选，默认1）
            
        Returns:
            dict: 注册结果
        """
        return self.user_service.register(username, password, phone_number, user_type)
    
    def logout(self) -> None:
        """用户登出"""
        self.user_service.logout()
    
    @property
    def is_authenticated(self) -> bool:
        """是否已认证"""
        return self.user_service.is_authenticated
    
    @property
    def current_user(self) -> Optional[dict]:
        """当前登录用户"""
        return self.user_service.current_user
    
    def get_saved_username(self) -> Optional[str]:
        """获取已保存的用户名"""
        return self.user_service.get_saved_username()
    
    def get_saved_password(self) -> Optional[str]:
        """获取已保存的密码"""
        return self.user_service.get_saved_password()
    
    def has_saved_credentials(self) -> bool:
        """检查是否有保存的凭据"""
        return self.user_service.has_saved_credentials()
    
    def save_credentials(self, username: str, password: str, remember: bool) -> None:
        """保存用户凭据"""
        self.user_service.save_credentials(username, password, remember)
    
    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        """根据ID获取用户信息"""
        return self.user_service.get_user_by_id(user_id)

