"""
诊疗报告 PDF 生成（无 UI）。
根据会话/患者数据构建报告 HTML，并生成 PDF 文件，供展示与导出使用。
"""

from __future__ import annotations

import base64
import html
import json
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtPrintSupport import QPrinter


def _strip_erds(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_erds(v) for k, v in value.items() if k != "ERDs"}
    if isinstance(value, list):
        return [_strip_erds(v) for v in value]
    return value


def _extract_complete_rate(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, str):
            parsed = json.loads(value)
        elif isinstance(value, dict):
            parsed = value
        else:
            return ""
        for key in ("t_complete_r", "complete_rate", "completeRate"):
            if key in parsed and parsed.get(key) not in (None, ""):
                return str(parsed.get(key))
    except Exception:
        pass
    return ""


def _format_json_value(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(_strip_erds(value), ensure_ascii=False, indent=2)
    if isinstance(value, str):
        try:
            return json.dumps(_strip_erds(json.loads(value)), ensure_ascii=False, indent=2)
        except Exception:
            return value
    return str(value)


def _format_stim_position(position: Any) -> str:
    if position is None or position == "":
        return "—"
    value = str(position).strip()
    if value == "up":
        return "上肢"
    if value == "down":
        return "下肢"
    return value


def _safe_str(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _get_patient_info(patient: Optional[Dict[str, Any]]) -> Dict[str, str]:
    patient = patient or {}
    return {
        "Name": _safe_str(patient.get("Name")),
        "Sex": _safe_str(patient.get("Sex")),
        "Age": _safe_str(patient.get("Age")),
        "UnderlyingHealthCondition": _safe_str(patient.get("UnderlyingHealthCondition")),
        "DurationOfillness": _safe_str(patient.get("DurationOfillness")),
        "DiagnosisResult": _safe_str(patient.get("DiagnosisResult")),
    }


def _get_training_info(detail: Optional[Dict[str, Any]]) -> Dict[str, str]:
    detail = detail or {}
    return {
        "TrainStartTime": _safe_str(detail.get("TrainStartTime")),
        "TrainStopTime": _safe_str(detail.get("TrainStopTime")),
        "TotalTrainDuration": _safe_str(detail.get("TotalTrainDuration")),
        "TrainProgress": _safe_str(detail.get("TrainProgress")),
        "StimFreqAB": _safe_str(detail.get("StimFreqAB")),
        "AverReactionTime": _safe_str(detail.get("AverReactionTime")),
    }


def _get_treatment_info(detail: Optional[Dict[str, Any]]) -> Dict[str, str]:
    detail = detail or {}
    def _map_scheme(v: Any) -> str:
        if v is None or v == "":
            return "—"
        try:
            return str(int(v) + 1)
        except Exception:
            return str(v)
    def _map_freq(v: Any) -> str:
        if v is None or v == "":
            return "—"
        mapping = {
            0: "0.5",
            1: "0.6",
            2: "0.7",
            3: "0.8",
            4: "0.9",
            5: "1.0",
            6: "2.0",
            7: "3.0",
            8: "4.0",
            9: "5.0",
        }
        try:
            key = int(v)
            return mapping.get(key, str(v))
        except Exception:
            return str(v)
    return {
        "StimChannelAIntensity": _safe_str(detail.get("StimChannelAIntensity")),
        "StimChannelBIntensity": _safe_str(detail.get("StimChannelBIntensity")),
        "StimSchemeAB": _map_scheme(detail.get("StimSchemeAB")),
        "StimFreqAB": _map_freq(detail.get("StimFreqAB")),
        "Paradigm": _safe_str(detail.get("Paradigm")),
        "StimPosition": _safe_str(detail.get("StimPosition")),
    }


def _build_patient_section(patient: Optional[Dict[str, Any]]) -> str:
    items = []
    mapping = [
        ("姓名", "Name"),
        ("性别", "Sex"),
        ("年龄", "Age"),
        ("病程时长", "DurationOfillness"),
        ("诊断结果", "DiagnosisResult"),
        ("基础病史", "UnderlyingHealthCondition"),
    ]
    patient = patient or {}
    for label, key in mapping:
        value = patient.get(key)
        display = "" if value is None or value == "" else str(value)
        items.append(f"<b>{html.escape(label)}:</b> {html.escape(display) if display else '—'}")
    items.append("<b>不良事件记录:</b> —")
    return "<b>患者基本情况</b><br>" + "<br>".join(items)


def _build_train_section(detail: Dict[str, Any]) -> str:
    if not detail:
        return ""
    items = []
    start_time = detail.get("TrainStartTime") or ""
    stop_time = detail.get("TrainStopTime") or ""
    if start_time or stop_time:
        items.append(f"<b>训练起止时间:</b> {html.escape(str(start_time))} ~ {html.escape(str(stop_time))}")
    total_duration = detail.get("TotalTrainDuration")
    if total_duration:
        items.append(f"<b>总训练时长:</b> {html.escape(str(total_duration))}")
        items.append(f"<b>单次训练时长:</b> {html.escape(str(total_duration))}")
    progress = detail.get("TrainProgress")
    if progress:
        items.append(f"<b>本次进度:</b> {html.escape(str(progress))}%")
    freq = detail.get("StimFreqAB")
    if freq is not None and freq != "":
        items.append(f"<b>训练频率:</b> {html.escape(str(freq))}")
    complete_rate = _extract_complete_rate(detail.get("TrainResult"))
    if complete_rate:
        items.append(f"<b>任务完成率:</b> {html.escape(complete_rate)}")
    avg_reaction = detail.get("AverReactionTime")
    if avg_reaction is not None and avg_reaction != "":
        items.append(f"<b>平均反应时间:</b> {html.escape(str(avg_reaction))}")
    if not items:
        return ""
    return "<b>训练基本参数</b><br>" + "<br>".join(items)


def _mime_for_path(path: Path) -> str:
    suf = (path.suffix or "").lower()
    if suf in (".png",):
        return "image/png"
    if suf in (".jpg", ".jpeg",):
        return "image/jpeg"
    if suf in (".gif",):
        return "image/gif"
    if suf in (".webp",):
        return "image/webp"
    return "image/png"


def _build_image_sections(
    detail: Dict[str, Any], root_dir: Path, embed_images: bool = False
) -> list[str]:
    sections: list[str] = []
    for label, key in (("反应时间曲线", "ReactionTimeCurve"), ("ERDs", "ERDsPath")):
        raw_path = (detail or {}).get(key)
        if not raw_path:
            continue
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = root_dir / path
        if not path.exists():
            sections.append(f"<b>{html.escape(label)}:</b> 未找到图片 ({html.escape(str(raw_path))})")
            continue
        if embed_images:
            try:
                data = path.read_bytes()
                b64 = base64.b64encode(data).decode("ascii")
                mime = _mime_for_path(path)
                src = f"data:{mime};base64,{b64}"
            except Exception:
                src = path.as_uri()
        else:
            src = path.as_uri()
        sections.append(
            f"<b>{html.escape(label)}:</b><br>"
            f'<img src="{src}" style="max-width: 100%; height: auto;"/>'
        )
    return sections


def build_report_html(
    session_app,
    report_app,
    patient_id: str,
    patient_name: str,
    session_id: Optional[int],
    record_data: Optional[Dict[str, Any]] = None,
    embed_images_for_web: bool = False,
) -> str:
    """
    根据会话/患者数据构建报告 HTML 字符串。
    embed_images_for_web=True 时图片以 base64 嵌入，便于网页内展示。
    """
    record_data = record_data or {}
    root_dir = Path(__file__).resolve().parents[2]

    detail = None
    if session_app and session_id is not None:
        try:
            detail = session_app.get_patient_treat_session_by_session_id(session_id)
        except Exception:
            detail = None

    patient = None
    if session_app:
        pid = (detail or {}).get("PatientId") or patient_id
        if pid:
            try:
                patient_app = getattr(session_app, "patient_app", None)
                if patient_app:
                    patient = patient_app.get_patient_by_id(str(pid))
            except Exception:
                pass

    pi = _get_patient_info(patient)
    ti = _get_training_info(detail)
    tri = _get_treatment_info(detail)
    stim_label = _format_stim_position(tri.get("StimPosition"))
    export_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    case_id = _safe_str((detail or {}).get("PatientId") or patient_id)

    def progress_bar(value: str) -> str:
        try:
            pct = float(str(value).replace("%", ""))
        except ValueError:
            pct = 0
        pct = max(0, min(100, pct))
        total_px = 120
        fill_px = int(total_px * pct / 100)
        return (
            '<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;">'
            '<tr>'
            '<td style="white-space:nowrap;">'
            '<table class="progress-table" width="120" cellspacing="0" cellpadding="0"'
            ' style="border:1px solid #000;border-collapse:collapse;height:16px;margin-right:6px;">'
            '<tr>'
            f'<td width="{fill_px}" style="background:#000;height:16px;"></td>'
            f'<td width="{total_px - fill_px}" style="background:#fff;height:16px;"></td>'
            '</tr>'
            '</table>'
            '</td>'
            f'<td style="white-space:nowrap;padding-left:4px;">{pct:.0f}%</td>'
            '</tr>'
            '</table>'
        )

    def img_src(key: str) -> tuple[str | None, str | None]:
        raw_path = (detail or {}).get(key)
        if not raw_path:
            return None, "暂无"
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = root_dir / path
        if not path.exists():
            return None, "未找到图片"
        if embed_images_for_web:
            try:
                data = path.read_bytes()
                b64 = base64.b64encode(data).decode("ascii")
                return f"data:{_mime_for_path(path)};base64,{b64}", None
            except Exception:
                pass
        return path.as_uri(), None

    def resolve_notes() -> str:
        notes = ""
        if record_data:
            notes = record_data.get("备注", "") or record_data.get("Notes", "") or ""
        if not notes and patient:
            notes = patient.get("Notes", "") or ""
        if not notes and report_app and case_id:
            try:
                reports = report_app.get_reports_by_patient(str(case_id))
            except Exception:
                reports = []
            candidate_time = ""
            if record_data:
                candidate_time = record_data.get("治疗时间", "") or ""
            if not candidate_time and detail:
                candidate_time = str(detail.get("TrainStartTime") or detail.get("CreateTime") or "")
            if reports:
                if candidate_time:
                    for r in reports:
                        if str(r.get("TreatStartTime") or "") == candidate_time or str(r.get("ReportTime") or "") == candidate_time:
                            notes = r.get("Notes", "") or ""
                            break
                if not notes:
                    notes = reports[0].get("Notes", "") or ""
        return _safe_str(notes)

    def calc_weekly_freq() -> str:
        if not session_app or not case_id:
            return "—"
        try:
            sessions = session_app.get_patient_treat_sessions_by_patient(str(case_id)) or []
        except Exception:
            sessions = []
        ref_str = ""
        if detail:
            ref_str = (
                str(detail.get("TrainStopTime") or "")
                or str(detail.get("TrainStartTime") or "")
                or str(detail.get("UpdateTime") or "")
            )
        try:
            ref_time = datetime.strptime(ref_str, "%Y-%m-%d %H:%M:%S") if ref_str else datetime.now()
        except Exception:
            ref_time = datetime.now()
        week_start = ref_time - timedelta(days=7)
        count = 0
        for row in sessions:
            tstr = (
                str(row.get("TrainStartTime") or "")
                or str(row.get("StartTime") or "")
                or str(row.get("CreateTime") or "")
            )
            try:
                t = datetime.strptime(tstr, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            if week_start <= t <= ref_time:
                count += 1
        return f"{count}次/周" if count > 0 else "—"

    def _parse_duration_to_seconds(value: str) -> int:
        if not value or value == "—":
            return 0
        try:
            parts = str(value).split(":")
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + int(float(s))
            if len(parts) == 2:
                m, s = parts
                return int(m) * 60 + int(float(s))
        except Exception:
            return 0
        return 0

    def _format_seconds(total: int) -> str:
        if total <= 0:
            return "—"
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def calc_total_duration_sum() -> str:
        if not session_app or not case_id:
            return ti.get("TotalTrainDuration") or "—"
        try:
            sessions = session_app.get_patient_treat_sessions_by_patient(str(case_id)) or []
        except Exception:
            sessions = []
        total_sec = 0
        for row in sessions:
            total_sec += _parse_duration_to_seconds(str(row.get("TotalTrainDuration") or ""))
        return _format_seconds(total_sec)

    css = """
    <style>
        body { font-family: 'Microsoft YaHei', SimSun, sans-serif; font-size: 14px; line-height: 1.5; color: #000; margin: 24px; }
        .title { font-size: 22px; font-weight: bold; text-align: center; margin: 6px 0 8px 0; }
        .header-row { font-size: 13px; margin-bottom: 8px; width: 100%; border-collapse: collapse; }
        .header-row td { padding: 0; }
        .divider { border-top: 1px solid #000; height: 0; margin: 6px 0; width: 100%; display: block; }
        .section-title { font-size: 16px; font-weight: bold; margin: 0 0 10px 0; border-bottom: 2px solid #000; padding-bottom: 3px; }
        .row-3col { width: 100%; border-collapse: collapse; margin: 3px 0; table-layout: fixed; }
        .row-3col td { padding: 0; }
        .row-2col { width: 100%; border-collapse: collapse; margin: 3px 0; }
        .row-2col td { padding: 0; }
        .label { font-weight: bold; margin-right: 4px; }
        .remark-box { width: 100%; border: 2px solid #000; border-radius: 15px; padding: 0; margin: 8px 0 16px 0; box-sizing: border-box; border-collapse: collapse; }
        .remark-box td { border: none; padding: 10px 12px; }
        .remark-content { min-height: 36px; }
        .progress-wrap { display: inline-block; }
        .progress-inline { display: inline-flex; align-items: center; white-space: nowrap; }
        .progress-table { border: 1px solid #000; border-collapse: collapse; }
        .progress-value { margin-left: 2px; }
        .chart-title { font-size: 15px; font-weight: bold; text-align: center; margin: 14px 0 6px 0; }
        .chart-img { max-width: 90%; height: auto; border: 1px solid #ddd; display: block; margin: 0 auto; page-break-inside: avoid; break-inside: avoid; }
        .chart-img-erds { max-width: 80%; max-height: 500px; height: auto; }
        .chart-center { text-align: center; page-break-inside: avoid; break-inside: avoid; }
    </style>
    """

    parts: list[str] = [css]

    parts.append('<div class="title">诊疗报告</div>')
    parts.append(
        '<table class="header-row" width="100%">'
        '<tr>'
        f'<td align="left">病历号: {html.escape(case_id)}</td>'
        f'<td align="right">报告导出时间: {html.escape(export_time)}</td>'
        '</tr>'
        '</table>'
    )
    parts.append('<table width="100%" cellspacing="0" cellpadding="0" style="margin:4px 0 6px 0;border-collapse:collapse;"><tr><td style="border-top:1px solid #000;height:0;"></td></tr></table>')

    parts.append('<div class="section-title">患者基本情况</div>')
    parts.append('<div style="height:6px;"></div>')
    parts.append(
        '<table class="row-3col" width="100%">'
        '<tr>'
        f'<td width="40%" align="left"><span class="label">姓名:</span>{html.escape(pi["Name"])}</td>'
        f'<td width="30%" align="center"><span class="label">性别:</span>{html.escape(pi["Sex"])}</td>'
        f'<td width="30%" align="right"><span class="label">年龄:</span>{html.escape(pi["Age"])}</td>'
        '</tr>'
        '</table>'
    )
    parts.append(
        '<table class="row-3col" width="100%">'
        '<tr>'
        f'<td width="40%" align="left"><span class="label">基础病史:</span>{html.escape(pi["UnderlyingHealthCondition"])}</td>'
        f'<td width="30%" align="center"><span class="label">患病时长:</span>{html.escape(pi["DurationOfillness"])}</td>'
        '<td width="30%" align="right">&nbsp;</td>'
        '</tr>'
        '</table>'
    )
    parts.append(
        '<div class="row-2col">'
        f'<div class="cell"><span class="label">诊断结果:</span>{html.escape(pi["DiagnosisResult"])}</div>'
        '<div class="cell"></div>'
        '</div>'
    )
    notes_text = resolve_notes()
    notes_html = html.escape(notes_text).replace("\n", "<br>")
    parts.append(
        '<table class="remark-box" width="100%" cellspacing="0" cellpadding="0"'
        ' style="border:2px solid #000;border-radius:15px;">'
        '<tr><td>'
        '<div><span class="label">备注:</span></div>'
        f'<div class="remark-content">{notes_html}</div>'
        '</td></tr>'
        '</table>'
    )
    parts.append('<table width="100%" cellspacing="0" cellpadding="0" style="margin:12px 0;border-collapse:collapse;"><tr><td style="border-top:1px solid #000;height:0;"></td></tr></table>')

    parts.append('<div class="section-title">基本训练情况</div>')
    parts.append('<div style="height:6px;"></div>')
    parts.append(
        '<table class="row-2col" width="100%">'
        '<tr>'
        f'<td width="70%" align="left"><span class="label">起止训练时间:</span>{html.escape(ti["TrainStartTime"])}—{html.escape(ti["TrainStopTime"])}</td>'
        f'<td width="30%" align="center"><span class="label">总治疗时长:</span>{html.escape(calc_total_duration_sum())}</td>'
        '</tr>'
        '</table>'
    )
    parts.append(
        '<table class="row-2col" width="100%">'
        '<tr>'
        f'<td width="50%" align="left"><span class="label">本次训练时长:</span>{html.escape(ti["TotalTrainDuration"])}</td>'
        f'<td width="50%" align="center"><span class="label">平均反应时间:</span>{html.escape(ti["AverReactionTime"])}</td>'
        '</tr>'
        '</table>'
    )
    parts.append(
        '<table class="row-2col" width="100%">'
        '<tr>'
        f'<td width="50%" align="left"><span class="label">训练频次:</span>{html.escape(calc_weekly_freq())}</td>'
        '<td width="50%" align="center">'
        '<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin:0 auto;">'
        '<tr>'
        '<td style="white-space:nowrap;"><span class="label">本次进度:</span></td>'
        f'<td style="white-space:nowrap;">{progress_bar(ti["TrainProgress"])}</td>'
        '</tr>'
        '</table>'
        '</td>'
        '</tr>'
        '</table>'
    )
    parts.append('<table width="100%" cellspacing="0" cellpadding="0" style="margin:4px 0 6px 0;border-collapse:collapse;"><tr><td style="border-top:1px solid #000;height:0;"></td></tr></table>')

    parts.append(f'<div class="section-title">治疗基本情况-{html.escape(stim_label)}</div>')
    parts.append('<div style="height:6px;"></div>')
    parts.append(
        '<table class="row-2col" width="100%">'
        '<tr>'
        f'<td width="50%" align="left"><span class="label">通道A强度:</span>{html.escape(tri["StimChannelAIntensity"])}</td>'
        f'<td width="50%" align="center"><span class="label">通道B强度:</span>{html.escape(tri["StimChannelBIntensity"])}</td>'
        '</tr>'
        '</table>'
    )
    parts.append(
        '<table class="row-2col" width="100%">'
        '<tr>'
        f'<td width="50%" align="left"><span class="label">刺激方案:</span>{html.escape("方案" + tri["StimSchemeAB"])}</td>'
        f'<td width="50%" align="center"><span class="label">刺激频率:</span>{html.escape(tri["StimFreqAB"])}Hz</td>'
        '</tr>'
        '</table>'
    )
    parts.append(
        '<div class="row-2col">'
        f'<div class="cell"><span class="label">范式:</span>{html.escape(tri["Paradigm"])}</div>'
        '<div class="cell"></div>'
        '</div>'
    )

    parts.append('<table width="100%" cellspacing="0" cellpadding="0" style="margin:12px 0 8px 0;border-collapse:collapse;"><tr><td style="border-top:1px solid #000;height:0;"></td></tr></table>')
    parts.append('<div class="chart-title">反应时间折线图</div>')
    rt_src, rt_err = img_src("ReactionTimeCurve")
    if rt_src:
        parts.append(f'<div class="chart-center"><img class="chart-img" src="{rt_src}" alt="反应时间折线图"></div>')
    else:
        parts.append(f'<div>{html.escape(rt_err or "暂无")}</div>')

    parts.append('<div style="page-break-before: always;"></div>')
    parts.append('<table width="100%" cellspacing="0" cellpadding="0" style="margin:12px 0 8px 0;border-collapse:collapse;"><tr><td style="border-top:1px solid #000;height:0;"></td></tr></table>')
    parts.append('<div class="chart-title">ERDs图</div>')
    erds_src, erds_err = img_src("ERDsPath")
    if erds_src:
        parts.append(f'<div class="chart-center"><img class="chart-img chart-img-erds" src="{erds_src}" alt="ERDs图"></div>')
    else:
        parts.append(f'<div>{html.escape(erds_err or "暂无")}</div>')

    return "".join(parts) if parts else "<p>暂无报告细节</p>"


def html_to_pdf(html_content: str, pdf_path: str) -> bool:
    """将 HTML 字符串写入为 PDF 文件。需在主线程（有 Qt 事件循环）中调用。"""
    try:
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(pdf_path)
        doc = QTextDocument()
        doc.setHtml(html_content)
        doc.print_(printer)
        return True
    except Exception:
        return False


def sanitize_filename(name: str) -> str:
    if not name:
        return ""
    return re.sub(r'[<>:"/\\|?*]', "_", str(name).strip())


def default_pdf_filename(patient_id: Optional[str], suffix: str = "诊疗报告") -> str:
    base = sanitize_filename(patient_id) if patient_id else suffix
    return f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"


def generate_and_open_pdf(
    session_app,
    report_app,
    patient_id: str,
    patient_name: str,
    session_id: Optional[int],
    record_data: Optional[Dict[str, Any]] = None,
    save_path: Optional[str] = None,
) -> Optional[str]:
    """
    生成报告 PDF 并打开。
    - save_path 为 None：生成到临时文件并打开（展示）。
    - save_path 有值：生成到该路径并打开（导出）。
    返回生成的 PDF 路径，失败返回 None。
    """
    html_content = build_report_html(
        session_app=session_app,
        report_app=report_app,
        patient_id=patient_id,
        patient_name=patient_name or "",
        session_id=session_id,
        record_data=record_data,
    )
    if save_path:
        path = save_path.strip()
        if not path.lower().endswith(".pdf"):
            path = path + ".pdf"
    else:
        fd = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        path = fd.name
        fd.close()
    if not html_to_pdf(html_content, path):
        return None
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path
