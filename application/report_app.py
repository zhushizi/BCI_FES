"""
报告应用层 - 连接 UI 层和 Service 层
负责协调报告相关的业务逻辑
"""

from typing import List, Dict, Any, Optional
import json
from datetime import datetime
from service.user import ReportService
import logging

from application.session_app import PatientTreatParams


class ReportApp:
    """报告应用层 - 连接前后端的中间层"""
    
    def __init__(self, report_service: ReportService):
        """
        初始化报告应用层
        
        Args:
            report_service: 注入的报告服务实例
        """
        if report_service is None:
            raise ValueError("report_service 参数不能为空")
        self.report_service = report_service
        self.logger = logging.getLogger(__name__)
    
    def add_report(self, report: Dict[str, Any]) -> Optional[int]:
        """
        新增报告记录
        
        Args:
            report: 报告数据字典
        
        Returns:
            Optional[int]: 新插入的报告 ID，失败返回 None
        """
        return self.report_service.add_report(report)

    def add_training_report(
        self,
        *,
        patient_id: str,
        patient_name: str = "",
        treat_start_time: Optional[str] = None,
        treat_time: str = "",
        treat_params: Optional[PatientTreatParams] = None,
        decoder_params: Optional[Dict[str, Any]] = None,
        paradigm_params: Optional[Dict[str, Any]] = None,
        notes: str = "",
    ) -> Optional[int]:
        """
        用例：结束治疗时写入“一次训练一条报告”。

        - 多次训练允许多条：用 `treat_start_time`（TreatStartTime）区分。
        - 训练基本参数/关键指标属于 paradigm，序列化到 ParadigmData（JSON 字符串）。
        """
        pid = str(patient_id or "").strip()
        if not pid:
            return None

        report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = treat_start_time or report_time

        # 把 UI 索引转为更稳定的数值（scheme=1/2, freq=0..9）
        left_scheme = ""
        right_scheme = ""
        left_freq = ""
        right_freq = ""
        left_grade = 0
        right_grade = 0
        if treat_params is not None:
            left_scheme = str(1 if (treat_params.left_scheme_idx or 0) <= 0 else 2)
            right_scheme = str(1 if (treat_params.right_scheme_idx or 0) <= 0 else 2)
            left_freq = str(int(treat_params.left_freq_idx or 0))
            right_freq = str(int(treat_params.right_freq_idx or 0))
            left_grade = int(treat_params.left_grade or 0)
            right_grade = int(treat_params.right_grade or 0)

        report = {
            "patient_id": pid,
            "patient_name": patient_name,
            "report_time": report_time,
            "treat_start_time": start_time,
            "treat_time": treat_time,
            "left_channel_scheme": left_scheme,
            "right_channel_scheme": right_scheme,
            "left_channel_freq": left_freq,
            "right_channel_freq": right_freq,
            "left_channel_grade": left_grade,
            "right_channel_grade": right_grade,
            "decoder_data": json.dumps(decoder_params or {}, ensure_ascii=False),
            "paradigm_data": json.dumps(paradigm_params or {}, ensure_ascii=False),
            "notes": notes or "",
        }
        return self.add_report(report)
    
    def get_reports_by_patient(self, patient_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """
        根据病历号查询报告列表
        
        Args:
            patient_id: 病历号（PatientId）
            limit: 返回的最大记录数，可选
        
        Returns:
            List[Dict[str, Any]]: 报告列表
        """
        return self.report_service.get_reports_by_patient(patient_id, limit)
    
    def get_report_by_id(self, report_id: int) -> Optional[Dict[str, Any]]:
        """
        根据报告 ID 查询单个报告
        
        Args:
            report_id: 报告 ID
        
        Returns:
            Optional[Dict[str, Any]]: 报告数据，不存在返回 None
        """
        return self.report_service.get_report_by_id(report_id)
    
    def update_report(self, report_id: int, report: Dict[str, Any]) -> bool:
        """
        更新报告记录
        
        Args:
            report_id: 报告 ID
            report: 要更新的报告数据字典
        
        Returns:
            bool: 是否成功
        """
        return self.report_service.update_report(report_id, report)
    
    def delete_report(self, report_id: int) -> bool:
        """
        删除单个报告
        
        Args:
            report_id: 报告 ID
        
        Returns:
            bool: 是否成功
        """
        return self.report_service.delete_report(report_id)
    
    def delete_reports_by_patient(self, patient_id: str) -> int:
        """
        删除指定患者的所有报告
        
        Args:
            patient_id: 病历号
        
        Returns:
            int: 删除的记录数
        """
        return self.report_service.delete_reports_by_patient(patient_id)
