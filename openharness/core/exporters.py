import json
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
import html


def export_to_json(run_detail: Dict[str, Any], indent: int = 2) -> str:
    """Export evaluation run details to JSON string."""
    return json.dumps(run_detail, indent=indent)


def export_to_junit_xml(run_detail: Dict[str, Any]) -> str:
    """Export evaluation run details to JUnit XML for CI/CD integrations."""
    testsuite = ET.Element("testsuite", {
        "name": run_detail.get("name", "OpenHarness Test Suite"),
        "tests": str(run_detail.get("total_count", 0)),
        "failures": str(run_detail.get("failed_count", 0)),
        "time": str(run_detail.get("duration_ms", 0.0) / 1000.0),
        "timestamp": str(run_detail.get("timestamp", ""))
    })

    for res in run_detail.get("results", []):
        testcase = ET.SubElement(testsuite, "testcase", {
            "name": res.get("test_case_name", "test"),
            "classname": run_detail.get("name", "OpenHarness"),
            "time": str(res.get("duration_ms", 0.0) / 1000.0)
        })

        if not res.get("passed", False):
            failed_metrics = [m for m in res.get("metrics", []) if not m.get("passed", True)]
            failure_reason = "\n".join([f"{m.get('name')}: {m.get('reason')}" for m in failed_metrics]) or "Test failed"
            failure_elem = ET.SubElement(testcase, "failure", {"message": "Evaluation assertion failed"})
            failure_elem.text = failure_reason

    return ET.tostring(testsuite, encoding="utf-8").decode("utf-8")


def export_to_html(run_detail: Dict[str, Any]) -> str:
    """Export evaluation run details to a standalone, stylish HTML report."""
    run_name = html.escape(str(run_detail.get("name", "Run Report")))
    passed_cnt = run_detail.get("passed_count", 0)
    total_cnt = run_detail.get("total_count", 0)
    pass_rate = (passed_cnt / total_cnt * 100.0) if total_cnt > 0 else 0.0

    cases_html = ""
    for res in run_detail.get("results", []):
        case_name = html.escape(str(res.get("test_case_name", "")))
        is_pass = res.get("passed", False)
        status_badge = '<span style="color:#10b981;font-weight:bold;">[PASSED]</span>' if is_pass else '<span style="color:#ef4444;font-weight:bold;">[FAILED]</span>'
        
        metrics_rows = ""
        for m in res.get("metrics", []):
            m_pass = m.get("passed", False)
            icon = "✔" if m_pass else "✖"
            color = "#10b981" if m_pass else "#ef4444"
            metrics_rows += f"""
                <tr style="border-bottom:1px solid #374151;">
                    <td style="padding:8px;color:{color};">{icon}</td>
                    <td style="padding:8px;font-weight:600;">{html.escape(str(m.get('name')))}</td>
                    <td style="padding:8px;color:#9ca3af;">{html.escape(str(m.get('category')))}</td>
                    <td style="padding:8px;">{html.escape(str(m.get('reason')))}</td>
                </tr>
            """

        cases_html += f"""
            <div style="background:#1f2937;border-radius:8px;padding:16px;margin-bottom:16px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <h3 style="margin:0;color:#f3f4f6;">{case_name}</h3>
                    {status_badge}
                </div>
                <p style="color:#9ca3af;font-size:0.85rem;">Score: {res.get('total_score')} | Duration: {res.get('duration_ms')}ms</p>
                <table style="width:100%;border-collapse:collapse;margin-top:12px;font-size:0.9rem;color:#d1d5db;">
                    {metrics_rows}
                </table>
            </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>OpenHarness Report - {run_name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #111827; color: #f3f4f6; padding: 32px; max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #06b6d4; font-size: 1.8rem; margin-bottom: 8px; }}
        .summary {{ background: #1f2937; padding: 20px; border-radius: 12px; display: flex; gap: 24px; margin-bottom: 24px; }}
        .stat {{ font-size: 1.5rem; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>⚡ OpenHarness Evaluation Report</h1>
    <h2 style="color:#9ca3af;font-weight:normal;margin-top:0;">Run: {run_name}</h2>
    <div class="summary">
        <div>Pass Rate: <span class="stat" style="color:{'#10b981' if pass_rate == 100 else '#f59e0b'};">{pass_rate:.1f}%</span></div>
        <div>Passed: <span class="stat">{passed_cnt} / {total_cnt}</span></div>
        <div>Total Duration: <span class="stat">{run_detail.get('duration_ms', 0):.1f}ms</span></div>
    </div>
    <h2>Test Cases</h2>
    {cases_html}
</body>
</html>
"""
