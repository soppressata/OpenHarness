"""
App module for OpenHarness.
Provides core functionality for the app subsystem.
"""
import os
import json
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from openharness.core.storage import StorageEngine
from openharness.core.exporters import export_to_json, export_to_html, export_to_junit_xml
from openharness.core.analytics import calculate_trajectory_cost, calculate_latency_breakdown
from openharness.core.types import Trajectory


def create_app(db_path: Optional[str] = None) -> FastAPI:
    db_file = db_path or os.environ.get("OPENHARNESS_DB", ".openharness/evals.db")
    storage = StorageEngine(db_path=db_file)

    app = FastAPI(title="OpenHarness Dashboard API", version="0.1.0")

    @app.get("/api/runs")
    def list_runs(limit: int = 50):
        return storage.get_runs(limit=limit)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        details = storage.get_run_details(run_id)
        if not details:
            raise HTTPException(status_code=404, detail="Run not found")
        return details

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str):
        details = storage.get_run_details(run_id)
        if not details:
            raise HTTPException(status_code=404, detail="Run not found")
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM metric_scores WHERE evaluation_result_id IN (SELECT id FROM evaluation_results WHERE run_id = ?)", (run_id,))
            cursor.execute("DELETE FROM evaluation_results WHERE run_id = ?", (run_id,))
            cursor.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()
        return {"status": "success", "deleted_run_id": run_id}

    @app.get("/api/runs/{run_id}/export")
    def export_run(run_id: str, format: str = Query("json", regex="^(json|html|junit)$")):
        details = storage.get_run_details(run_id)
        if not details:
            raise HTTPException(status_code=404, detail="Run not found")
        
        if format == "json":
            return Response(content=export_to_json(details), media_type="application/json")
        elif format == "html":
            return Response(content=export_to_html(details), media_type="text/html")
        elif format == "junit":
            return Response(content=export_to_junit_xml(details), media_type="application/xml")

    @app.get("/api/runs/{run_id}/analytics")
    def get_run_analytics(run_id: str):
        details = storage.get_run_details(run_id)
        if not details:
            raise HTTPException(status_code=404, detail="Run not found")

        analytics_results = []
        for res in details.get("results", []):
            if res.get("trajectory"):
                traj = Trajectory(**res["trajectory"])
                cost = calculate_trajectory_cost(traj).model_dump()
                latency = calculate_latency_breakdown(traj).model_dump()
                analytics_results.append({
                    "test_case_name": res["test_case_name"],
                    "cost": cost,
                    "latency": latency
                })
        return {"run_id": run_id, "analytics": analytics_results}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTML_DASHBOARD_TEMPLATE

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})

    return app


HTML_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenHarness - Agentic Evaluator Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0b0f19;
            --bg-card: #131b2e;
            --bg-card-hover: #1c2744;
            --accent-cyan: #06b6d4;
            --accent-purple: #8b5cf6;
            --accent-pink: #ec4899;
            --success-green: #10b981;
            --error-red: #ef4444;
            --warning-amber: #f59e0b;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --border-color: rgba(255, 255, 255, 0.08);
            --glass-bg: rgba(19, 27, 46, 0.7);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        header {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.4rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .badge {
            background: rgba(6, 182, 212, 0.15);
            border: 1px solid var(--accent-cyan);
            color: var(--accent-cyan);
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        main {
            padding: 32px;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 24px;
            flex: 1;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }

        h2 {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 16px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .run-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-height: calc(100vh - 160px);
            overflow-y: auto;
        }

        .run-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .run-item:hover, .run-item.active {
            background: var(--bg-card-hover);
            border-color: var(--accent-purple);
            transform: translateY(-2px);
        }

        .run-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }

        .run-title { font-weight: 600; font-size: 1rem; }

        .pass-tag {
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
        }

        .pass-tag.success { background: rgba(16, 185, 129, 0.2); color: var(--success-green); }
        .pass-tag.fail { background: rgba(239, 68, 68, 0.2); color: var(--error-red); }

        .run-meta {
            font-size: 0.8rem;
            color: var(--text-secondary);
            display: flex;
            gap: 12px;
        }

        .details-panel { display: flex; flex-direction: column; gap: 24px; }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .stat-val {
            font-size: 1.8rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff, var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .case-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }

        .metrics-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }

        .metric-pill {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .metric-pill.passed { border-color: rgba(16, 185, 129, 0.4); }
        .metric-pill.failed { border-color: rgba(239, 68, 68, 0.4); }

        .trajectory-view {
            margin-top: 16px;
            background: #080c14;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            overflow-x: auto;
        }

        .step-block {
            border-left: 2px solid var(--accent-purple);
            padding-left: 12px;
            margin-bottom: 12px;
        }

        .tool-call-tag { color: var(--accent-cyan); font-weight: 600; }
        .empty-state { text-align: center; padding: 60px; color: var(--text-secondary); }
    </style>
</head>
<body>
    <header>
        <div class="logo">
            ⚡ OpenHarness
            <span class="badge">AGENTIC EVALUATOR</span>
        </div>
        <div style="font-size: 0.9rem; color: var(--text-secondary);">
            Local-First & Zero Cost
        </div>
    </header>

    <main>
        <div class="card">
            <h2>Evaluation Runs</h2>
            <div id="run-list" class="run-list">
                <div class="empty-state">Loading runs...</div>
            </div>
        </div>

        <div class="details-panel">
            <div class="card">
                <h2>Run Overview</h2>
                <div class="stats-grid" id="stats-grid">
                    <div class="stat-card">
                        <span style="font-size: 0.8rem; color: var(--text-secondary);">Pass Rate</span>
                        <span class="stat-val" id="stat-pass-rate">--%</span>
                    </div>
                    <div class="stat-card">
                        <span style="font-size: 0.8rem; color: var(--text-secondary);">Total Cases</span>
                        <span class="stat-val" id="stat-total-cases">--</span>
                    </div>
                    <div class="stat-card">
                        <span style="font-size: 0.8rem; color: var(--text-secondary);">Avg Duration</span>
                        <span class="stat-val" id="stat-avg-duration">--ms</span>
                    </div>
                    <div class="stat-card">
                        <span style="font-size: 0.8rem; color: var(--text-secondary);">Avg Score</span>
                        <span class="stat-val" id="stat-avg-score">--</span>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2>Test Cases & Trajectory Details</h2>
                <div id="cases-container">
                    <div class="empty-state">Select a run from the left panel to inspect evaluation details.</div>
                </div>
            </div>
        </div>
    </main>

    <script>
        async function fetchRuns() {
            try {
                const res = await fetch('/api/runs');
                const runs = await res.json();
                renderRunList(runs);
                if (runs.length > 0) {
                    selectRun(runs[0].id);
                } else {
                    document.getElementById('run-list').innerHTML = '<div class="empty-state">No evaluation runs recorded yet.<br><br>Run <code>harness init</code> or execute an eval script!</div>';
                }
            } catch (err) {
                console.error("Failed to fetch runs:", err);
            }
        }

        function renderRunList(runs) {
            const container = document.getElementById('run-list');
            container.innerHTML = runs.map(run => {
                const passRate = run.total_count > 0 ? ((run.passed_count / run.total_count) * 100).toFixed(0) : 0;
                const isPass = passRate == 100;
                const dateStr = new Date(run.timestamp * 1000).toLocaleTimeString();
                return `
                    <div class="run-item" onclick="selectRun('${run.id}')" id="run-item-${run.id}">
                        <div class="run-header">
                            <span class="run-title">${run.name}</span>
                            <span class="pass-tag ${isPass ? 'success' : 'fail'}">${passRate}% PASS</span>
                        </div>
                        <div class="run-meta">
                            <span>ID: ${run.id}</span>
                            <span>⏱ ${run.duration_ms.toFixed(1)}ms</span>
                            <span>🕒 ${dateStr}</span>
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function selectRun(runId) {
            document.querySelectorAll('.run-item').forEach(el => el.classList.remove('active'));
            const activeEl = document.getElementById(`run-item-${runId}`);
            if (activeEl) activeEl.classList.add('active');

            try {
                const res = await fetch(`/api/runs/${runId}`);
                const run = await res.json();
                renderRunDetails(run);
            } catch (err) {
                console.error("Failed to fetch run details:", err);
            }
        }

        function renderRunDetails(run) {
            const total = run.results.length;
            const passed = run.results.filter(r => r.passed).length;
            const passRate = total > 0 ? ((passed / total) * 100).toFixed(1) : 0;
            const avgDuration = total > 0 ? (run.results.reduce((acc, r) => acc + r.duration_ms, 0) / total).toFixed(1) : 0;
            const avgScore = total > 0 ? (run.results.reduce((acc, r) => acc + r.total_score, 0) / total).toFixed(2) : 0;

            document.getElementById('stat-pass-rate').innerText = `${passRate}%`;
            document.getElementById('stat-total-cases').innerText = total;
            document.getElementById('stat-avg-duration').innerText = `${avgDuration}ms`;
            document.getElementById('stat-avg-score').innerText = avgScore;

            const casesContainer = document.getElementById('cases-container');
            casesContainer.innerHTML = run.results.map(res => {
                const metricsHtml = res.metrics.map(m => `
                    <div class="metric-pill ${m.passed ? 'passed' : 'failed'}">
                        <span>${m.passed ? '✔' : '✖'}</span>
                        <strong style="color: var(--text-primary);">${m.name}:</strong>
                        <span>${m.reason}</span>
                    </div>
                `).join('');

                let trajHtml = '';
                if (res.trajectory) {
                    const steps = res.trajectory.steps || [];
                    trajHtml = `
                        <div class="trajectory-view">
                            <div style="color: var(--accent-cyan); margin-bottom: 8px;">📥 Prompt: "${res.trajectory.input_prompt}"</div>
                            ${steps.map(s => `
                                <div class="step-block">
                                    <span style="color: var(--accent-purple);">Step ${s.step_index} [${s.step_type}]</span>
                                    <div>${s.content}</div>
                                    ${(s.tool_calls || []).map(tc => `
                                        <div class="tool-call-tag">🛠 Tool Call: ${tc.name}(${JSON.stringify(tc.args)})</div>
                                        ${tc.result ? `<div style="color: #6b7280;">  └─ Result: ${JSON.stringify(tc.result)}</div>` : ''}
                                        ${tc.error ? `<div style="color: var(--error-red);">  └─ Error: ${tc.error}</div>` : ''}
                                    `).join('')}
                                </div>
                            `).join('')}
                            <div style="color: var(--success-green); margin-top: 8px;">📤 Final Output: "${res.trajectory.final_output}"</div>
                        </div>
                    `;
                }

                return `
                    <div class="case-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <h3 style="font-size: 1.05rem;">${res.test_case_name}</h3>
                            <span class="pass-tag ${res.passed ? 'success' : 'fail'}">${res.passed ? 'PASSED' : 'FAILED'}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">
                            Score: ${res.total_score} | Duration: ${res.duration_ms.toFixed(1)}ms
                        </div>
                        <div class="metrics-list">
                            ${metricsHtml}
                        </div>
                        ${trajHtml}
                    </div>
                `;
            }).join('');
        }

        fetchRuns();
    </script>
</body>
</html>
"""
