"""
患者应用层 - 连接 UI 层和 Service 层
负责协调患者相关的业务逻辑
"""

from typing import List, Dict, Any, Optional
from service.user import PatientService
import logging


class PatientApp:
    """患者应用层 - 连接前后端的中间层"""
    
    def __init__(self, patient_service: PatientService):
        """
        初始化患者应用层
        
        Args:
            patient_service: 注入的患者服务实例
        """
        if patient_service is None:
            raise ValueError("patient_service 参数不能为空")
        self.patient_service = patient_service
        self.logger = logging.getLogger(__name__)
    
    def get_patients(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取患者列表
        
        Args:
            limit: 返回的最大记录数，可选
            
        Returns:
            List[Dict[str, Any]]: 患者列表
        """
        return self.patient_service.get_patients(limit)

    def get_patient_by_id(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """根据病历号获取患者信息"""
        return self.patient_service.get_patient_by_id(patient_id)
    
    def search_patients(self, keyword: str, limit: int = None) -> List[Dict[str, Any]]:
        """
        根据关键词搜索患者（支持姓名和病历号模糊查询）
        
        Args:
            keyword: 搜索关键词（姓名或病历号）
            limit: 返回的最大记录数，可选
            
        Returns:
            List[Dict[str, Any]]: 匹配的患者列表
        """
        return self.patient_service.search_patients(keyword, limit)
    
    def add_patient(self, patient: Dict[str, Any]) -> bool:
        """
        新增患者
        
        Args:
            patient: 患者信息字典
            
        Returns:
            bool: 是否成功
        """
        return self.patient_service.add_patient(patient)
    
    def update_patient(self, patient: Dict[str, Any]) -> bool:
        """
        更新患者信息
        
        Args:
            patient: 患者信息字典（必须包含 PatientId）
        """
        return self.patient_service.update_patient(patient)
    
    def delete_patient(self, patient_id: str) -> bool:
        """
        删除患者（单个）
        
        Args:
            patient_id: 病历号
        """
        return self.patient_service.delete_patient(patient_id)
    
    def get_treat_records(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        根据病历号查询诊疗记录
        
        Args:
            patient_id: 病历号（PatientId）
            
        Returns:
            List[Dict[str, Any]]: 诊疗记录列表
        """
        return self.patient_service.get_treat_records(patient_id)

    def delete_treat_records(self, patient_id: str, start_times: List[str]) -> int:
        """
        根据病历号与治疗开始时间批量删除诊疗记录

        Args:
            patient_id: 病历号
            start_times: TreatStartTime 列表

        Returns:
            int: 删除的行数
        """
        return self.patient_service.delete_treat_records(patient_id, start_times)

