from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from service.business.session.base import BaseSessionRepository


class PatientTreatSessionRepository(BaseSessionRepository):
    TABLE_NAME = "PatientTreatSession"
    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"

    def init_table(self) -> None:
        """初始化 PatientTreatSession 表结构"""
        try:
            if not self.db.table_exists(self.TABLE_NAME):
                sql = self._build_create_patient_treat_table_sql()
                self.db.execute_script(sql)
                self.logger.info("PatientTreatSession 表创建成功")
            else:
                self._ensure_patient_treat_columns()
        except Exception as e:
            self.logger.error(f"初始化 PatientTreatSession 表失败: {e}")

    def upsert_patient_treat_session(
        self,
        *,
        session_id: int,
        patient_id: str,
        stim_channel_a: Optional[int] = None,
        stim_channel_b: Optional[int] = None,
        stim_scheme_ab: Optional[int] = None,
        stim_freq_ab: Optional[int] = None,
        stim_position: str = "",
        paradigm: str = "",
        total_train_duration: str = "",
        train_params: str = "",
        train_result: str = "",
    ) -> bool:
        pid = self.normalize_patient_id(patient_id)
        if not session_id or not pid:
            return False
        try:
            sql = f"""
                INSERT INTO {self.TABLE_NAME} (
                    SessionId, PatientId,
                    StimChannelAIntensity, StimChannelBIntensity,
                    StimSchemeAB, StimFreqAB,
                    StimPosition, Paradigm, TotalTrainDuration,
                    TrainParams, TrainResult,
                    UpdateTime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                ON CONFLICT(SessionId) DO UPDATE SET
                    PatientId = excluded.PatientId,
                    StimChannelAIntensity = COALESCE(excluded.StimChannelAIntensity, StimChannelAIntensity),
                    StimChannelBIntensity = COALESCE(excluded.StimChannelBIntensity, StimChannelBIntensity),
                    StimSchemeAB = COALESCE(excluded.StimSchemeAB, StimSchemeAB),
                    StimFreqAB = COALESCE(excluded.StimFreqAB, StimFreqAB),
                    StimPosition = CASE WHEN excluded.StimPosition != '' THEN excluded.StimPosition ELSE StimPosition END,
                    Paradigm = CASE WHEN excluded.Paradigm != '' THEN excluded.Paradigm ELSE Paradigm END,
                    TotalTrainDuration = CASE WHEN excluded.TotalTrainDuration != '' THEN excluded.TotalTrainDuration ELSE TotalTrainDuration END,
                    TrainParams = CASE WHEN excluded.TrainParams != '' THEN excluded.TrainParams ELSE TrainParams END,
                    TrainResult = CASE WHEN excluded.TrainResult != '' THEN excluded.TrainResult ELSE TrainResult END,
                    UpdateTime = datetime('now', 'localtime')
            """
            self.db.execute_update(
                sql,
                (
                    int(session_id),
                    pid,
                    stim_channel_a,
                    stim_channel_b,
                    stim_scheme_ab,
                    stim_freq_ab,
                    stim_position or "",
                    paradigm or "",
                    total_train_duration or "",
                    train_params or "",
                    train_result or "",
                ),
            )
            return True
        except Exception as e:
            self.logger.error(f"写入 PatientTreatSession 失败: {e}")
            return False

    def update_train_start_time(
        self,
        *,
        session_id: int,
        patient_id: str,
        train_start_time: Optional[str] = None,
    ) -> bool:
        pid = self.normalize_patient_id(patient_id)
        if not session_id or not pid:
            return False
        try:
            train_start_time = train_start_time or self.now_str()
            sql = f"""
                UPDATE {self.TABLE_NAME}
                SET TrainStartTime = CASE
                        WHEN TrainStartTime IS NULL OR TrainStartTime = '' THEN ?
                        ELSE TrainStartTime
                    END,
                    UpdateTime = datetime('now', 'localtime')
                WHERE SessionId = ? AND PatientId = ?
            """
            updated = self.db.execute_update(sql, (train_start_time, int(session_id), pid))
            return updated > 0
        except Exception as e:
            self.logger.error(f"更新 TrainStartTime 失败: {e}")
            return False

    def update_average_reaction_time(
        self,
        *,
        session_id: int,
        patient_id: str,
        average_reaction_time: float,
    ) -> bool:
        return self._update_patient_treat_field(
            session_id=session_id,
            patient_id=patient_id,
            field="AverReactionTime",
            value=str(average_reaction_time),
            error_msg="更新 AverReactionTime 失败",
        )

    def update_average_reaction_time_curve(
        self,
        *,
        session_id: int,
        patient_id: str,
        curve_path: str,
    ) -> bool:
        return self._update_patient_treat_field(
            session_id=session_id,
            patient_id=patient_id,
            field="AverReactionTimeCurve",
            value=curve_path or "",
            error_msg="更新 AverReactionTimeCurve 失败",
        )

    def update_reaction_time_curve(
        self,
        *,
        session_id: int,
        patient_id: str,
        curve_path: str,
    ) -> bool:
        return self._update_patient_treat_field(
            session_id=session_id,
            patient_id=patient_id,
            field="ReactionTimeCurve",
            value=curve_path or "",
            error_msg="更新 ReactionTimeCurve 失败",
        )

    def update_train_stop_info(
        self,
        *,
        session_id: int,
        patient_id: str,
        countdown_minutes: Optional[float],
    ) -> bool:
        pid = self.normalize_patient_id(patient_id)
        if not session_id or not pid:
            return False
        try:
            train_stop_time = datetime.now()
            row = self.get_patient_treat_session_by_session_id(int(session_id)) or {}
            start_str = row.get("TrainStartTime") or ""
            try:
                train_start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                train_start_time = train_stop_time
            duration_sec = max(0, int((train_stop_time - train_start_time).total_seconds()))
            total_train_duration = str(timedelta(seconds=duration_sec))
            progress_value = ""
            if countdown_minutes:
                total_sec = float(countdown_minutes) * 60.0
                if total_sec > 0:
                    progress = min(duration_sec / total_sec * 100.0, 100.0)
                    progress_value = f"{progress:.2f}"
            sql = f"""
                UPDATE {self.TABLE_NAME}
                SET TrainStopTime = ?,
                    TotalTrainDuration = ?,
                    TrainProgress = ?,
                    UpdateTime = datetime('now', 'localtime')
                WHERE SessionId = ? AND PatientId = ?
            """
            updated = self.db.execute_update(
                sql,
                (
                    train_stop_time.strftime("%Y-%m-%d %H:%M:%S"),
                    total_train_duration,
                    progress_value,
                    int(session_id),
                    pid,
                ),
            )
            return updated > 0
        except Exception as e:
            self.logger.error(f"更新 TrainStopTime/TotalTrainDuration/TrainProgress 失败: {e}")
            return False

    def update_erds_path(
        self,
        *,
        session_id: int,
        patient_id: str,
        erds_path: str,
    ) -> bool:
        return self._update_patient_treat_field(
            session_id=session_id,
            patient_id=patient_id,
            field="ERDsPath",
            value=erds_path or "",
            error_msg="更新 ERDsPath 失败",
        )

    def create_session(
        self,
        patient_info: Dict[str, Any],
        plan_name: str = "",
        body_part: str = "",
        paradigm: str = "",
        start_time: Optional[str] = None,
    ) -> Optional[int]:
        """创建新会话（仅写入 PatientTreatSession），返回 SessionId。"""
        patient_id = self.normalize_patient_id(
            patient_info.get("PatientId") or patient_info.get("patient_id")
        )
        if not patient_id:
            self.logger.error("创建会话失败：PatientId 为空")
            return None
        try:
            start_time = start_time or self.now_str()
            sql = f"""
                INSERT INTO {self.TABLE_NAME} (
                    PatientId, StimPosition, Paradigm, StartTime, Status
                ) VALUES (?, ?, ?, ?, ?)
            """
            params = (
                patient_id,
                body_part or "",
                paradigm or "",
                start_time,
                self.STATUS_ACTIVE,
            )
            self.db.execute_update(sql, params)
            session_id = self.db.get_last_insert_id()
            self.logger.info("创建治疗会话成功，SessionId: %s", session_id)
            return session_id
        except Exception as e:
            self.logger.error("创建治疗会话失败: %s", e)
            return None

    def end_session(
        self, session_id: int, reason: str = "manual_exit", end_time: Optional[str] = None
    ) -> bool:
        """结束会话（更新 EndTime、EndReason、Status）。"""
        if not session_id:
            return False
        try:
            end_time = end_time or self.now_str()
            sql = f"""
                UPDATE {self.TABLE_NAME}
                SET EndTime = ?, EndReason = ?, Status = ?
                WHERE SessionId = ?
            """
            updated = self.db.execute_update(
                sql, (end_time, reason or "", self.STATUS_ENDED, session_id)
            )
            return updated > 0
        except Exception as e:
            self.logger.error("结束治疗会话失败: %s", e)
            return False

    def get_session_by_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        """按 SessionId 查询会话（等同 get_patient_treat_session_by_session_id）。"""
        return self.get_patient_treat_session_by_session_id(session_id)

    def get_active_sessions_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """查询某患者的进行中会话（Status = active）。"""
        pid = self.normalize_patient_id(patient_id)
        if not pid:
            return []
        sql = f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE PatientId = ? AND Status = ?
            ORDER BY StartTime DESC
        """
        return self._execute_query_list(
            sql, (pid, self.STATUS_ACTIVE), "查询患者进行中会话失败"
        )

    def get_patient_treat_session_by_session_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        sql = f"SELECT * FROM {self.TABLE_NAME} WHERE SessionId = ?"
        return self._execute_query_one(sql, (int(session_id),), "查询 PatientTreatSession 失败")

    def get_patient_treat_sessions_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        pid = self.normalize_patient_id(patient_id)
        if not pid:
            return []
        sql = f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE PatientId = ?
            ORDER BY UpdateTime DESC
        """
        return self._execute_query_list(sql, (pid,), "查询 PatientTreatSession 列表失败")

    def delete_patient_treat_sessions(self, session_ids: List[int]) -> int:
        if not session_ids:
            return 0
        placeholders = ",".join("?" for _ in session_ids)
        sql = f"DELETE FROM {self.TABLE_NAME} WHERE SessionId IN ({placeholders})"
        return self._execute_update(sql, tuple(session_ids), "删除 PatientTreatSession 失败")

    def _ensure_patient_treat_columns(self) -> None:
        """为已存在的 PatientTreatSession 表补齐缺失列（轻量迁移）。"""
        try:
            info = self.db.get_table_info(self.TABLE_NAME)
            existing = {row.get("name") for row in (info or [])}
            desired = self._patient_treat_table_columns()
            missing = desired - existing
            for col in missing:
                if col in ("StimChannelAIntensity", "StimChannelBIntensity", "StimSchemeAB", "StimFreqAB"):
                    self.db.execute_update(
                        f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {col} INTEGER",
                        (),
                    )
                elif col in ("Status",):
                    self.db.execute_update(
                        f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {col} TEXT DEFAULT '{self.STATUS_ACTIVE}'",
                        (),
                    )
                elif col in ("CreateTime",):
                    self.db.execute_update(
                        f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {col} TEXT DEFAULT (datetime('now', 'localtime'))",
                        (),
                    )
                elif col in ("UpdateTime",):
                    self.db.execute_update(
                        f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {col} TEXT DEFAULT (datetime('now', 'localtime'))",
                        (),
                    )
                else:
                    self.db.execute_update(
                        f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {col} TEXT",
                        (),
                    )
            if missing:
                self.logger.info("PatientTreatSession 表已补充列: %s", ", ".join(sorted(missing)))
        except Exception as e:
            self.logger.error(f"PatientTreatSession 表列检查/迁移失败: {e}")

    def _patient_treat_table_columns(self) -> set[str]:
        return {
            "SessionId", "PatientId",
            "StimChannelAIntensity", "StimChannelBIntensity",
            "StimSchemeAB", "StimFreqAB",
            "StimPosition", "Paradigm",
            "StartTime", "EndTime", "EndReason", "Status",
            "TotalTrainDuration",
            "TrainStartTime",
            "TrainStopTime",
            "AverReactionTime",
            "AverReactionTimeCurve",
            "ReactionTimeCurve",
            "TrainProgress",
            "ERDsPath",
            "TrainParams", "TrainResult",
            "CreateTime", "UpdateTime",
        }

    def _build_create_patient_treat_table_sql(self) -> str:
        return f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                SessionId INTEGER PRIMARY KEY AUTOINCREMENT,
                PatientId TEXT NOT NULL,
                StimChannelAIntensity INTEGER,
                StimChannelBIntensity INTEGER,
                StimSchemeAB INTEGER,
                StimFreqAB INTEGER,
                StimPosition TEXT,
                Paradigm TEXT,
                StartTime TEXT,
                EndTime TEXT,
                EndReason TEXT,
                Status TEXT DEFAULT '{self.STATUS_ACTIVE}',
                TotalTrainDuration TEXT,
                TrainStartTime TEXT,
                TrainStopTime TEXT,
                AverReactionTime TEXT,
                AverReactionTimeCurve TEXT,
                ReactionTimeCurve TEXT,
                TrainProgress TEXT,
                ERDsPath TEXT,
                TrainParams TEXT,
                TrainResult TEXT,
                CreateTime TEXT DEFAULT (datetime('now', 'localtime')),
                UpdateTime TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """

    def _update_patient_treat_field(
        self,
        *,
        session_id: int,
        patient_id: str,
        field: str,
        value: Any,
        error_msg: str,
    ) -> bool:
        pid = self.normalize_patient_id(patient_id)
        if not session_id or not pid:
            return False
        sql = f"""
            UPDATE {self.TABLE_NAME}
            SET {field} = ?,
                UpdateTime = datetime('now', 'localtime')
            WHERE SessionId = ? AND PatientId = ?
        """
        updated = self._execute_update(sql, (value, int(session_id), pid), error_msg)
        return updated > 0
