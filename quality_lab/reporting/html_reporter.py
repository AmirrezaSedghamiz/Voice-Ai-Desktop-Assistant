"""
Quality Lab Standalone HTML Report Generator.
Produces a self-contained, offline-compatible HTML dashboard displaying test results,
performance percentiles, AI evaluation breakdowns, security gates, and release status.
"""

from __future__ import annotations

import html
from pathlib import Path
from quality_lab.models import RunSummary, TestStatus


def generate_html_report(summary: RunSummary, output_path: Path) -> Path:
    """Generates an offline-compatible HTML report document."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    status_color = "#10b981" if summary.release_gate_passed else "#ef4444"
    gate_badge = "RELEASE GATE PASSED" if summary.release_gate_passed else "RELEASE GATE BLOCKED"

    # Count breakdown
    pass_pct = round((summary.passed / summary.total_tests) * 100.0, 1) if summary.total_tests > 0 else 0.0

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Quality Lab Report - {html.escape(summary.run_id)}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --pass: #10b981;
      --fail: #ef4444;
      --warn: #f59e0b;
      --inconcl: #6b7280;
      --primary: #38bdf8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 2rem; line-height: 1.5; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; margin-bottom: 2rem; }}
    .title h1 {{ font-size: 1.8rem; font-weight: 700; color: #fff; }}
    .title p {{ color: var(--text-muted); font-size: 0.9rem; margin-top: 0.25rem; }}
    .gate-badge {{ background: {status_color}; color: #fff; padding: 0.5rem 1.25rem; border-radius: 9999px; font-weight: 700; font-size: 0.9rem; letter-spacing: 0.05em; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
    .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.25rem; }}
    .card-title {{ font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
    .card-value {{ font-size: 1.8rem; font-weight: 700; margin-top: 0.5rem; }}
    .section-title {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; color: #e2e8f0; }}
    .box-blocker {{ background: rgba(239, 68, 68, 0.15); border: 1px solid var(--fail); border-radius: 0.5rem; padding: 1rem; margin-bottom: 1.5rem; }}
    .box-blocker h3 {{ color: var(--fail); font-size: 1rem; margin-bottom: 0.5rem; }}
    .box-blocker ul {{ list-style-position: inside; color: #fca5a5; font-size: 0.9rem; }}
    .box-warn {{ background: rgba(245, 158, 11, 0.15); border: 1px solid var(--warn); border-radius: 0.5rem; padding: 1rem; margin-bottom: 1.5rem; }}
    .box-warn h3 {{ color: var(--warn); font-size: 1rem; margin-bottom: 0.5rem; }}
    .box-warn ul {{ list-style-position: inside; color: #fde68a; font-size: 0.9rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; background: var(--card-bg); border-radius: 0.75rem; overflow: hidden; border: 1px solid var(--border); }}
    th, td {{ padding: 0.85rem 1rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
    th {{ background: #0f172a; color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; }}
    tr:last-child td {{ border-bottom: none; }}
    .badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }}
    .badge-passed {{ background: rgba(16, 185, 129, 0.2); color: var(--pass); }}
    .badge-failed {{ background: rgba(239, 68, 68, 0.2); color: var(--fail); }}
    .badge-error {{ background: rgba(239, 68, 68, 0.2); color: var(--fail); }}
    .badge-skipped {{ background: rgba(107, 114, 128, 0.2); color: var(--inconcl); }}
    .badge-inconclusive {{ background: rgba(245, 158, 11, 0.2); color: var(--warn); }}
    .diagnostic {{ font-family: monospace; font-size: 0.8rem; color: #cbd5e1; word-break: break-all; margin-top: 0.25rem; }}
    .telemetry-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 2rem; }}
    .footer {{ text-align: center; color: var(--text-muted); font-size: 0.8rem; margin-top: 2rem; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title">
        <h1>Quality Lab Report</h1>
        <p>Run ID: <strong>{html.escape(summary.run_id)}</strong> | Timestamp: {html.escape(summary.timestamp)}</p>
      </div>
      <div class="gate-badge">{gate_badge}</div>
    </div>

    <!-- Summary Metrics -->
    <div class="grid">
      <div class="card">
        <div class="card-title">Total Tests</div>
        <div class="card-value">{summary.total_tests}</div>
      </div>
      <div class="card">
        <div class="card-title">Passed ({pass_pct}%)</div>
        <div class="card-value" style="color: var(--pass);">{summary.passed}</div>
      </div>
      <div class="card">
        <div class="card-title">Failed</div>
        <div class="card-value" style="color: var(--fail);">{summary.failed}</div>
      </div>
      <div class="card">
        <div class="card-title">Inconclusive</div>
        <div class="card-value" style="color: var(--warn);">{summary.inconclusive}</div>
      </div>
      <div class="card">
        <div class="card-title">Total Duration</div>
        <div class="card-value">{summary.duration_seconds:.2f}s</div>
      </div>
    </div>
"""

    if summary.blockers:
        html_content += f"""
    <div class="box-blocker">
      <h3>Release Blockers ({len(summary.blockers)})</h3>
      <ul>
        {''.join(f'<li>{html.escape(b)}</li>' for b in summary.blockers)}
      </ul>
    </div>
"""

    if summary.warnings:
        html_content += f"""
    <div class="box-warn">
      <h3>Release Warnings ({len(summary.warnings)})</h3>
      <ul>
        {''.join(f'<li>{html.escape(w)}</li>' for w in summary.warnings)}
      </ul>
    </div>
"""

    # Environment Telemetry
    env = summary.environment_telemetry
    if env:
        html_content += f"""
    <div class="section-title">Environment & Hardware Inventory</div>
    <div class="card" style="margin-bottom: 2rem;">
      <p><strong>OS:</strong> {html.escape(str(env.get('os_system', '')))} {html.escape(str(env.get('os_release', '')))} ({html.escape(str(env.get('architecture', '')))}) | <strong>Cores:</strong> {env.get('cpu_count_physical')} physical, {env.get('cpu_count_logical')} logical | <strong>RAM:</strong> {env.get('total_ram_gb')} GB</p>
      <p style="margin-top: 0.25rem;"><strong>GPU:</strong> {html.escape(str(env.get('gpu_name', 'None detected')))} | <strong>VRAM:</strong> {env.get('gpu_vram_total_mb', 0)} MB | <strong>Driver:</strong> {html.escape(str(env.get('gpu_driver_version', 'N/A')))}</p>
      <p style="margin-top: 0.25rem;"><strong>Audio:</strong> {env.get('input_device_count', 0)} Inputs, {env.get('output_device_count', 0)} Outputs</p>
    </div>
"""

    # Suite Summary Table
    html_content += """
    <div class="section-title">Suite Execution Overview</div>
    <table>
      <thead>
        <tr>
          <th>Suite</th>
          <th>Status</th>
          <th>Total</th>
          <th>Passed</th>
          <th>Failed</th>
          <th>Inconclusive</th>
          <th>Duration</th>
        </tr>
      </thead>
      <tbody>
"""
    for s_name, s_res in summary.suites.items():
        badge_class = f"badge-{s_res.status.value}"
        html_content += f"""
        <tr>
          <td><strong>{html.escape(s_name)}</strong></td>
          <td><span class="badge {badge_class}">{s_res.status.value}</span></td>
          <td>{s_res.total}</td>
          <td style="color: var(--pass); font-weight: 600;">{s_res.passed}</td>
          <td style="color: var(--fail); font-weight: 600;">{s_res.failed}</td>
          <td style="color: var(--warn); font-weight: 600;">{s_res.inconclusive}</td>
          <td>{s_res.duration_seconds:.2f}s</td>
        </tr>
"""
    html_content += """
      </tbody>
    </table>
"""

    # Detailed Test Cases
    html_content += """
    <div class="section-title">Individual Test Outcomes</div>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Suite</th>
          <th>Name</th>
          <th>Status</th>
          <th>Duration</th>
          <th>Diagnostic Details</th>
        </tr>
      </thead>
      <tbody>
"""
    for s_name, s_res in summary.suites.items():
        for r in s_res.results:
            badge_class = f"badge-{r.status.value}"
            diag_text = r.diagnostic_message or r.observed_outcome
            html_content += f"""
        <tr>
          <td><code>{html.escape(r.test_id)}</code></td>
          <td>{html.escape(s_name)}</td>
          <td>{html.escape(r.name)}</td>
          <td><span class="badge {badge_class}">{r.status.value}</span></td>
          <td>{r.duration_seconds:.3f}s</td>
          <td><div class="diagnostic">{html.escape(diag_text[:200])}</div></td>
        </tr>
"""
    html_content += f"""
      </tbody>
    </table>
    <div class="footer">
      Generated locally by David Quality Lab v1.0.0 &bull; 100% Offline &bull; Zero External Network Transmissions
    </div>
  </div>
</body>
</html>
"""

    output_path.write_text(html_content, encoding="utf-8")
    return output_path
