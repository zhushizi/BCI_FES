"""
UI资源加载模块
统一管理所有UI资源文件的加载，供所有页面使用

使用方法：
    from ui.core.resource_loader import ensure_resources_loaded
    ensure_resources_loaded()  # 在需要使用资源前调用
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Union
import importlib.util

logger = logging.getLogger(__name__)


class ResourceLoadError(Exception):
    """资源加载相关异常"""
    pass


class ResourceLoader:
    """UI资源加载器 - 负责Qt资源文件的加载和管理"""

    def __init__(self, resource_path: Optional[Union[str, Path]] = None):
        """
        初始化资源加载器

        Args:
            resource_path: 资源文件路径，默认自动查找
        """
        self._resource_path = resource_path
        self._is_loaded = False
        self._resource_module: Optional[object] = None
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def is_loaded(self) -> bool:
        """检查资源是否已加载"""
        return self._is_loaded

    def ensure_loaded(self) -> bool:
        """
        确保资源已加载（幂等操作）

        Returns:
            bool: 加载是否成功
        """
        if self._is_loaded:
            return True

        try:
            self._validate_environment()
            resource_file = self._get_resource_file_path()
            self._validate_resource_file(resource_file)
            self._load_resource_module(resource_file)
            self._initialize_resources()

            self._is_loaded = True
            self._logger.info(f"资源文件加载成功: {resource_file}")
            return True

        except ResourceLoadError as e:
            self._logger.error(f"资源加载失败: {e}")
            return False
        except Exception as e:
            self._logger.error(f"意外错误: {e}", exc_info=True)
            return False

    def _validate_environment(self) -> None:
        """验证运行环境"""
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                self._logger.warning("QApplication尚未创建，资源可能无法正确加载")
        except ImportError as e:
            raise ResourceLoadError("PySide6未安装") from e

    def _get_resource_file_path(self) -> Path:
        """获取资源文件路径"""
        if self._resource_path:
            return Path(self._resource_path)

        # 默认路径：ui/resources_rc.py
        ui_dir = Path(__file__).resolve().parents[1]
        return ui_dir / "resources_rc.py"

    def _validate_resource_file(self, resource_file: Path) -> None:
        """验证资源文件是否存在"""
        if not resource_file.exists():
            raise ResourceLoadError(f"资源文件不存在: {resource_file}")

    def _load_resource_module(self, resource_file: Path) -> None:
        """加载资源模块"""
        module_name = "ui.resources_rc"

        # 检查是否已导入
        if module_name in sys.modules:
            self._resource_module = sys.modules[module_name]
            return

        # 动态导入
        spec = importlib.util.spec_from_file_location(module_name, str(resource_file))
        if not spec or not spec.loader:
            raise ResourceLoadError(f"无法创建模块规格: {resource_file}")

        self._resource_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = self._resource_module
        spec.loader.exec_module(self._resource_module)

    def _initialize_resources(self) -> None:
        """初始化Qt资源"""
        if not self._resource_module or not hasattr(self._resource_module, 'qInitResources'):
            raise ResourceLoadError("资源模块缺少qInitResources函数")

        try:
            self._resource_module.qInitResources()
        except Exception as e:
            # 如果资源已注册，Qt会抛出异常，这是正常的
            if "already registered" not in str(e).lower():
                raise ResourceLoadError(f"资源初始化失败: {e}") from e


# 全局实例，用于保持向后兼容性
_default_loader = ResourceLoader()


def ensure_resources_loaded() -> bool:
    """
    确保资源文件已加载（向后兼容接口）

    Returns:
        bool: 资源是否成功加载
    """
    return _default_loader.ensure_loaded()


def is_resources_loaded() -> bool:
    """
    检查资源是否已加载

    Returns:
        bool: 资源是否已加载
    """
    return _default_loader.is_loaded


__all__ = [
    "ResourceLoadError",
    "ResourceLoader",
    "ensure_resources_loaded",
    "is_resources_loaded",
]
