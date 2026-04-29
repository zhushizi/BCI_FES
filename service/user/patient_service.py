"""
患者服务类 - 负责患者信息相关业务逻辑
"""

from typing import List, Dict, Any, Optional, Tuple
import logging

from infrastructure.data import DatabaseService
from service.user._db_base import _DbBase


class PatientService(_DbBase):
    """患者服务类"""

    TABLE_PATIENT = "Patient"
    TABLE_TREAT_RECORD = "TreatRecord"

    def __init__(self, db_service: DatabaseService):
        super().__init__(db_service)
        self.logger = logging.getLogger(__name__)
        self._patient_fields = (
            "PatientId", "Name", "Sex", "Age", "VisitTime",
            "UserId", "PhoneNumber", "IdCard", "DoctorName",
            "Notes", "OperationDate", "Birthday",
            "DiagnosisResult", "DurationOfillness", "UnderlyingHealthCondition",
        )
        self._treat_record_fields = (
            "PatientId",
            "Name",
            "TreatMode",
            "PlanName",
            "Stimposition",
            "StimInterval",
            "TreatTime",
            "TreatStartTime",
        )

    def _patient_select_sql(self) -> str:
        fields = ", ".join(self._patient_fields)
        return f"SELECT {fields} FROM {self.TABLE_PATIENT}"

    def _treat_record_select_sql(self) -> str:
        fields = ", ".join(self._treat_record_fields)
        return f"SELECT {fields} FROM {self.TABLE_TREAT_RECORD}"

    @staticmethod
    def _normalize_patient_id(patient_id: Any) -> str:
        return str(patient_id or "").strip()

    @staticmethod
    def _placeholders(count: int) -> str:
        return ",".join("?" for _ in range(count))

    def get_patients(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取患者列表

        Args:
            limit: 返回的最大记录数，可选
        """
        sql = f"{self._patient_select_sql()} ORDER BY VisitTime DESC"
        params: Tuple[Any, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return self._execute_query_list(sql, params, "获取患者列表失败")

    def get_patient_by_id(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        根据病历号获取患者信息
        """
        pid = self._normalize_patient_id(patient_id)
        if not pid:
            return None
        sql = f"{self._patient_select_sql()} WHERE PatientId = ? LIMIT 1"
        return self._execute_query_one(sql, (pid,), "查询患者信息失败")

    def search_patients(self, keyword: str, limit: int = None) -> List[Dict[str, Any]]:
        """
        根据关键词搜索患者（支持姓名和病历号模糊查询）

        Args:
            keyword: 搜索关键词（姓名或病历号）
            limit: 返回的最大记录数，可选

        Returns:
            List[Dict[str, Any]]: 匹配的患者列表
        """
        if not keyword or not keyword.strip():
            # 如果关键词为空，返回所有患者
            return self.get_patients(limit)

        search_pattern = f"%{keyword.strip()}%"
        sql = f"{self._patient_select_sql()} WHERE Name LIKE ? OR PatientId LIKE ? ORDER BY VisitTime DESC"
        params: Tuple[Any, ...] = (search_pattern, search_pattern)
        if limit is not None:
            sql += " LIMIT ?"
            params = (search_pattern, search_pattern, limit)
        return self._execute_query_list(sql, params, "搜索患者失败")

    def add_patient(self, patient: Dict[str, Any]) -> bool:
        """
        新增患者

        必填字段：PatientId, Name
        其他字段缺省时写空
        """
        sql = f"""
            INSERT INTO {self.TABLE_PATIENT} (
                PatientId, Name, Sex, Age, VisitTime,
                UserId, PhoneNumber, IdCard, DoctorName,
                Notes, OperationDate, Birthday,
                DiagnosisResult, DurationOfillness, UnderlyingHealthCondition
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            patient.get("PatientId", ""),
            patient.get("Name", ""),
            patient.get("Sex", ""),
            patient.get("Age", None),
            patient.get("VisitTime", ""),
            patient.get("UserId", ""),
            patient.get("PhoneNumber", ""),
            patient.get("IdCard", ""),
            patient.get("DoctorName", ""),
            patient.get("Notes", ""),
            patient.get("OperationDate", ""),
            patient.get("Birthday", ""),
            patient.get("DiagnosisResult", ""),
            patient.get("DurationOfillness", ""),
            patient.get("UnderlyingHealthCondition", ""),
        )
        return self._execute_update(sql, params, "新增患者失败") > 0

    def update_patient(self, patient: Dict[str, Any]) -> bool:
        """
        更新患者信息

        必填：PatientId
        """
        if not patient.get("PatientId"):
            return False

        sql = f"""
            UPDATE {self.TABLE_PATIENT} SET
                Name = ?,
                Sex = ?,
                Age = ?,
                VisitTime = ?,
                UserId = ?,
                PhoneNumber = ?,
                IdCard = ?,
                DoctorName = ?,
                Notes = ?,
                OperationDate = ?,
                Birthday = ?,
                DiagnosisResult = ?,
                DurationOfillness = ?,
                UnderlyingHealthCondition = ?
            WHERE PatientId = ?
        """
        params = (
            patient.get("Name", ""),
            patient.get("Sex", ""),
            patient.get("Age", None),
            patient.get("VisitTime", ""),
            patient.get("UserId", ""),
            patient.get("PhoneNumber", ""),
            patient.get("IdCard", ""),
            patient.get("DoctorName", ""),
            patient.get("Notes", ""),
            patient.get("OperationDate", ""),
            patient.get("Birthday", ""),
            patient.get("DiagnosisResult", ""),
            patient.get("DurationOfillness", ""),
            patient.get("UnderlyingHealthCondition", ""),
            patient.get("PatientId", ""),
        )
        return self._execute_update(sql, params, "更新患者失败") > 0

    def get_treat_records(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        根据病历号查询诊疗记录
        
        Args:
            patient_id: 病历号（PatientId）
        
        Returns:
            List[Dict[str, Any]]: 诊疗记录列表
        """
        sql = f"{self._treat_record_select_sql()} WHERE PatientId = ? ORDER BY TreatTime DESC"
        params = (patient_id,)
        return self._execute_query_list(sql, params, "查询诊疗记录失败")

    def delete_treat_records(self, patient_id: str, start_times: List[str]) -> int:
        """
        根据病历号与治疗开始时间批量删除诊疗记录

        Args:
            patient_id: 病历号
            start_times: 需要删除的 TreatStartTime 列表

        Returns:
            int: 实际删除的行数
        """
        if not start_times:
            return 0

        placeholders = self._placeholders(len(start_times))
        sql = f"""
            DELETE FROM {self.TABLE_TREAT_RECORD}
            WHERE PatientId = ?
            AND TreatStartTime IN ({placeholders})
        """
        params = (patient_id, *start_times)
        return self._execute_update(sql, params, "删除诊疗记录失败")

    def delete_patient(self, patient_id: str) -> bool:
        """
        删除单个患者（按病历号）
        """
        if not patient_id:
            return False

        # 先删除患者关联的诊疗记录，避免外键/脏数据
        self._execute_update(
            f"DELETE FROM {self.TABLE_TREAT_RECORD} WHERE PatientId = ?",
            (patient_id,),
            "删除诊疗记录失败",
        )
        # 再删除患者
        return self._execute_update(
            f"DELETE FROM {self.TABLE_PATIENT} WHERE PatientId = ?",
            (patient_id,),
            "删除患者失败",
        ) > 0
