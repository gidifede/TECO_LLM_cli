"""Generazione report HTML per la valutazione di coerenza dei test cases."""

from __future__ import annotations

import html
import json
from datetime import datetime


# Colori predefiniti per catena (background, border) — Chart.js
CHART_COLORS: dict[str, tuple[str, str]] = {
    "direct": ("rgba(22, 163, 74, 0.7)", "rgba(22, 163, 74, 1)"),
    "indirect_ac": ("rgba(37, 99, 235, 0.7)", "rgba(37, 99, 235, 1)"),
    "indirect_persona": ("rgba(168, 85, 247, 0.7)", "rgba(168, 85, 247, 1)"),
}


def _score_color(score: int | float) -> str:
    if score >= 80:
        return "#16a34a"  # green
    if score >= 50:
        return "#ca8a04"  # amber
    return "#dc2626"  # red


def _score_bg(score: int | float) -> str:
    if score >= 80:
        return "#dcfce7"
    if score >= 50:
        return "#fef9c3"
    return "#fee2e2"


def _esc(text: str) -> str:
    return html.escape(str(text))


def _render_ac_list(acceptance_criteria: list[str]) -> str:
    rows = ""
    for i, ac in enumerate(acceptance_criteria, 1):
        rows += f"<tr><td class='ac-num'>AC-{i}</td><td>{_esc(ac)}</td></tr>\n"
    return rows


def _render_tc_table(test_cases: list[dict], label: str) -> str:
    if not test_cases:
        return f"<p class='empty'>Nessun test case {_esc(label)}.</p>"
    rows = ""
    for tc in test_cases:
        tid = _esc(tc.get("test_id", "\u2014"))
        title = _esc(tc.get("title", "\u2014"))
        tc_type = _esc(tc.get("type", "\u2014"))
        priority = _esc(tc.get("priority", "\u2014"))
        traced = ", ".join(tc.get("traced_criteria", [])) or "\u2014"
        rows += (
            f"<tr>"
            f"<td class='mono'>{tid}</td>"
            f"<td>{title}</td>"
            f"<td>{tc_type}</td>"
            f"<td>{priority}</td>"
            f"<td>{_esc(traced)}</td>"
            f"</tr>\n"
        )
    return f"""
    <table class="data-table">
      <thead>
        <tr>
          <th>Test ID</th><th>Titolo</th><th>Tipo</th><th>Priorita</th><th>Criteri tracciati</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def _render_issues_table(
    items: list[dict], col1: str, key1: str, col2: str, key2: str
) -> str:
    if not items:
        return "<p class='empty'>Nessun elemento.</p>"
    rows = ""
    for item in items:
        v1 = _esc(item.get(key1, "\u2014"))
        v2 = _esc(item.get(key2, "\u2014"))
        rows += f"<tr><td class='mono'>{v1}</td><td>{v2}</td></tr>\n"
    return f"""
    <table class="data-table">
      <thead><tr><th>{_esc(col1)}</th><th>{_esc(col2)}</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def _render_redundancies_table(items: list[dict]) -> str:
    if not items:
        return "<p class='empty'>Nessuna ridondanza.</p>"
    rows = ""
    for item in items:
        ids = ", ".join(item.get("test_ids", []))
        detail = _esc(item.get("detail", "\u2014"))
        rows += f"<tr><td class='mono'>{_esc(ids)}</td><td>{detail}</td></tr>\n"
    return f"""
    <table class="data-table">
      <thead><tr><th>Test IDs</th><th>Dettaglio</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def _render_set_section(
    data: dict, label: str, is_winner: bool, total_ac: int
) -> str:
    score = data.get("coherence_score", 0)
    tc_count = data.get("tc_count", 0)
    ac_cov = data.get("ac_coverage", {})
    covered = ac_cov.get("covered_ac", 0)
    total = ac_cov.get("total_ac", total_ac)
    uncovered = ac_cov.get("uncovered_ac", [])
    added = data.get("added_info", [])
    missing = data.get("missing_info", [])
    redundancies = data.get("redundancies", [])

    cov_pct = (covered / total * 100) if total > 0 else 0
    winner_badge = (
        '<span class="winner-badge">&#9733; VINCITORE</span>' if is_winner else ""
    )

    uncovered_html = ""
    if uncovered:
        uncovered_items = "".join(f"<li>{_esc(ac)}</li>" for ac in uncovered)
        uncovered_html = (
            f'<div class="uncovered"><strong>AC non coperti:</strong>'
            f"<ul>{uncovered_items}</ul></div>"
        )

    return f"""
    <div class="set-section">
      <div class="set-header">
        <h2>{_esc(label)} {winner_badge}</h2>
        <div class="score-box" style="background:{_score_bg(score)};color:{_score_color(score)}">
          <div class="score-value">{score}</div>
          <div class="score-label">/ 100</div>
        </div>
      </div>

      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-num">{tc_count}</div>
          <div class="metric-label">Test Cases</div>
        </div>
        <div class="metric-card">
          <div class="metric-num">{covered}/{total}</div>
          <div class="metric-label">AC coperti</div>
        </div>
        <div class="metric-card">
          <div class="metric-num">{len(added)}</div>
          <div class="metric-label">Info aggiunte</div>
        </div>
        <div class="metric-card">
          <div class="metric-num">{len(missing)}</div>
          <div class="metric-label">Info mancanti</div>
        </div>
        <div class="metric-card">
          <div class="metric-num">{len(redundancies)}</div>
          <div class="metric-label">Ridondanze</div>
        </div>
      </div>

      <div class="progress-container">
        <div class="progress-label">Copertura AC: {covered}/{total} ({cov_pct:.0f}%)</div>
        <div class="progress-bar">
          <div class="progress-fill" style="width:{cov_pct}%"></div>
        </div>
      </div>
      {uncovered_html}

      <h3>Informazioni aggiunte</h3>
      {_render_issues_table(added, "Test ID", "test_id", "Dettaglio", "detail")}

      <h3>Informazioni mancanti</h3>
      {_render_issues_table(missing, "Fonte", "source", "Dettaglio", "detail")}

      <h3>Ridondanze</h3>
      {_render_redundancies_table(redundancies)}
    </div>"""


def generate_evaluation_html(
    evaluation: dict,
    requirement: dict,
    tc_sets: dict[str, list[dict]],
    chain_metadata: dict[str, dict],
    model: str = "",
) -> str:
    """Genera una pagina HTML completa con il report di valutazione.

    Parametri:
        evaluation: risultato della valutazione (JSON dal modello)
        requirement: requisito originale
        tc_sets: {"direct": [...], "indirect_ac": [...], ...} — TC inviati
        chain_metadata: {"direct": {"label": "...", "naming": "..."}, ...}
        model: nome del modello utilizzato
    """
    req_code = _esc(requirement.get("code", "UNKNOWN"))
    req_title = _esc(requirement.get("title", ""))
    req_desc = _esc(requirement.get("description", ""))
    req_cat = _esc(requirement.get("category", ""))
    req_priority = _esc(requirement.get("priority", ""))
    acceptance_criteria = requirement.get("acceptance_criteria", [])
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    total_ac = len(acceptance_criteria)

    # Dati comparison
    comparison = evaluation.get("comparison", {})
    winner = comparison.get("winner", "")
    ranking = comparison.get("ranking", [])
    reasoning = _esc(comparison.get("reasoning", ""))

    # --- Confronto: card dinamiche ---
    comparison_cards = ""
    for key in tc_sets:
        label = chain_metadata.get(key, {}).get("label", key)
        data = evaluation.get(key, {})
        score = data.get("coherence_score", 0)
        is_winner = key == winner
        # Posizione in classifica
        rank_pos = (ranking.index(key) + 1) if key in ranking else ""
        rank_badge = f"<div style='font-size:0.8rem;color:#64748b;margin-top:0.2rem'>#{rank_pos}</div>" if rank_pos else ""
        winner_class = "winner" if is_winner else ""
        winner_html = (
            "<div class='winner-badge' style='margin-top:0.5rem'>&#9733; VINCITORE</div>"
            if is_winner else ""
        )
        comparison_cards += f"""
    <div class="comparison-card {winner_class}">
      <div class="comparison-score" style="color:{_score_color(score)}">{score}</div>
      <div class="comparison-label">{_esc(label)}</div>
      {rank_badge}
      {winner_html}
    </div>"""

    # --- Sezioni set ---
    set_sections = ""
    for key in tc_sets:
        label = chain_metadata.get(key, {}).get("label", key)
        data = evaluation.get(key, {})
        is_winner = key == winner
        set_sections += _render_set_section(data, label, is_winner, total_ac)

    # --- Blocchi details per dati di input ---
    input_details = ""
    for key, tc_list in tc_sets.items():
        label = chain_metadata.get(key, {}).get("label", key)
        tc_table = _render_tc_table(tc_list, label)
        input_details += f"""
  <details>
    <summary>{_esc(label)} &mdash; {len(tc_list)} TC inviati</summary>
    {tc_table}
  </details>"""

    # JSON del requisito pre-computato
    req_json_pretty = _esc(json.dumps(
        {
            "code": requirement.get("code", ""),
            "title": requirement.get("title", ""),
            "description": requirement.get("description", ""),
            "category": requirement.get("category", ""),
            "priority": requirement.get("priority", ""),
            "acceptance_criteria": requirement.get("acceptance_criteria", []),
        },
        indent=2,
        ensure_ascii=False,
    ))

    # --- Chart.js: dataset dinamici ---
    chart_labels = ["AC coperti", "Info aggiunte", "Info mancanti", "Ridondanze"]
    chart_datasets: list[dict] = []
    for key in tc_sets:
        label = chain_metadata.get(key, {}).get("label", key)
        data = evaluation.get(key, {})
        bg, border = CHART_COLORS.get(key, ("rgba(100,100,100,0.7)", "rgba(100,100,100,1)"))
        chart_datasets.append({
            "label": label,
            "data": [
                data.get("ac_coverage", {}).get("covered_ac", 0),
                len(data.get("added_info", [])),
                len(data.get("missing_info", [])),
                len(data.get("redundancies", [])),
            ],
            "backgroundColor": bg,
            "borderColor": border,
            "borderWidth": 1,
        })

    chart_data_json = json.dumps(
        {"labels": chart_labels, "datasets": chart_datasets},
        ensure_ascii=False,
    )

    # Griglia confronto: auto-fit per N card
    grid_cols = f"repeat({len(tc_sets)}, 1fr)"

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Valutazione coerenza &mdash; {req_code}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    background: #f8fafc; color: #1e293b; line-height: 1.6;
    padding: 2rem; max-width: 1200px; margin: 0 auto;
  }}
  .header {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
    color: white; padding: 2rem; border-radius: 12px; margin-bottom: 2rem;
  }}
  .header h1 {{ font-size: 1.8rem; margin-bottom: 0.3rem; }}
  .header .subtitle {{ opacity: 0.85; font-size: 1.1rem; }}
  .header .meta {{ margin-top: 1rem; font-size: 0.85rem; opacity: 0.7; }}
  .header .meta span {{ margin-right: 1.5rem; }}

  .section {{ background: white; border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .section h2 {{ font-size: 1.3rem; margin-bottom: 1rem; color: #1e3a5f;
    border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }}
  .section h3 {{ font-size: 1.05rem; margin: 1.2rem 0 0.6rem; color: #475569; }}

  .req-field {{ margin-bottom: 0.6rem; }}
  .req-field strong {{ color: #475569; min-width: 100px; display: inline-block; }}
  .req-desc {{ background: #f1f5f9; padding: 1rem; border-radius: 6px;
    margin: 0.8rem 0; border-left: 4px solid #2563eb; }}

  table.ac-table {{ width: 100%; border-collapse: collapse; margin: 0.8rem 0; }}
  table.ac-table td {{ padding: 0.5rem; border-bottom: 1px solid #e2e8f0; }}
  .ac-num {{ font-weight: 600; color: #2563eb; width: 60px; white-space: nowrap; }}

  /* Confronto */
  .comparison-grid {{ display: grid; grid-template-columns: {grid_cols}; gap: 1.5rem; margin: 1rem 0; }}
  .comparison-card {{
    text-align: center; padding: 1.5rem; border-radius: 10px;
    border: 2px solid #e2e8f0; position: relative;
  }}
  .comparison-card.winner {{ border-color: #16a34a; background: #f0fdf4; }}
  .comparison-score {{ font-size: 3rem; font-weight: 800; }}
  .comparison-label {{ font-size: 0.9rem; color: #64748b; margin-top: 0.3rem; }}
  .winner-badge {{
    display: inline-block; background: #16a34a; color: white; font-size: 0.75rem;
    padding: 0.2rem 0.6rem; border-radius: 20px; vertical-align: middle; margin-left: 0.5rem;
  }}
  .reasoning {{ background: #f1f5f9; padding: 1rem; border-radius: 6px;
    margin-top: 1rem; font-style: italic; color: #475569; }}

  /* Set sections */
  .set-section {{ background: white; border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .set-header {{ display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.8rem; }}
  .set-header h2 {{ border: none; padding: 0; margin: 0; }}
  .score-box {{
    text-align: center; padding: 0.8rem 1.5rem; border-radius: 10px; min-width: 100px;
  }}
  .score-value {{ font-size: 2.2rem; font-weight: 800; line-height: 1; }}
  .score-label {{ font-size: 0.8rem; opacity: 0.7; }}

  .metrics-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.8rem; margin: 1rem 0; }}
  .metric-card {{
    text-align: center; padding: 0.8rem; background: #f8fafc;
    border-radius: 8px; border: 1px solid #e2e8f0;
  }}
  .metric-num {{ font-size: 1.5rem; font-weight: 700; color: #1e3a5f; }}
  .metric-label {{ font-size: 0.75rem; color: #64748b; margin-top: 0.2rem; }}

  .progress-container {{ margin: 1rem 0; }}
  .progress-label {{ font-size: 0.85rem; color: #475569; margin-bottom: 0.3rem; }}
  .progress-bar {{ background: #e2e8f0; border-radius: 8px; height: 12px; overflow: hidden; }}
  .progress-fill {{ background: #2563eb; height: 100%; border-radius: 8px;
    transition: width 0.5s ease; }}

  .uncovered {{ background: #fef2f2; padding: 0.8rem 1rem; border-radius: 6px;
    margin: 0.8rem 0; border-left: 4px solid #dc2626; }}
  .uncovered ul {{ margin: 0.5rem 0 0 1.2rem; }}
  .uncovered li {{ font-size: 0.9rem; color: #7f1d1d; }}

  /* Tabelle dati */
  table.data-table {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0; font-size: 0.9rem; }}
  table.data-table th {{
    background: #f1f5f9; padding: 0.6rem 0.8rem; text-align: left;
    font-weight: 600; color: #475569; border-bottom: 2px solid #e2e8f0;
  }}
  table.data-table td {{ padding: 0.5rem 0.8rem; border-bottom: 1px solid #f1f5f9; }}
  table.data-table tr:hover td {{ background: #f8fafc; }}
  .mono {{ font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 0.8rem; white-space: nowrap; }}

  .empty {{ color: #94a3b8; font-style: italic; padding: 0.5rem 0; }}

  /* Chart */
  .chart-container {{ max-width: 600px; margin: 1.5rem auto; }}

  /* Input data */
  .input-section {{ background: #fffbeb; border: 1px solid #fde68a; }}
  .input-section h2 {{ color: #92400e; border-color: #fde68a; }}

  /* Collapsible */
  details {{ margin: 0.5rem 0; }}
  details summary {{
    cursor: pointer; font-weight: 600; color: #2563eb; padding: 0.5rem 0;
    user-select: none;
  }}
  details summary:hover {{ color: #1d4ed8; }}

  @media (max-width: 768px) {{
    body {{ padding: 1rem; }}
    .comparison-grid {{ grid-template-columns: 1fr; }}
    .metrics-grid {{ grid-template-columns: repeat(3, 1fr); }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>Valutazione coerenza &mdash; {req_code}</h1>
  <div class="subtitle">{req_title}</div>
  <div class="meta">
    <span>Data: {now}</span>
    <span>Modello: {_esc(model) if model else "N/A"}</span>
    <span>Set valutati: {len(tc_sets)}</span>
  </div>
</div>

<!-- Requisito -->
<div class="section">
  <h2>Requisito</h2>
  <div class="req-field"><strong>Codice:</strong> {req_code}</div>
  <div class="req-field"><strong>Titolo:</strong> {req_title}</div>
  <div class="req-field"><strong>Categoria:</strong> {req_cat}</div>
  <div class="req-field"><strong>Priorita:</strong> {req_priority}</div>
  <div class="req-desc">{req_desc}</div>
  <h3>Acceptance Criteria</h3>
  <table class="ac-table">
    {_render_ac_list(acceptance_criteria)}
  </table>
</div>

<!-- Confronto -->
<div class="section">
  <h2>Confronto</h2>
  <div class="comparison-grid">
    {comparison_cards}
  </div>
  <div class="reasoning"><strong>Motivazione:</strong> {reasoning}</div>

  <div class="chart-container">
    <canvas id="comparisonChart"></canvas>
  </div>
</div>

<!-- Sezioni set -->
{set_sections}

<!-- Dati di input inviati al modello -->
<div class="section input-section">
  <h2>Dati di input inviati al modello</h2>
  <p style="color:#92400e;font-size:0.9rem;margin-bottom:1rem;">
    Questi sono i dati esatti sottomessi al modello per la valutazione di coerenza.
  </p>

  <details>
    <summary>Requisito originale (JSON)</summary>
    <pre style="background:#fef3c7;padding:1rem;border-radius:6px;overflow-x:auto;font-size:0.8rem;margin-top:0.5rem">{req_json_pretty}</pre>
  </details>

  {input_details}
</div>

<script>
const chartData = {chart_data_json};
new Chart(document.getElementById('comparisonChart'), {{
  type: 'bar',
  data: {{
    labels: chartData.labels,
    datasets: chartData.datasets,
  }},
  options: {{
    responsive: true,
    plugins: {{
      title: {{
        display: true,
        text: 'Confronto metriche',
        font: {{ size: 14 }},
      }},
      legend: {{ position: 'bottom' }},
    }},
    scales: {{
      y: {{
        beginAtZero: true,
        ticks: {{ stepSize: 1 }},
      }},
    }},
  }},
}});
</script>

</body>
</html>"""
