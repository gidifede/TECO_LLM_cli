"""Generazione HTML per il confronto affiancato di due valutazioni."""

import json
from datetime import datetime
from pathlib import Path


def _safe(val, default=0):
    """Restituisce il valore numerico oppure un default."""
    if isinstance(val, (int, float)):
        return val
    return default


def _delta_str(a: float, b: float) -> str:
    """Restituisce la stringa delta con segno (es. '+0.4' / '-0.4')."""
    d = a - b
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.1f}"


def _winner_class(a: float, b: float) -> tuple[str, str]:
    """Restituisce (classe CSS per A, classe CSS per B)."""
    if a > b:
        return "winner", "loser"
    if b > a:
        return "loser", "winner"
    return "tie", "tie"


def generate_comparison_html(
    eval_a: dict,
    eval_b: dict,
    label_a: str,
    label_b: str,
    output_path: Path,
) -> Path:
    """Genera un file HTML standalone con il confronto tra due valutazioni.

    Args:
        eval_a: JSON completo della valutazione A.
        eval_b: JSON completo della valutazione B.
        label_a: Etichetta descrittiva per A.
        label_b: Etichetta descrittiva per B.
        output_path: Path dove salvare l'HTML.

    Returns:
        Il Path del file HTML salvato.
    """
    # --- Estrai dati ---
    overall_a = _safe(eval_a.get("overall_score"))
    overall_b = _safe(eval_b.get("overall_score"))

    qual_a = eval_a.get("quality", {})
    qual_b = eval_b.get("quality", {})
    quality_score_a = _safe(qual_a.get("quality_score"))
    quality_score_b = _safe(qual_b.get("quality_score"))

    mat_a = eval_a.get("maturity", {})
    mat_b = eval_b.get("maturity", {})
    maturity_score_a = _safe(mat_a.get("maturity_score"))
    maturity_score_b = _safe(mat_b.get("maturity_score"))

    # Quality sub-scores (radar)
    quality_keys = [
        ("avg_specificita_titolo", "Specificità titolo"),
        ("avg_completezza_descrizione", "Completezza descrizione"),
        ("avg_qualita_criteri", "Qualità criteri"),
        ("avg_pertinenza_topic", "Pertinenza topic"),
    ]
    radar_labels = json.dumps([lbl for _, lbl in quality_keys])
    radar_a = json.dumps([_safe(qual_a.get(k)) for k, _ in quality_keys])
    radar_b = json.dumps([_safe(qual_b.get(k)) for k, _ in quality_keys])

    # Maturity sub-scores (bar)
    maturity_keys = [
        ("copertura_topic", "Copertura topic"),
        ("prontezza_backlog", "Prontezza backlog"),
        ("ambiguita", "Chiarezza"),
        ("duplicati", "Unicità"),
    ]
    bar_labels = json.dumps([lbl for _, lbl in maturity_keys])

    def _mat_score(mat: dict, key: str) -> float:
        sub = mat.get(key, {})
        if isinstance(sub, dict):
            return _safe(sub.get("score"))
        return _safe(sub)

    bar_a = json.dumps([_mat_score(mat_a, k) for k, _ in maturity_keys])
    bar_b = json.dumps([_mat_score(mat_b, k) for k, _ in maturity_keys])

    # Quantity
    qty_a = eval_a.get("quantity", {})
    qty_b = eval_b.get("quantity", {})

    # Lineage
    lineage_a = eval_a.get("lineage", {})
    lineage_b = eval_b.get("lineage", {})
    interview_a = lineage_a.get("interview") or {}
    interview_b = lineage_b.get("interview") or {}

    # Strengths / weaknesses
    strengths_a = eval_a.get("strengths", [])
    strengths_b = eval_b.get("strengths", [])
    weaknesses_a = eval_a.get("weaknesses", [])
    weaknesses_b = eval_b.get("weaknesses", [])

    # Verdetto
    if overall_a > overall_b:
        winner_label = label_a
        winner_letter = "A"
    elif overall_b > overall_a:
        winner_label = label_b
        winner_letter = "B"
    else:
        winner_label = "Pareggio"
        winner_letter = ""

    delta_overall = abs(overall_a - overall_b)
    delta_quality = quality_score_a - quality_score_b
    delta_maturity = maturity_score_a - maturity_score_b

    # Dimensioni vantaggio/svantaggio (dal punto di vista del vincitore)
    # I delta sono calcolati come A - B; se B vince, il segno va invertito.
    sign = 1 if winner_letter != "B" else -1
    advantages = []
    disadvantages = []

    if delta_quality * sign > 0:
        advantages.append("qualità")
    elif delta_quality * sign < 0:
        disadvantages.append("qualità")

    if delta_maturity * sign > 0:
        advantages.append("maturità")
    elif delta_maturity * sign < 0:
        disadvantages.append("maturità")

    qty_total_a = _safe(qty_a.get("total_requirements"))
    qty_total_b = _safe(qty_b.get("total_requirements"))
    delta_qty = qty_total_a - qty_total_b
    if delta_qty * sign > 0:
        advantages.append("quantità")
    elif delta_qty * sign < 0:
        disadvantages.append("quantità")

    if winner_letter:
        adv_str = ", ".join(advantages) if advantages else "nessuna dimensione"
        dis_str = ", ".join(disadvantages) if disadvantages else "nessuna dimensione"
        verdict_text = (
            f"La valutazione {winner_letter} supera l'altra di "
            f"+{delta_overall:.1f} punti overall, con vantaggi in [{adv_str}] "
            f"e svantaggi in [{dis_str}]."
        )
    else:
        verdict_text = "Le due valutazioni hanno lo stesso punteggio overall."

    # Score card helper
    def _score_card_class(a_val: float, b_val: float, side: str) -> str:
        if a_val > b_val:
            return "winner" if side == "a" else "loser"
        if b_val > a_val:
            return "loser" if side == "a" else "winner"
        return "tie"

    # Lineage row helper
    def _lineage_val(interview: dict, key: str, fmt: str = "") -> str:
        val = interview.get(key)
        if val is None:
            return "-"
        if fmt == "f1":
            return f"{val:.1f}s"
        return str(val)

    # Category distribution helper
    def _cat_rows(qty: dict) -> str:
        by_cat = qty.get("by_category", {})
        if not by_cat:
            return "<tr><td colspan='2'>-</td></tr>"
        rows = ""
        for cat, count in sorted(by_cat.items()):
            rows += f"<tr><td>{cat}</td><td>{count}</td></tr>\n"
        return rows

    # Strengths/weaknesses list helper
    def _list_items(items: list) -> str:
        if not items:
            return "<li>-</li>"
        return "\n".join(f"<li>{item}</li>" for item in items)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    escaped_label_a = label_a.replace("&", "&amp;").replace("<", "&lt;")
    escaped_label_b = label_b.replace("&", "&amp;").replace("<", "&lt;")

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Confronto Valutazioni</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  :root {{
    --blue: #3B82F6;
    --blue-bg: rgba(59,130,246,0.2);
    --orange: #F97316;
    --orange-bg: rgba(249,115,22,0.2);
    --green: #22C55E;
    --amber: #F59E0B;
    --gray-50: #F9FAFB;
    --gray-100: #F3F4F6;
    --gray-200: #E5E7EB;
    --gray-600: #4B5563;
    --gray-800: #1F2937;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--gray-50);
    color: var(--gray-800);
    line-height: 1.6;
    padding: 2rem;
  }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.25rem; }}
  .date {{ color: var(--gray-600); font-size: 0.9rem; margin-bottom: 2rem; }}
  h2 {{
    font-size: 1.2rem;
    margin: 2rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--gray-200);
  }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  .card {{
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  .card-a {{ border-top: 4px solid var(--blue); }}
  .card-b {{ border-top: 4px solid var(--orange); }}
  .card-label {{
    font-size: 0.85rem;
    color: var(--gray-600);
    margin-bottom: 0.5rem;
    word-break: break-all;
  }}
  .score-big {{
    font-size: 2.5rem;
    font-weight: 700;
    line-height: 1.2;
  }}
  .score-row {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-top: 0.5rem;
  }}
  .score-label {{ font-size: 0.85rem; color: var(--gray-600); }}
  .score-val {{ font-size: 1.1rem; font-weight: 600; }}
  .delta {{ font-size: 0.8rem; color: var(--gray-600); margin-left: 0.5rem; }}
  .winner .score-big, .winner .score-val {{ color: var(--green); }}
  .loser .score-big, .loser .score-val {{ color: var(--amber); }}
  .tie .score-big, .tie .score-val {{ color: var(--gray-800); }}
  .chart-container {{ background: white; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  canvas {{ max-height: 400px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--gray-200); }}
  th {{ background: var(--gray-100); font-weight: 600; }}
  .verdict {{
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    border-left: 4px solid var(--blue);
    margin-top: 1rem;
  }}
  .verdict strong {{ font-size: 1.1rem; }}
  .verdict p {{ margin-top: 0.5rem; color: var(--gray-600); }}
  ul {{ padding-left: 1.2rem; }}
  li {{ margin-bottom: 0.3rem; }}
  @media (max-width: 768px) {{
    .grid {{ grid-template-columns: 1fr; }}
    body {{ padding: 1rem; }}
  }}
</style>
</head>
<body>
<div class="container">

<!-- 1. Header -->
<h1>Confronto Valutazioni</h1>
<p class="date">Generato il {now}</p>

<!-- 2. Score cards -->
<h2>Punteggi complessivi</h2>
<div class="grid">
  <div class="card card-a {_score_card_class(overall_a, overall_b, 'a')}">
    <div class="card-label">A &mdash; {escaped_label_a}</div>
    <div class="score-big">{overall_a:.1f}<span style="font-size:1rem;font-weight:400">/5.0</span></div>
    <div class="score-row">
      <span class="score-label">Quality</span>
      <span class="score-val">{quality_score_a:.1f} <span class="delta">({_delta_str(quality_score_a, quality_score_b)})</span></span>
    </div>
    <div class="score-row">
      <span class="score-label">Maturity</span>
      <span class="score-val">{maturity_score_a:.1f} <span class="delta">({_delta_str(maturity_score_a, maturity_score_b)})</span></span>
    </div>
  </div>
  <div class="card card-b {_score_card_class(overall_b, overall_a, 'b')}">
    <div class="card-label">B &mdash; {escaped_label_b}</div>
    <div class="score-big">{overall_b:.1f}<span style="font-size:1rem;font-weight:400">/5.0</span></div>
    <div class="score-row">
      <span class="score-label">Quality</span>
      <span class="score-val">{quality_score_b:.1f} <span class="delta">({_delta_str(quality_score_b, quality_score_a)})</span></span>
    </div>
    <div class="score-row">
      <span class="score-label">Maturity</span>
      <span class="score-val">{maturity_score_b:.1f} <span class="delta">({_delta_str(maturity_score_b, maturity_score_a)})</span></span>
    </div>
  </div>
</div>

<!-- 3. Lineage -->
<h2>Catena di produzione</h2>
<div class="grid">
  <div class="card card-a">
    <div class="card-label">A &mdash; {escaped_label_a}</div>
    <table>
      <tr><th>Parametro</th><th>Valore</th></tr>
      <tr><td>Prompt interviewer</td><td>{interview_a.get('interviewer_prompt', '-')}</td></tr>
      <tr><td>Modello intervista</td><td>{interview_a.get('interviewer_model', '-')}</td></tr>
      <tr><td>Modello estrazione</td><td>{lineage_a.get('extraction_model', '-')}</td></tr>
      <tr><td>Modello valutazione</td><td>{eval_a.get('evaluation_model', '-')}</td></tr>
      <tr><td>Turni</td><td>{_lineage_val(interview_a, 'total_turns')}</td></tr>
      <tr><td>Token totali</td><td>{_lineage_val(interview_a, 'total_tokens')}</td></tr>
      <tr><td>Tempo medio turno</td><td>{_lineage_val(interview_a, 'avg_turn_time', 'f1')}</td></tr>
    </table>
  </div>
  <div class="card card-b">
    <div class="card-label">B &mdash; {escaped_label_b}</div>
    <table>
      <tr><th>Parametro</th><th>Valore</th></tr>
      <tr><td>Prompt interviewer</td><td>{interview_b.get('interviewer_prompt', '-')}</td></tr>
      <tr><td>Modello intervista</td><td>{interview_b.get('interviewer_model', '-')}</td></tr>
      <tr><td>Modello estrazione</td><td>{lineage_b.get('extraction_model', '-')}</td></tr>
      <tr><td>Modello valutazione</td><td>{eval_b.get('evaluation_model', '-')}</td></tr>
      <tr><td>Turni</td><td>{_lineage_val(interview_b, 'total_turns')}</td></tr>
      <tr><td>Token totali</td><td>{_lineage_val(interview_b, 'total_tokens')}</td></tr>
      <tr><td>Tempo medio turno</td><td>{_lineage_val(interview_b, 'avg_turn_time', 'f1')}</td></tr>
    </table>
  </div>
</div>

<!-- 4. Radar chart (qualità) -->
<h2>Qualit&agrave; &mdash; Radar</h2>
<div class="chart-container">
  <canvas id="radarChart"></canvas>
</div>

<!-- 5. Bar chart (maturità) -->
<h2>Maturit&agrave; &mdash; Barre</h2>
<div class="chart-container">
  <canvas id="barChart"></canvas>
</div>

<!-- 6. Tabella quantità -->
<h2>Quantit&agrave;</h2>
<div class="grid">
  <div class="card card-a">
    <div class="card-label">A &mdash; {escaped_label_a}</div>
    <table>
      <tr><th>Metrica</th><th>Valore</th></tr>
      <tr><td>Requisiti totali</td><td>{qty_a.get('total_requirements', '-')}</td></tr>
      <tr><td>Categorie distinte</td><td>{qty_a.get('distinct_categories', '-')}</td></tr>
      <tr><td>Criteri accettazione</td><td>{qty_a.get('total_acceptance_criteria', '-')}</td></tr>
    </table>
    <table style="margin-top:0.75rem">
      <tr><th>Categoria</th><th>N</th></tr>
      {_cat_rows(qty_a)}
    </table>
  </div>
  <div class="card card-b">
    <div class="card-label">B &mdash; {escaped_label_b}</div>
    <table>
      <tr><th>Metrica</th><th>Valore</th></tr>
      <tr><td>Requisiti totali</td><td>{qty_b.get('total_requirements', '-')}</td></tr>
      <tr><td>Categorie distinte</td><td>{qty_b.get('distinct_categories', '-')}</td></tr>
      <tr><td>Criteri accettazione</td><td>{qty_b.get('total_acceptance_criteria', '-')}</td></tr>
    </table>
    <table style="margin-top:0.75rem">
      <tr><th>Categoria</th><th>N</th></tr>
      {_cat_rows(qty_b)}
    </table>
  </div>
</div>

<!-- 7. Tempi intervista -->
<h2>Tempi intervista</h2>
<div class="grid">
  <div class="card card-a">
    <div class="card-label">A &mdash; {escaped_label_a}</div>
    <table>
      <tr><th>Metrica</th><th>Valore</th></tr>
      <tr><td>Tempo medio turno</td><td>{_lineage_val(interview_a, 'avg_turn_time', 'f1')}</td></tr>
      <tr><td>Tempo interviewer</td><td>{_lineage_val(interview_a, 'avg_interviewer_time', 'f1')}</td></tr>
      <tr><td>Tempo stakeholder</td><td>{_lineage_val(interview_a, 'avg_stakeholder_time', 'f1')}</td></tr>
    </table>
  </div>
  <div class="card card-b">
    <div class="card-label">B &mdash; {escaped_label_b}</div>
    <table>
      <tr><th>Metrica</th><th>Valore</th></tr>
      <tr><td>Tempo medio turno</td><td>{_lineage_val(interview_b, 'avg_turn_time', 'f1')}</td></tr>
      <tr><td>Tempo interviewer</td><td>{_lineage_val(interview_b, 'avg_interviewer_time', 'f1')}</td></tr>
      <tr><td>Tempo stakeholder</td><td>{_lineage_val(interview_b, 'avg_stakeholder_time', 'f1')}</td></tr>
    </table>
  </div>
</div>

<!-- 8. Punti di forza / debolezze -->
<h2>Punti di forza e debolezze</h2>
<div class="grid">
  <div class="card card-a">
    <div class="card-label">A &mdash; {escaped_label_a}</div>
    <h3 style="color:var(--green);font-size:0.95rem;margin:0.5rem 0">Punti di forza</h3>
    <ul>{_list_items(strengths_a)}</ul>
    <h3 style="color:var(--amber);font-size:0.95rem;margin:0.75rem 0 0.5rem">Debolezze</h3>
    <ul>{_list_items(weaknesses_a)}</ul>
  </div>
  <div class="card card-b">
    <div class="card-label">B &mdash; {escaped_label_b}</div>
    <h3 style="color:var(--green);font-size:0.95rem;margin:0.5rem 0">Punti di forza</h3>
    <ul>{_list_items(strengths_b)}</ul>
    <h3 style="color:var(--amber);font-size:0.95rem;margin:0.75rem 0 0.5rem">Debolezze</h3>
    <ul>{_list_items(weaknesses_b)}</ul>
  </div>
</div>

<!-- 9. Verdetto -->
<h2>Verdetto finale</h2>
<div class="verdict">
  <strong>Vincitore: {winner_label if winner_letter else 'Pareggio'}</strong>
  <p>Overall: {_delta_str(overall_a, overall_b)} | Quality: {_delta_str(quality_score_a, quality_score_b)} | Maturity: {_delta_str(maturity_score_a, maturity_score_b)}</p>
  <p style="margin-top:0.75rem">{verdict_text}</p>
</div>

</div><!-- .container -->

<script>
// Radar chart — Qualità
new Chart(document.getElementById('radarChart'), {{
  type: 'radar',
  data: {{
    labels: {radar_labels},
    datasets: [
      {{
        label: 'A',
        data: {radar_a},
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59,130,246,0.2)',
        pointBackgroundColor: '#3B82F6',
      }},
      {{
        label: 'B',
        data: {radar_b},
        borderColor: '#F97316',
        backgroundColor: 'rgba(249,115,22,0.2)',
        pointBackgroundColor: '#F97316',
      }}
    ]
  }},
  options: {{
    scales: {{
      r: {{
        min: 0, max: 5,
        ticks: {{ stepSize: 1 }},
        pointLabels: {{ font: {{ size: 13 }} }}
      }}
    }},
    plugins: {{ legend: {{ position: 'bottom' }} }}
  }}
}});

// Bar chart — Maturità
new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: {bar_labels},
    datasets: [
      {{
        label: 'A',
        data: {bar_a},
        backgroundColor: 'rgba(59,130,246,0.7)',
        borderColor: '#3B82F6',
        borderWidth: 1,
      }},
      {{
        label: 'B',
        data: {bar_b},
        backgroundColor: 'rgba(249,115,22,0.7)',
        borderColor: '#F97316',
        borderWidth: 1,
      }}
    ]
  }},
  options: {{
    indexAxis: 'y',
    scales: {{
      x: {{ min: 0, max: 5, ticks: {{ stepSize: 1 }} }}
    }},
    plugins: {{ legend: {{ position: 'bottom' }} }}
  }}
}});
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
