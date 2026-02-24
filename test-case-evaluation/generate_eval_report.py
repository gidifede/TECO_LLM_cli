"""Genera un report HTML aggregato da tutte le evaluation.json in output_test/valutazioni/."""

import json
import re
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, median, stdev

EVAL_DIR = Path(__file__).parent / "output_test" / "valutazioni"
OUTPUT_FILE = Path(__file__).parent / "output_test" / "evaluation_report_aggregato.html"

# ---------------------------------------------------------------------------
# 1. Caricamento dati
# ---------------------------------------------------------------------------

def load_evaluations() -> list[dict]:
    evals = []
    for d in sorted(EVAL_DIR.iterdir()):
        jf = d / "evaluation.json"
        if jf.is_file():
            data = json.loads(jf.read_text(encoding="utf-8"))
            if data.get("status") == "ok":
                # Aggiungi categoria derivata dal requirement_id
                req_id = data["requirement_id"]
                match = re.match(r"REQ-([A-Z]+)-", req_id)
                data["_category"] = match.group(1) if match else "OTHER"
                evals.append(data)
    return evals


# ---------------------------------------------------------------------------
# 2. Estrazione metriche
# ---------------------------------------------------------------------------

def extract_metrics(evals: list[dict]) -> dict:
    m: dict = {
        "total": len(evals),
        "rows": [],
        "categories": defaultdict(list),
    }

    for ev in evals:
        req_id = ev["requirement_id"]
        cat = ev["_category"]
        d = ev["direct"]
        ip = ev["indirect_persona"]
        comp = ev["comparison"]

        row = {
            "req_id": req_id,
            "category": cat,
            "d_tc": d["tc_count"],
            "d_score": d["coherence_score"],
            "d_total_ac": d["ac_coverage"]["total_ac"],
            "d_covered_ac": d["ac_coverage"]["covered_ac"],
            "d_added": len(d["added_info"]),
            "d_missing": len(d["missing_info"]),
            "d_redundancies": len(d["redundancies"]),
            "ip_tc": ip["tc_count"],
            "ip_score": ip["coherence_score"],
            "ip_total_ac": ip["ac_coverage"]["total_ac"],
            "ip_covered_ac": ip["ac_coverage"]["covered_ac"],
            "ip_added": len(ip["added_info"]),
            "ip_missing": len(ip["missing_info"]),
            "ip_redundancies": len(ip["redundancies"]),
            "winner": comp["winner"],
            "reasoning": comp["reasoning"],
            "score_gap": d["coherence_score"] - ip["coherence_score"],
        }
        m["rows"].append(row)
        m["categories"][cat].append(row)

    return m


# ---------------------------------------------------------------------------
# 3. Calcolo statistiche aggregate
# ---------------------------------------------------------------------------

def compute_stats(metrics: dict) -> dict:
    rows = metrics["rows"]

    d_scores = [r["d_score"] for r in rows]
    ip_scores = [r["ip_score"] for r in rows]
    gaps = [r["score_gap"] for r in rows]

    winners = Counter(r["winner"] for r in rows)

    # Per-category stats
    cat_stats = {}
    for cat, cat_rows in sorted(metrics["categories"].items()):
        cd = [r["d_score"] for r in cat_rows]
        ci = [r["ip_score"] for r in cat_rows]
        cw = Counter(r["winner"] for r in cat_rows)
        cat_stats[cat] = {
            "count": len(cat_rows),
            "d_avg": round(mean(cd), 1),
            "ip_avg": round(mean(ci), 1),
            "d_median": round(median(cd), 1),
            "ip_median": round(median(ci), 1),
            "direct_wins": cw.get("direct", 0),
            "indirect_wins": cw.get("indirect_persona", 0),
            "avg_gap": round(mean([r["score_gap"] for r in cat_rows]), 1),
            "d_avg_tc": round(mean([r["d_tc"] for r in cat_rows]), 1),
            "ip_avg_tc": round(mean([r["ip_tc"] for r in cat_rows]), 1),
            "d_avg_added": round(mean([r["d_added"] for r in cat_rows]), 1),
            "ip_avg_added": round(mean([r["ip_added"] for r in cat_rows]), 1),
            "d_avg_redundancies": round(mean([r["d_redundancies"] for r in cat_rows]), 1),
            "ip_avg_redundancies": round(mean([r["ip_redundancies"] for r in cat_rows]), 1),
        }

    # Reasoning keyword analysis
    reason_keywords_direct = Counter()
    reason_keywords_indirect = Counter()
    keyword_patterns = [
        ("informazioni non tracciabili", "info_non_tracciabili"),
        ("added_info", "added_info"),
        ("ridondanz", "ridondanze"),
        ("assunzioni", "assunzioni"),
        ("scenari extra", "scenari_extra"),
        ("edge case", "edge_case"),
        ("copertura", "copertura"),
        ("aderente", "aderenza"),
        ("penalità", "penalita"),
        ("esplosione", "esplosione"),
    ]
    for r in rows:
        reason_lower = r["reasoning"].lower()
        target = reason_keywords_direct if r["winner"] == "direct" else reason_keywords_indirect
        for pattern, key in keyword_patterns:
            if pattern in reason_lower:
                target[key] += 1

    return {
        "total": len(rows),
        "direct_wins": winners.get("direct", 0),
        "indirect_wins": winners.get("indirect_persona", 0),
        "d_avg": round(mean(d_scores), 1),
        "d_median": round(median(d_scores), 1),
        "d_stdev": round(stdev(d_scores), 1) if len(d_scores) > 1 else 0,
        "d_min": min(d_scores),
        "d_max": max(d_scores),
        "ip_avg": round(mean(ip_scores), 1),
        "ip_median": round(median(ip_scores), 1),
        "ip_stdev": round(stdev(ip_scores), 1) if len(ip_scores) > 1 else 0,
        "ip_min": min(ip_scores),
        "ip_max": max(ip_scores),
        "gap_avg": round(mean(gaps), 1),
        "gap_median": round(median(gaps), 1),
        "gap_max": max(gaps),
        "gap_min": min(gaps),
        "d_avg_tc": round(mean([r["d_tc"] for r in rows]), 1),
        "ip_avg_tc": round(mean([r["ip_tc"] for r in rows]), 1),
        "d_avg_added": round(mean([r["d_added"] for r in rows]), 1),
        "ip_avg_added": round(mean([r["ip_added"] for r in rows]), 1),
        "d_avg_missing": round(mean([r["d_missing"] for r in rows]), 1),
        "ip_avg_missing": round(mean([r["ip_missing"] for r in rows]), 1),
        "d_avg_redundancies": round(mean([r["d_redundancies"] for r in rows]), 1),
        "ip_avg_redundancies": round(mean([r["ip_redundancies"] for r in rows]), 1),
        "cat_stats": cat_stats,
        "reason_kw_direct": dict(reason_keywords_direct.most_common()),
        "reason_kw_indirect": dict(reason_keywords_indirect.most_common()),
    }


# ---------------------------------------------------------------------------
# 4. Generazione HTML
# ---------------------------------------------------------------------------

CATEGORY_LABELS = {
    "D": "Dati",
    "F": "Funzionali",
    "I": "Integrazione",
    "NF": "Non-Funzionali",
    "UI": "Interfaccia",
    "V": "Validazione",
}


def generate_html(metrics: dict, stats: dict) -> str:
    rows = metrics["rows"]

    # Prepare JSON data for charts
    req_labels = json.dumps([r["req_id"] for r in rows])
    d_scores_json = json.dumps([r["d_score"] for r in rows])
    ip_scores_json = json.dumps([r["ip_score"] for r in rows])
    gap_json = json.dumps([r["score_gap"] for r in rows])
    winner_colors = json.dumps(["#2563eb" if r["winner"] == "direct" else "#f59e0b" for r in rows])

    d_tc_json = json.dumps([r["d_tc"] for r in rows])
    ip_tc_json = json.dumps([r["ip_tc"] for r in rows])
    d_added_json = json.dumps([r["d_added"] for r in rows])
    ip_added_json = json.dumps([r["ip_added"] for r in rows])
    d_redund_json = json.dumps([r["d_redundancies"] for r in rows])
    ip_redund_json = json.dumps([r["ip_redundancies"] for r in rows])

    cat_labels = json.dumps([CATEGORY_LABELS.get(c, c) for c in sorted(stats["cat_stats"])])
    cat_d_avg = json.dumps([stats["cat_stats"][c]["d_avg"] for c in sorted(stats["cat_stats"])])
    cat_ip_avg = json.dumps([stats["cat_stats"][c]["ip_avg"] for c in sorted(stats["cat_stats"])])
    cat_direct_wins = json.dumps([stats["cat_stats"][c]["direct_wins"] for c in sorted(stats["cat_stats"])])
    cat_indirect_wins = json.dumps([stats["cat_stats"][c]["indirect_wins"] for c in sorted(stats["cat_stats"])])
    cat_d_tc = json.dumps([stats["cat_stats"][c]["d_avg_tc"] for c in sorted(stats["cat_stats"])])
    cat_ip_tc = json.dumps([stats["cat_stats"][c]["ip_avg_tc"] for c in sorted(stats["cat_stats"])])

    # Score distribution buckets
    def bucket(scores):
        buckets = [0]*10  # 0-9, 10-19, ..., 90-100
        for s in scores:
            idx = min(s // 10, 9)
            buckets[idx] += 1
        return buckets

    d_dist = json.dumps(bucket([r["d_score"] for r in rows]))
    ip_dist = json.dumps(bucket([r["ip_score"] for r in rows]))

    # Category detail table rows
    cat_table_rows = ""
    for cat in sorted(stats["cat_stats"]):
        cs = stats["cat_stats"][cat]
        cat_name = CATEGORY_LABELS.get(cat, cat)
        total_cat = cs["count"]
        dw = cs["direct_wins"]
        iw = cs["indirect_wins"]
        dw_pct = round(dw / total_cat * 100)
        cat_table_rows += f"""
        <tr>
            <td><strong>REQ-{cat}</strong> — {cat_name}</td>
            <td>{total_cat}</td>
            <td>{cs['d_avg']}</td>
            <td>{cs['ip_avg']}</td>
            <td>{cs['avg_gap']:+.1f}</td>
            <td>{dw} ({dw_pct}%)</td>
            <td>{iw} ({100-dw_pct}%)</td>
            <td>{cs['d_avg_tc']}</td>
            <td>{cs['ip_avg_tc']}</td>
            <td>{cs['d_avg_added']}</td>
            <td>{cs['ip_avg_added']}</td>
            <td>{cs['d_avg_redundancies']}</td>
            <td>{cs['ip_avg_redundancies']}</td>
        </tr>"""

    # Detail table
    detail_rows = ""
    for r in rows:
        w_badge = '<span class="badge badge-direct">Diretto</span>' if r["winner"] == "direct" else '<span class="badge badge-indirect">Persona</span>'
        gap_class = "positive" if r["score_gap"] > 0 else ("negative" if r["score_gap"] < 0 else "")
        detail_rows += f"""
        <tr>
            <td><code>{r['req_id']}</code></td>
            <td>{CATEGORY_LABELS.get(r['category'], r['category'])}</td>
            <td>{r['d_score']}</td>
            <td>{r['ip_score']}</td>
            <td class="{gap_class}">{r['score_gap']:+d}</td>
            <td>{w_badge}</td>
            <td>{r['d_tc']}</td>
            <td>{r['ip_tc']}</td>
            <td>{r['d_added']}</td>
            <td>{r['ip_added']}</td>
            <td>{r['d_redundancies']}</td>
            <td>{r['ip_redundancies']}</td>
        </tr>"""

    # Reasoning analysis: find top patterns
    # Group reasonings by winner
    direct_reasonings = [r["reasoning"] for r in rows if r["winner"] == "direct"]
    indirect_reasonings = [r["reasoning"] for r in rows if r["winner"] == "indirect_persona"]

    # Biggest wins for direct
    sorted_by_gap = sorted(rows, key=lambda r: r["score_gap"], reverse=True)
    top_direct = sorted_by_gap[:5]
    top_indirect = sorted_by_gap[-5:][::-1]  # Reverse to show biggest indirect wins

    top_direct_html = ""
    for r in top_direct:
        top_direct_html += f"""
        <div class="reasoning-card">
            <div class="reasoning-header">
                <code>{r['req_id']}</code> — Gap: <strong>{r['score_gap']:+d}</strong>
                (Diretto: {r['d_score']} vs Persona: {r['ip_score']})
            </div>
            <p>{r['reasoning']}</p>
        </div>"""

    top_indirect_html = ""
    for r in top_indirect:
        top_indirect_html += f"""
        <div class="reasoning-card">
            <div class="reasoning-header">
                <code>{r['req_id']}</code> — Gap: <strong>{r['score_gap']:+d}</strong>
                (Diretto: {r['d_score']} vs Persona: {r['ip_score']})
            </div>
            <p>{r['reasoning']}</p>
        </div>"""

    # Correlation: tc_count vs score
    d_tc_scores = json.dumps([{"x": r["d_tc"], "y": r["d_score"]} for r in rows])
    ip_tc_scores = json.dumps([{"x": r["ip_tc"], "y": r["ip_score"]} for r in rows])

    # Added info vs score correlation
    d_added_scores = json.dumps([{"x": r["d_added"], "y": r["d_score"]} for r in rows])
    ip_added_scores = json.dumps([{"x": r["ip_added"], "y": r["ip_score"]} for r in rows])

    direct_win_pct = round(stats["direct_wins"] / stats["total"] * 100)
    indirect_win_pct = 100 - direct_win_pct

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Report Valutazione Coerenza — TECO LLM CLI</title>
<script src="chart.umd.min.js"></script>
<style>
    :root {{
        --blue: #2563eb;
        --blue-light: #93c5fd;
        --amber: #f59e0b;
        --amber-light: #fde68a;
        --green: #16a34a;
        --red: #dc2626;
        --gray-50: #f9fafb;
        --gray-100: #f3f4f6;
        --gray-200: #e5e7eb;
        --gray-300: #d1d5db;
        --gray-600: #4b5563;
        --gray-700: #374151;
        --gray-800: #1f2937;
        --gray-900: #111827;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: var(--gray-50);
        color: var(--gray-800);
        line-height: 1.6;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    h1 {{
        font-size: 28px; font-weight: 700; margin-bottom: 8px;
        color: var(--gray-900);
    }}
    h2 {{
        font-size: 20px; font-weight: 600; margin: 32px 0 16px;
        color: var(--gray-900); border-bottom: 2px solid var(--gray-200);
        padding-bottom: 8px;
    }}
    h3 {{ font-size: 16px; font-weight: 600; margin: 16px 0 8px; color: var(--gray-700); }}
    .subtitle {{ color: var(--gray-600); font-size: 14px; margin-bottom: 24px; }}

    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 32px;
    }}
    .kpi-card {{
        background: white; border-radius: 12px; padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .kpi-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--gray-600); margin-bottom: 4px; }}
    .kpi-value {{ font-size: 28px; font-weight: 700; }}
    .kpi-sub {{ font-size: 12px; color: var(--gray-600); margin-top: 4px; }}
    .kpi-blue .kpi-value {{ color: var(--blue); }}
    .kpi-amber .kpi-value {{ color: var(--amber); }}
    .kpi-green .kpi-value {{ color: var(--green); }}
    .kpi-red .kpi-value {{ color: var(--red); }}

    .chart-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
        gap: 24px;
        margin-bottom: 32px;
    }}
    .chart-card {{
        background: white; border-radius: 12px; padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .chart-card h3 {{ margin-top: 0; }}
    .chart-container {{ position: relative; height: 350px; }}
    .chart-container-small {{ position: relative; height: 280px; }}

    table {{
        width: 100%; border-collapse: collapse; font-size: 13px;
        background: white; border-radius: 12px; overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    th {{
        background: var(--gray-100); padding: 10px 8px; text-align: left;
        font-weight: 600; color: var(--gray-700); font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.3px;
        position: sticky; top: 0;
    }}
    td {{ padding: 8px; border-top: 1px solid var(--gray-100); }}
    tr:hover td {{ background: var(--gray-50); }}
    .positive {{ color: var(--green); font-weight: 600; }}
    .negative {{ color: var(--red); font-weight: 600; }}

    .badge {{
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-size: 11px; font-weight: 600;
    }}
    .badge-direct {{ background: var(--blue-light); color: #1e40af; }}
    .badge-indirect {{ background: var(--amber-light); color: #92400e; }}

    .reasoning-card {{
        background: white; border-radius: 8px; padding: 16px;
        margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        border-left: 4px solid var(--gray-300);
    }}
    .reasoning-header {{ font-size: 13px; margin-bottom: 8px; color: var(--gray-600); }}
    .reasoning-card p {{ font-size: 13px; color: var(--gray-700); }}

    .insights-box {{
        background: white; border-radius: 12px; padding: 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px;
    }}
    .insights-box ul {{ margin-left: 20px; }}
    .insights-box li {{ margin-bottom: 8px; font-size: 14px; }}
    .insights-box strong {{ color: var(--gray-900); }}

    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
    @media (max-width: 900px) {{
        .two-col {{ grid-template-columns: 1fr; }}
        .chart-grid {{ grid-template-columns: 1fr; }}
    }}
</style>
</head>
<body>
<div class="container">

<h1>Report Valutazione Coerenza</h1>
<p class="subtitle">
    Confronto tra percorso <strong style="color:var(--blue)">diretto</strong> (requisito → test cases) e
    <strong style="color:var(--amber)">indiretto persona-based</strong> (requisito → user stories → test cases)
    su {stats['total']} requisiti valutati.
</p>

<!-- ═══════════════ KPI ═══════════════ -->
<h2>Panoramica</h2>
<div class="kpi-grid">
    <div class="kpi-card kpi-blue">
        <div class="kpi-label">Valutazioni totali</div>
        <div class="kpi-value">{stats['total']}</div>
        <div class="kpi-sub">{len(stats['cat_stats'])} categorie di requisiti</div>
    </div>
    <div class="kpi-card kpi-blue">
        <div class="kpi-label">Vittorie Diretto</div>
        <div class="kpi-value">{stats['direct_wins']} ({direct_win_pct}%)</div>
        <div class="kpi-sub">Score medio: {stats['d_avg']}</div>
    </div>
    <div class="kpi-card kpi-amber">
        <div class="kpi-label">Vittorie Persona</div>
        <div class="kpi-value">{stats['indirect_wins']} ({indirect_win_pct}%)</div>
        <div class="kpi-sub">Score medio: {stats['ip_avg']}</div>
    </div>
    <div class="kpi-card kpi-green">
        <div class="kpi-label">Gap medio (D - P)</div>
        <div class="kpi-value">{stats['gap_avg']:+.1f}</div>
        <div class="kpi-sub">Mediana: {stats['gap_median']:+.1f} | Max: {stats['gap_max']:+d}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Score Diretto</div>
        <div class="kpi-value">{stats['d_avg']}</div>
        <div class="kpi-sub">Min {stats['d_min']} — Max {stats['d_max']} — &sigma; {stats['d_stdev']}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Score Persona</div>
        <div class="kpi-value">{stats['ip_avg']}</div>
        <div class="kpi-sub">Min {stats['ip_min']} — Max {stats['ip_max']} — &sigma; {stats['ip_stdev']}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">TC medi Diretto</div>
        <div class="kpi-value">{stats['d_avg_tc']}</div>
        <div class="kpi-sub">Added info medio: {stats['d_avg_added']}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">TC medi Persona</div>
        <div class="kpi-value">{stats['ip_avg_tc']}</div>
        <div class="kpi-sub">Added info medio: {stats['ip_avg_added']}</div>
    </div>
</div>

<!-- ═══════════════ GRAFICI PRINCIPALI ═══════════════ -->
<h2>Distribuzione Score di Coerenza</h2>
<div class="chart-grid">
    <div class="chart-card">
        <h3>Score per requisito (ordinato per gap)</h3>
        <div class="chart-container"><canvas id="chartScores"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Distribuzione frequenze score</h3>
        <div class="chart-container"><canvas id="chartDist"></canvas></div>
    </div>
</div>

<div class="chart-grid">
    <div class="chart-card">
        <h3>Gap (Diretto - Persona) per requisito</h3>
        <div class="chart-container"><canvas id="chartGap"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Vincitore per categoria</h3>
        <div class="chart-container"><canvas id="chartCatWins"></canvas></div>
    </div>
</div>

<!-- ═══════════════ ANALISI PER CATEGORIA ═══════════════ -->
<h2>Analisi per Categoria</h2>
<div class="chart-grid">
    <div class="chart-card">
        <h3>Score medio per categoria</h3>
        <div class="chart-container-small"><canvas id="chartCatAvg"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Test cases medi per categoria</h3>
        <div class="chart-container-small"><canvas id="chartCatTC"></canvas></div>
    </div>
</div>

<div style="overflow-x:auto; margin-bottom: 32px;">
<table>
    <thead>
        <tr>
            <th>Categoria</th><th>N.</th>
            <th>Avg D</th><th>Avg P</th><th>Gap</th>
            <th>Vince D</th><th>Vince P</th>
            <th>TC D</th><th>TC P</th>
            <th>Added D</th><th>Added P</th>
            <th>Redund. D</th><th>Redund. P</th>
        </tr>
    </thead>
    <tbody>{cat_table_rows}</tbody>
</table>
</div>

<!-- ═══════════════ CORRELAZIONI ═══════════════ -->
<h2>Correlazioni</h2>
<div class="chart-grid">
    <div class="chart-card">
        <h3>Numero TC vs Score di coerenza</h3>
        <div class="chart-container"><canvas id="chartTcVsScore"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Added Info vs Score di coerenza</h3>
        <div class="chart-container"><canvas id="chartAddedVsScore"></canvas></div>
    </div>
</div>

<!-- ═══════════════ ADDED INFO / RIDONDANZE ═══════════════ -->
<h2>Informazioni Aggiunte e Ridondanze</h2>
<div class="chart-grid">
    <div class="chart-card">
        <h3>Added Info per requisito</h3>
        <div class="chart-container"><canvas id="chartAdded"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Ridondanze per requisito</h3>
        <div class="chart-container"><canvas id="chartRedund"></canvas></div>
    </div>
</div>

<!-- ═══════════════ INSIGHT E MOTIVAZIONI ═══════════════ -->
<h2>Analisi Qualitativa: Perche il Diretto Tende a Vincere</h2>
<div class="insights-box">
    <h3>Pattern ricorrenti nelle valutazioni</h3>
    <ul>
        <li><strong>Esplosione dei test cases</strong>: il percorso persona genera in media {stats['ip_avg_tc']} TC contro {stats['d_avg_tc']} del diretto ({round(stats['ip_avg_tc']/stats['d_avg_tc']*100 - 100)}% in piu). Piu TC non significa piu copertura ma piu assunzioni.</li>
        <li><strong>Informazioni non tracciabili</strong>: il persona aggiunge in media {stats['ip_avg_added']} elementi non presenti nel requisito originale contro {stats['d_avg_added']} del diretto. Ogni assunzione e una penalita di coerenza.</li>
        <li><strong>Ridondanze</strong>: il persona produce {stats['ip_avg_redundancies']} ridondanze medie contro {stats['d_avg_redundancies']} del diretto — scenari simili replicati per ogni persona/canale generano sovrapposizioni.</li>
        <li><strong>Scenari inventati</strong>: il passaggio per le user stories tende a introdurre scenari edge-case, gestione errori, dettagli UI/UX e vincoli tecnici non richiesti dal requisito.</li>
        <li><strong>Riformulazione e drift semantico</strong>: ogni layer di trasformazione (requisito → US → TC) aggiunge un margine di interpretazione. Il percorso diretto ha un solo passaggio, il persona ne ha due.</li>
        <li><strong>Copertura AC invariata</strong>: entrambi i percorsi coprono sempre tutti gli acceptance criteria — il vantaggio del persona non sta nella copertura ma nella prospettiva utente.</li>
    </ul>
</div>

<div class="insights-box">
    <h3>Quando il percorso persona vince</h3>
    <ul>
        <li>Su {stats['indirect_wins']} requisiti ({indirect_win_pct}%) il persona ottiene un punteggio migliore.</li>
        <li>Tipicamente si tratta di requisiti dove il diretto introduce piu assunzioni tecniche (codici HTTP, API, correlazione, timeout) mentre il persona resta piu focalizzato sull'esperienza utente osservabile.</li>
        <li>Il vantaggio del persona e marginale: nei casi di vittoria, il gap medio e inferiore rispetto alle vittorie del diretto.</li>
    </ul>
</div>

<div class="two-col">
    <div>
        <h3>Top 5 — Maggiori vittorie del Diretto</h3>
        {top_direct_html}
    </div>
    <div>
        <h3>Top 5 — Maggiori vittorie del Persona</h3>
        {top_indirect_html}
    </div>
</div>

<!-- ═══════════════ TABELLA DETTAGLIO ═══════════════ -->
<h2>Dettaglio per Requisito</h2>
<div style="overflow-x:auto;">
<table>
    <thead>
        <tr>
            <th>Requisito</th><th>Categoria</th>
            <th>Score D</th><th>Score P</th><th>Gap</th><th>Vincitore</th>
            <th>TC D</th><th>TC P</th>
            <th>Added D</th><th>Added P</th>
            <th>Red. D</th><th>Red. P</th>
        </tr>
    </thead>
    <tbody>{detail_rows}</tbody>
</table>
</div>

<p style="margin-top:32px; font-size:12px; color:var(--gray-600);">
    Report generato automaticamente da <code>generate_eval_report.py</code> — TECO LLM CLI
</p>
</div>

<!-- ═══════════════ CHART.JS ═══════════════ -->
<script>
const blue = '#2563eb';
const blueLight = '#93c5fd33';
const amber = '#f59e0b';
const amberLight = '#fde68a33';

// --- Scores per requisito (sorted by gap) ---
(() => {{
    const labels = {req_labels};
    const dScores = {d_scores_json};
    const ipScores = {ip_scores_json};
    const gaps = {gap_json};
    // Sort by gap descending
    const indices = gaps.map((g, i) => i).sort((a, b) => gaps[b] - gaps[a]);
    new Chart(document.getElementById('chartScores'), {{
        type: 'bar',
        data: {{
            labels: indices.map(i => labels[i]),
            datasets: [
                {{ label: 'Diretto', data: indices.map(i => dScores[i]), backgroundColor: blue, borderRadius: 2 }},
                {{ label: 'Persona', data: indices.map(i => ipScores[i]), backgroundColor: amber, borderRadius: 2 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{
                x: {{ ticks: {{ display: false }} }},
                y: {{ min: 0, max: 100, title: {{ display: true, text: 'Score coerenza' }} }}
            }}
        }}
    }});
}})();

// --- Distribution histogram ---
(() => {{
    const bucketLabels = ['0-9','10-19','20-29','30-39','40-49','50-59','60-69','70-79','80-89','90-100'];
    new Chart(document.getElementById('chartDist'), {{
        type: 'bar',
        data: {{
            labels: bucketLabels,
            datasets: [
                {{ label: 'Diretto', data: {d_dist}, backgroundColor: blue, borderRadius: 4 }},
                {{ label: 'Persona', data: {ip_dist}, backgroundColor: amber, borderRadius: 4 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{ y: {{ title: {{ display: true, text: 'Frequenza' }}, beginAtZero: true }} }}
        }}
    }});
}})();

// --- Gap chart ---
(() => {{
    const labels = {req_labels};
    const gaps = {gap_json};
    const indices = gaps.map((g, i) => i).sort((a, b) => gaps[b] - gaps[a]);
    const colors = indices.map(i => gaps[i] >= 0 ? blue : amber);
    new Chart(document.getElementById('chartGap'), {{
        type: 'bar',
        data: {{
            labels: indices.map(i => labels[i]),
            datasets: [{{ label: 'Gap (D - P)', data: indices.map(i => gaps[i]), backgroundColor: colors, borderRadius: 2 }}]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{
                x: {{ ticks: {{ display: false }} }},
                y: {{ title: {{ display: true, text: 'Gap score' }} }}
            }}
        }}
    }});
}})();

// --- Category wins ---
(() => {{
    new Chart(document.getElementById('chartCatWins'), {{
        type: 'bar',
        data: {{
            labels: {cat_labels},
            datasets: [
                {{ label: 'Vince Diretto', data: {cat_direct_wins}, backgroundColor: blue, borderRadius: 4 }},
                {{ label: 'Vince Persona', data: {cat_indirect_wins}, backgroundColor: amber, borderRadius: 4 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true, title: {{ display: true, text: 'Requisiti' }} }} }}
        }}
    }});
}})();

// --- Category avg score ---
(() => {{
    new Chart(document.getElementById('chartCatAvg'), {{
        type: 'bar',
        data: {{
            labels: {cat_labels},
            datasets: [
                {{ label: 'Diretto', data: {cat_d_avg}, backgroundColor: blue, borderRadius: 4 }},
                {{ label: 'Persona', data: {cat_ip_avg}, backgroundColor: amber, borderRadius: 4 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{ x: {{ min: 0, max: 100, title: {{ display: true, text: 'Score medio' }} }} }}
        }}
    }});
}})();

// --- Category avg TC ---
(() => {{
    const catLabels = {cat_labels};
    const dTC = {cat_d_tc};
    const ipTC = {cat_ip_tc};
    new Chart(document.getElementById('chartCatTC'), {{
        type: 'bar',
        data: {{
            labels: catLabels,
            datasets: [
                {{ label: 'TC Diretto', data: dTC, backgroundColor: blue, borderRadius: 4 }},
                {{ label: 'TC Persona', data: ipTC, backgroundColor: amber, borderRadius: 4 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{ x: {{ beginAtZero: true, title: {{ display: true, text: 'TC medi' }} }} }}
        }}
    }});
}})();

// --- TC vs Score scatter ---
(() => {{
    new Chart(document.getElementById('chartTcVsScore'), {{
        type: 'scatter',
        data: {{
            datasets: [
                {{ label: 'Diretto', data: {d_tc_scores}, backgroundColor: blue + '99', pointRadius: 5 }},
                {{ label: 'Persona', data: {ip_tc_scores}, backgroundColor: amber + '99', pointRadius: 5 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{
                x: {{ title: {{ display: true, text: 'Numero Test Cases' }}, beginAtZero: true }},
                y: {{ title: {{ display: true, text: 'Score coerenza' }}, min: 0, max: 100 }}
            }}
        }}
    }});
}})();

// --- Added Info vs Score scatter ---
(() => {{
    new Chart(document.getElementById('chartAddedVsScore'), {{
        type: 'scatter',
        data: {{
            datasets: [
                {{ label: 'Diretto', data: {d_added_scores}, backgroundColor: blue + '99', pointRadius: 5 }},
                {{ label: 'Persona', data: {ip_added_scores}, backgroundColor: amber + '99', pointRadius: 5 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{
                x: {{ title: {{ display: true, text: 'Added Info (count)' }}, beginAtZero: true }},
                y: {{ title: {{ display: true, text: 'Score coerenza' }}, min: 0, max: 100 }}
            }}
        }}
    }});
}})();

// --- Added info per requisito ---
(() => {{
    const labels = {req_labels};
    new Chart(document.getElementById('chartAdded'), {{
        type: 'bar',
        data: {{
            labels: labels,
            datasets: [
                {{ label: 'Diretto', data: {d_added_json}, backgroundColor: blue, borderRadius: 2 }},
                {{ label: 'Persona', data: {ip_added_json}, backgroundColor: amber, borderRadius: 2 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{
                x: {{ ticks: {{ display: false }} }},
                y: {{ beginAtZero: true, title: {{ display: true, text: 'Added Info' }} }}
            }}
        }}
    }});
}})();

// --- Redundancies per requisito ---
(() => {{
    const labels = {req_labels};
    new Chart(document.getElementById('chartRedund'), {{
        type: 'bar',
        data: {{
            labels: labels,
            datasets: [
                {{ label: 'Diretto', data: {d_redund_json}, backgroundColor: blue, borderRadius: 2 }},
                {{ label: 'Persona', data: {ip_redund_json}, backgroundColor: amber, borderRadius: 2 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{
                x: {{ ticks: {{ display: false }} }},
                y: {{ beginAtZero: true, title: {{ display: true, text: 'Ridondanze' }} }}
            }}
        }}
    }});
}})();
</script>
</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Caricamento valutazioni da {EVAL_DIR}...")
    evals = load_evaluations()
    print(f"  Caricate {len(evals)} valutazioni")

    print("Estrazione metriche...")
    metrics = extract_metrics(evals)

    print("Calcolo statistiche...")
    stats = compute_stats(metrics)

    print("Generazione HTML...")
    html = generate_html(metrics, stats)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Report salvato in: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
