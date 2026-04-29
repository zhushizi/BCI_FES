"""
报告服务类 - 负责治疗报告（Report 表）的业务逻辑
用于记录治疗过程中的参数和结果
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from infrastructure.data import DatabaseService
from service.user._db_base import _DbBase


class ReportService(_DbBase):
    """报告服务类"""

    # 统一键名映射：外部可用小写蛇形命名，内部统一转为表字段名
    KEY_ALIASES = {
        # 基础信息
        "patient_id": "PatientId",
        "patientid": "PatientId",
        "patient_name": "PatientName",
        "patientname": "PatientName",
        "report_time": "ReportTime",
        "reporttime": "ReportTime",
        # 通道方案 / 频率
        "left_channel_scheme": "LeftChannelScheme",
        "left_scheme": "LeftChannelScheme",
        "right_channel_scheme": "RightChannelScheme",
        "right_scheme": "RightChannelScheme",
        "left_channel_freq": "LeftChannelFreq",
        "right_channel_freq": "RightChannelFreq",
        # 等级（左/右）
        "left_channel_grade": "LeftChannelGrade",
        "left_grade": "LeftChannelGrade",
        "right_channel_grade": "RightChannelGrade",
        "right_grade": "RightChannelGrade",
        # 解码数据
        "decoder_data": "DecoderData",
        # 范式数据（训练基本参数/关键指标，JSON 字符串）
        "paradigm_data": "ParadigmData",
        # 治疗参数
        "treat_mode": "TreatMode",
        "plan_name": "PlanName",
        "stim_position": "StimPosition",
        "stim_interval": "StimInterval",
        "treat_time": "TreatTime",
        "treat_start_time": "TreatStartTime",
        # 备注
        "notes": "Notes",
    }

    TABLE_REPORT = "Report"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, db_service: DatabaseService):
        super().__init__(db_service)
        self.logger = logging.getLogger(__name__)
        # 初始化表结构
        self._init_table()
        self._report_fields = (
            "ReportId", "PatientId", "PatientName", "ReportTime",
            "LeftChannelScheme", "RightChannelScheme",
            "LeftChannelFreq", "RightChannelFreq",
            "LeftChannelGrade", "RightChannelGrade",
            "DecoderData", "ParadigmData",
            "TreatMode", "PlanName", "StimPosition",
            "StimInterval", "TreatTime", "TreatStartTime",
            "Notes", "CreateTime",
        )

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime(ReportService.DATETIME_FORMAT)

    def _report_select_sql(self) -> str:
        fields = ", ".join(self._report_fields)
        return f"SELECT {fields} FROM {self.TABLE_REPORT}"

    def _normalize_report_data(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        将外部传入的 report 数据统一为表字段命名（帕斯卡命名）
        支持小写蛇形和原始帕斯卡命名共存，后写优先
        """
        normalized: Dict[str, Any] = {}

        # 先保留原始帕斯卡命名键
        for k, v in (report or {}).items():
            if k in self.KEY_ALIASES.values():
                normalized[k] = v

        # 再处理别名（小写蛇形等）
        for alias, target in self.KEY_ALIASES.items():
            if alias in report and target not in normalized:
                normalized[target] = report.get(alias)

        # 确保等级字段为 int
        for grade_key in ("LeftChannelGrade", "RightChannelGrade"):
            if grade_key in normalized:
                try:
                    normalized[grade_key] = int(normalized.get(grade_key) or 0)
                except (ValueError, TypeError):
                    normalized[grade_key] = 0

        return normalized

    def _build_report_params(self, report: Dict[str, Any], report_time: str) -> Tuple[Any, ...]:
        return (
            report.get("PatientId", ""),
            report.get("PatientName", ""),
            report_time,
            report.get("LeftChannelScheme", ""),
            report.get("RightChannelScheme", ""),
            report.get("LeftChannelFreq", ""),
            report.get("RightChannelFreq", ""),
            report.get("LeftChannelGrade", 0),
            report.get("RightChannelGrade", 0),
            report.get("DecoderData", ""),
            report.get("ParadigmData", ""),
            report.get("TreatMode", ""),
            report.get("PlanName", ""),
            report.get("StimPosition", ""),
            report.get("StimInterval", ""),
            report.get("TreatTime", ""),
            report.get("TreatStartTime", ""),
            report.get("Notes", ""),
        )

    def _build_update_params(self, report: Dict[str, Any], report_id: int) -> Tuple[Any, ...]:
        return (
            report.get("PatientName", ""),
            report.get("LeftChannelScheme", ""),
            report.get("RightChannelScheme", ""),
            report.get("LeftChannelFreq", ""),
            report.get("RightChannelFreq", ""),
            report.get("LeftChannelGrade", 0),
            report.get("RightChannelGrade", 0),
            report.get("DecoderData", ""),
            report.get("ParadigmData", ""),
            report.get("TreatMode", ""),
            report.get("PlanName", ""),
            report.get("StimPosition", ""),
            report.get("StimInterval", ""),
            report.get("TreatTime", ""),
            report.get("TreatStartTime", ""),
            report.get("Notes", ""),
            report_id,
        )

    def _init_table(self):
        """初始化 Report 表结构"""
        try:
            if not self.db.table_exists(self.TABLE_REPORT):
                sql = """
                    CREATE TABLE IF NOT EXISTS Report (
                        ReportId INTEGER PRIMARY KEY AUTOINCREMENT,
                        PatientId TEXT NOT NULL,
                        PatientName TEXT,
                        ReportTime TEXT NOT NULL,
                        -- UI 选择的参数
                        LeftChannelScheme TEXT,
                        RightChannelScheme TEXT,
                        LeftChannelFreq TEXT,
                        RightChannelFreq TEXT,
                        LeftChannelGrade INTEGER DEFAULT 0,
                        RightChannelGrade INTEGER DEFAULT 0,
                        -- 解码模块发送的数据（JSON 格式存储）
                        DecoderData TEXT,
                        -- 范式模块发送的数据（JSON 格式存储，用于训练关键指标）
                        ParadigmData TEXT,
                        -- 其他治疗参数
                        TreatMode TEXT,
                        PlanName TEXT,
                        StimPosition TEXT,
                        StimInterval TEXT,
                        TreatTime TEXT,
                        TreatStartTime TEXT,
                        -- 备注信息
                        Notes TEXT,
                        -- 创建时间
                        CreateTime TEXT DEFAULT (datetime('now', 'localtime'))
                    )
                """
                self.db.execute_script(sql)
                self.logger.info("Report 表创建成功")
            else:
                self._ensure_columns()
        except Exception as e:
            self.logger.error(f"初始化 Report 表失败: {e}")

    def _ensure_columns(self) -> None:
        """为已存在的 Report 表补齐缺失列（轻量迁移）。"""
        try:
            info = self.db.get_table_info(self.TABLE_REPORT)
            existing = {row.get("name") for row in (info or [])}
            if "ParadigmData" not in existing:
                self.db.execute_update(f"ALTER TABLE {self.TABLE_REPORT} ADD COLUMN ParadigmData TEXT", ())
                self.logger.info("Report 表已补充列 ParadigmData")
        except Exception as e:
            self.logger.error(f"Report 表列检查/迁移失败: {e}")
    def add_report(self, report: Dict[str, Any]) -> Optional[int]:
        """
        新增报告记录
        
        Args:
            report: 报告数据字典，包含：
                - PatientId: 病历号（必填）
                - PatientName: 患者姓名（可选）
                - LeftChannelScheme: 左通道方案（可选）
                - RightChannelScheme: 右通道方案（可选）
                - LeftChannelFreq: 左通道频率（可选）
                - RightChannelFreq: 右通道频率（可选）
                - LeftChannelGrade: 左通道等级（可选，默认0）
                - RightChannelGrade: 右通道等级（可选，默认0）
                - DecoderData: 解码模块数据，JSON 字符串（可选）
                - TreatMode: 治疗模式（可选）
                - PlanName: 方案名称（可选）
                - StimPosition: 刺激部位（可选）
                - StimInterval: 刺激间隔（可选）
                - TreatTime: 治疗时长（可选）
                - TreatStartTime: 治疗开始时间（可选）
                - Notes: 备注（可选）
        
        Returns:
            Optional[int]: 新插入的报告 ID，失败返回 None
        """
        report = self._normalize_report_data(report)

        if not report.get("PatientId"):
            self.logger.error("新增报告失败：PatientId 不能为空")
            return None

        try:
            # 生成报告时间
            report_time = report.get("ReportTime") or self._now_str()
            
            sql = f"""
                INSERT INTO {self.TABLE_REPORT} (
                    PatientId, PatientName, ReportTime,
                    LeftChannelScheme, RightChannelScheme,
                    LeftChannelFreq, RightChannelFreq,
                    LeftChannelGrade, RightChannelGrade,
                    DecoderData,
                    ParadigmData,
                    TreatMode, PlanName, StimPosition,
                    StimInterval, TreatTime, TreatStartTime,
                    Notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = self._build_report_params(report, report_time)
            self._execute_update(sql, params, "新增报告失败")
            report_id = self.db.get_last_insert_id()
            self.logger.info(f"新增报告成功，ReportId: {report_id}")
            return report_id
        except Exception as e:
            self.logger.error(f"新增报告失败: {e}")
            return None

    def get_reports_by_patient(self, patient_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """
        根据病历号查询报告列表
        
        Args:
            patient_id: 病历号（PatientId）
            limit: 返回的最大记录数，可选
        
        Returns:
            List[Dict[str, Any]]: 报告列表
        """
        sql = f"{self._report_select_sql()} WHERE PatientId = ? ORDER BY ReportTime DESC"
        params: Tuple[Any, ...] = (patient_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (patient_id, limit)
        return self._execute_query_list(sql, params, "查询报告列表失败")

    def get_report_by_id(self, report_id: int) -> Optional[Dict[str, Any]]:
        """
        根据报告 ID 查询单个报告
        
        Args:
            report_id: 报告 ID
        
        Returns:
            Optional[Dict[str, Any]]: 报告数据，不存在返回 None
        """
        sql = f"{self._report_select_sql()} WHERE ReportId = ?"
        return self._execute_query_one(sql, (report_id,), "查询报告失败")

    def update_report(self, report_id: int, report: Dict[str, Any]) -> bool:
        """
        更新报告记录
        
        Args:
            report_id: 报告 ID
            report: 要更新的报告数据字典
        
        Returns:
            bool: 是否成功
        """
        report = self._normalize_report_data(report)

        sql = f"""
            UPDATE {self.TABLE_REPORT} SET
                PatientName = ?,
                LeftChannelScheme = ?,
                RightChannelScheme = ?,
                LeftChannelFreq = ?,
                RightChannelFreq = ?,
                LeftChannelGrade = ?,
                RightChannelGrade = ?,
                DecoderData = ?,
                ParadigmData = ?,
                TreatMode = ?,
                PlanName = ?,
                StimPosition = ?,
                StimInterval = ?,
                TreatTime = ?,
                TreatStartTime = ?,
                Notes = ?
            WHERE ReportId = ?
        """
        params = self._build_update_params(report, report_id)
        return self._execute_update(sql, params, "更新报告失败") > 0

    def delete_report(self, report_id: int) -> bool:
        """
        删除单个报告
        
        Args:
            report_id: 报告 ID
        
        Returns:
            bool: 是否成功
        """
        sql = f"DELETE FROM {self.TABLE_REPORT} WHERE ReportId = ?"
        return self._execute_update(sql, (report_id,), "删除报告失败") > 0

    def delete_reports_by_patient(self, patient_id: str) -> int:
        """
        删除指定患者的所有报告
        
        Args:
            patient_id: 病历号
        
        Returns:
            int: 删除的记录数
        """
        sql = f"DELETE FROM {self.TABLE_REPORT} WHERE PatientId = ?"
        return self._execute_update(sql, (patient_id,), "删除患者报告失败")
