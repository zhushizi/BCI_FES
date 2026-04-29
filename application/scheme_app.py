"""
方案应用层 - 连接 UI 与 Service 层
"""

import logging
from typing import List, Dict

from service.user import SchemeService


class SchemeApp:
    """方案应用层"""

    def __init__(self, scheme_service: SchemeService):
        """
        初始化方案应用层
        """
        if scheme_service is None:
            raise ValueError("scheme_service 参数不能为空")
        self.scheme_service = scheme_service
        self.logger = logging.getLogger(__name__)

    def get_schemes(self) -> List[Dict[str, str]]:
        """
        获取方案列表

        Returns:
            List[Dict[str, str]]: SchemeManager 表的全部方案
        """
        return self.scheme_service.get_schemes()

    def add_scheme(self, scheme: Dict[str, str]) -> bool:
        """新增方案"""
        return self.scheme_service.add_scheme(scheme)

    def delete_scheme(self, scheme_id: int) -> bool:
        """删除指定方案"""
        return self.scheme_service.delete_scheme(scheme_id)

