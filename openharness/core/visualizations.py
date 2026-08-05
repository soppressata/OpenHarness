import html
from typing import Dict, Any, List, Optional
from openharness.core.types import Trajectory, EvaluationResult


def render_ascii_waterfall(trajectory: Trajectory, width: int = 50) -> str:
    """Render an ASCII Waterfall Gantt chart for terminal output."""
    steps = trajectory.steps
    if not steps:
        return "No trajectory steps recorded."

    total_duration = trajectory.total_duration_ms or sum(s.duration_ms for s in steps) or 1.0
    lines = [f"📊 WATERFALL TIMELINE (Total: {total_duration:.1f}ms)"]
    lines.append("-" * (width + 25))

    accumulated = 0.0
    for step in steps:
        start_ratio = accumulated / total_duration
        dur_ratio = (step.duration_ms or 1.0) / total_duration
        
        start_pad = int(start_ratio * width)
        bar_len = max(1, int(dur_ratio * width))
        
        bar = " " * start_pad + "█" * bar_len + " " * max(0, width - start_pad - bar_len)
        tool_names = ", ".join(tc.name for tc in step.tool_calls) if step.tool_calls else step.step_type
        
        lines.append(f"Step {step.step_index:2d} |{bar}| {step.duration_ms:6.1f}ms [{tool_names}]")
        accumulated += step.duration_ms

    lines.append("-" * (width + 25))
    return "\n".join(lines)


def render_ascii_scorecard(results: List[EvaluationResult]) -> str:
    """Render an ASCII Heatmap Matrix Scorecard for evaluation results."""
    if not results:
        return "No evaluation results available."

    lines = ["📋 EVALUATION SCORECARD MATRIX"]
    lines.append("=" * 65)
    lines.append(f"{'TEST CASE':<30} | {'SCORE':<7} | {'STATUS':<8} | {'METRICS PASSED'}")
    lines.append("-" * 65)

    for res in results:
        status_str = "PASS ✅" if res.passed else "FAIL ❌"
        passed_m = sum(1 for m in res.metrics if m.passed)
        total_m = len(res.metrics)
        m_str = f"{passed_m}/{total_m}"
        lines.append(f"{res.test_case_name[:30]:<30} | {res.total_score:7.2f} | {status_str:<8} | {m_str}")

    lines.append("=" * 65)
    return "\n".join(lines)


def render_ascii_quality_radar(results: List[EvaluationResult]) -> str:
    """Render an ASCII Quality vs Latency Breakdown Table for terminal output."""
    if not results:
        return "No quality metrics available."

    lines = ["🎯 QUALITY VS LATENCY PARETO MATRIX"]
    lines.append("=" * 70)
    lines.append(f"{'TEST CASE':<28} | {'QUALITY':<8} | {'LATENCY':<9} | {'PARETO EFFICIENCY'}")
    lines.append("-" * 70)

    for res in results:
        quality_metrics = [m for m in res.metrics if m.category in ["quality", "assertion", "llm_judge"]]
        avg_quality = (sum(m.score for m in quality_metrics) / len(quality_metrics)) if quality_metrics else res.total_score
        
        latency_str = f"{res.duration_ms:.1f}ms"
        
        # Pareto efficiency: High Quality (>0.8) regardless of latency is EXCELLENT
        if avg_quality >= 0.9:
            pareto_str = "OPTIMAL (High Quality)"
        elif avg_quality >= 0.7:
            pareto_str = "BALANCED"
        else:
            pareto_str = "SUBOPTIMAL (Low Quality)"

        lines.append(f"{res.test_case_name[:28]:<28} | {avg_quality:8.2f} | {latency_str:<9} | {pareto_str}")

    lines.append("=" * 70)
    return "\n".join(lines)


def render_svg_waterfall(trajectory: Trajectory) -> str:
    """Generate a self-contained SVG Waterfall Gantt chart."""
    steps = trajectory.steps
    if not steps:
        return "<svg><text>No steps</text></svg>"

    total_duration = trajectory.total_duration_ms or sum(s.duration_ms for s in steps) or 1.0
    row_height = 36
    header_height = 40
    width = 700
    height = header_height + (len(steps) * row_height) + 20

    svg_rows = []
    accumulated = 0.0

    for i, step in enumerate(steps):
        y = header_height + (i * row_height)
        start_x = 180 + (accumulated / total_duration * 480)
        bar_width = max(4, (step.duration_ms / total_duration * 480))
        
        color = "#06b6d4" if step.tool_calls else "#8b5cf6"
        label = html.escape(f"Step {step.step_index}: {step.step_type}")
        
        svg_rows.append(f"""
            <text x="10" y="{y + 20}" fill="#9ca3af" font-size="12">{label}</text>
            <rect x="{start_x:.1f}" y="{y + 6}" width="{bar_width:.1f}" height="20" rx="4" fill="{color}" opacity="0.85"/>
            <text x="{start_x + bar_width + 8:.1f}" y="{y + 20}" fill="#f3f4f6" font-size="11">{step.duration_ms:.1f}ms</text>
        """)
        accumulated += step.duration_ms

    return f"""<svg width="{width}" height="{height}" style="background:#0b0f19;font-family:sans-serif;">
        <text x="10" y="24" fill="#06b6d4" font-size="14" font-weight="bold">Waterfall Timeline (Total: {total_duration:.1f}ms)</text>
        <line x1="180" y1="35" x2="660" y2="35" stroke="#374151" stroke-width="1"/>
        {"".join(svg_rows)}
    </svg>"""


def render_pairwise_diff_html(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> str:
    """Render side-by-side pairwise diff visualizer (Agent A vs Agent B)."""
    name_a = html.escape(run_a.get("name", "Agent A"))
    name_b = html.escape(run_b.get("name", "Agent B"))
    pass_a = run_a.get("passed_count", 0)
    pass_b = run_b.get("passed_count", 0)

    return f"""
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;background:#131b2e;padding:24px;border-radius:12px;color:#f3f4f6;">
        <div style="border-right:1px solid rgba(255,255,255,0.1);padding-right:16px;">
            <h3 style="color:#06b6d4;">🔵 {name_a}</h3>
            <p style="color:#9ca3af;">Passes: {pass_a} / {run_a.get('total_count', 0)} | Duration: {run_a.get('duration_ms', 0):.1f}ms</p>
        </div>
        <div style="padding-left:16px;">
            <h3 style="color:#ec4899;">🔴 {name_b}</h3>
            <p style="color:#9ca3af;">Passes: {pass_b} / {run_b.get('total_count', 0)} | Duration: {run_b.get('duration_ms', 0):.1f}ms</p>
        </div>
    </div>
    """
