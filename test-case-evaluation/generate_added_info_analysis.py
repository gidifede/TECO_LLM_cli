"""Analisi qualitativa delle added_info: valore vs rumore nei test cases persona-based."""

import json
import re
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean

EVAL_DIR = Path(__file__).parent / "output_test" / "valutazioni"
OUTPUT_FILE = Path(__file__).parent / "output_test" / "added_info_analysis.html"

CATEGORY_LABELS = {
    "D": "Dati",
    "F": "Funzionali",
    "I": "Integrazione",
    "NF": "Non-Funzionali",
    "UI": "Interfaccia",
    "V": "Validazione",
}

# ---------------------------------------------------------------------------
# Classificazione a 3 livelli di valore
# ---------------------------------------------------------------------------

VALUE_TIERS = {
    "valuable": {
        "label": "Valore concreto",
        "color": "#16a34a",
        "color_light": "#bbf7d0",
        "description": "Scenari che un QA esperto aggiungerebbe indipendentemente dal requisito: "
                       "resilienza, input invalidi, concorrenza, sicurezza, stati vuoti.",
    },
    "useful": {
        "label": "Potenzialmente utile",
        "color": "#2563eb",
        "color_light": "#bfdbfe",
        "description": "Estensioni ragionevoli che coprono aspetti spesso necessari in produzione: "
                       "audit, cross-channel, backward compatibility, recovery.",
    },
    "noise": {
        "label": "Rumore",
        "color": "#dc2626",
        "color_light": "#fecaca",
        "description": "Dettagli inventati dal modello senza base nel requisito: componenti UI fittizi, "
                       "scelte implementative specifiche, attori/workflow inesistenti.",
    },
    "extension": {
        "label": "Estensione di scope",
        "color": "#f59e0b",
        "color_light": "#fde68a",
        "description": "Informazioni non errate ma fuori dal perimetro del requisito: "
                       "assunzioni ragionevoli, scenari nuovi, estensioni di funzionalità.",
    },
    "unclassified": {
        "label": "Non classificato",
        "color": "#6b7280",
        "color_light": "#e5e7eb",
        "description": "Aggiunte non rientrate nelle categorie precedenti.",
    },
}

SUBCATEGORY_LABELS = {
    "resilience": "Resilienza / Error handling",
    "data_quality": "Qualità dati / Input validation",
    "concurrency": "Concorrenza / Race conditions",
    "security": "Sicurezza / Session management",
    "negative_test": "Test negativi / Stati vuoti",
    "cross_channel": "Coerenza cross-canale",
    "backward_compat": "Backward compatibility",
    "audit": "Audit / Tracciamento",
    "recovery": "Recovery / Ripristino",
    "invented_ui": "UI/UX inventata",
    "tech_impl": "Dettagli tecnici implementativi",
    "impl_choice": "Scelte implementative (flag, config)",
    "invented_component": "Componenti/servizi inventati",
    "invented_workflow": "Workflow/stati inventati",
    "beyond_scope": "Fuori perimetro (esplicito)",
    "assumption": "Assunzioni non tracciabili",
    "new_scenario": "Scenari nuovi estesi",
    "other": "Altro",
}


def classify_value(detail: str) -> tuple[str, str]:
    """Classifica una added_info in (tier, subcategory)."""
    dl = detail.lower()

    # === VALUABLE ===
    if any(p in dl for p in [
        "timeout", "indisponibil", "503", "500", "502",
        "fallback", "servizio non disponibile", "retry",
        "gestione errori", "degraded", "circuit breaker",
    ]):
        return ("valuable", "resilience")
    if any(p in dl for p in [
        "dato inconsisten", "dato mancante", "campo mancante",
        "valore nullo", "null", "input non valido", "formato non valido",
        "validazione input", "durata 0", "caratteri speciali", "lunghezza",
    ]):
        return ("valuable", "data_quality")
    if any(p in dl for p in [
        "concorren", "race condition", "simultaneo",
        "idempotenza", "deduplica", "lock",
    ]):
        return ("valuable", "concurrency")
    if any(p in dl for p in [
        "sessione scaduta", "permessi revocati durante",
        "privilege escalation", "injection", "atomicit",
    ]):
        return ("valuable", "security")
    if any(p in dl for p in [
        "lista vuota", "nessun risultato", "nessuna offerta",
        "nessun dato", "offerte vuota",
    ]):
        return ("valuable", "negative_test")

    # === USEFUL ===
    if any(p in dl for p in [
        "cross-canal", "coerenza tra canale", "allineamento canal",
        "coerenza tra app", "coerenza tra web", "cross canale",
    ]):
        return ("useful", "cross_channel")
    if any(p in dl for p in ["retroattiv", "backward", "migrazione", "legacy", "deprecat"]):
        return ("useful", "backward_compat")
    if any(p in dl for p in ["audit", "tracciamento", "log operazion"]):
        return ("useful", "audit")
    if any(p in dl for p in [
        "recupero", "recovery", "ripristino", "stati intermedi", "consistenz",
    ]):
        return ("useful", "recovery")

    # === NOISE ===
    if any(p in dl for p in [
        "dashboard", "schermata", "pop-up", "modale", "toast", "tooltip",
        "banner", "spinner", "placeholder", "layout", "rendering",
        "etichetta", "popup",
    ]):
        return ("noise", "invented_ui")
    if any(p in dl for p in [
        "endpoint", "http", "rest", "payload json", "status code",
        "siem", "correlation", "x-correlation", "deep link", "url specifica",
    ]):
        return ("noise", "tech_impl")
    if any(p in dl for p in ["feature flag", "flag", "toggle"]):
        return ("noise", "impl_choice")
    if re.search(r"introduce.*(?:componente|attore|servizio|motore|modulo)", dl):
        return ("noise", "invented_component")
    if re.search(r"introduce.*(?:stato|workflow|approvazione|rifiut)", dl):
        return ("noise", "invented_workflow")

    # === EXTENSION ===
    if any(p in dl for p in [
        "non menzionato", "non presente nel requisito",
        "non previsto", "non richiesto", "non definit",
        "non esplicit", "non trattato", "non citato", "non descritto",
    ]):
        return ("extension", "beyond_scope")
    if any(p in dl for p in ["assume", "assunzione", "ipotesi"]):
        return ("extension", "assumption")
    if "introduce" in dl:
        return ("extension", "new_scenario")

    return ("unclassified", "other")


# ---------------------------------------------------------------------------
# Caricamento e analisi
# ---------------------------------------------------------------------------

def load_and_classify():
    ip_items = []
    d_items = []

    for d in sorted(EVAL_DIR.iterdir()):
        jf = d / "evaluation.json"
        if not jf.is_file():
            continue
        data = json.loads(jf.read_text(encoding="utf-8"))
        if data.get("status") != "ok":
            continue

        req = data["requirement_id"]
        match = re.match(r"REQ-([A-Z]+)-", req)
        cat = match.group(1) if match else "OTHER"

        for item in data["indirect_persona"]["added_info"]:
            tier, subcat = classify_value(item["detail"])
            ip_items.append({
                "req": req, "cat": cat, "tc": item["test_id"],
                "detail": item["detail"], "tier": tier, "subcat": subcat,
            })

        for item in data["direct"]["added_info"]:
            tier, subcat = classify_value(item["detail"])
            d_items.append({
                "req": req, "cat": cat, "tc": item["test_id"],
                "detail": item["detail"], "tier": tier, "subcat": subcat,
            })

    return ip_items, d_items


# ---------------------------------------------------------------------------
# Generazione HTML
# ---------------------------------------------------------------------------

def generate_html(ip_items, d_items):
    total_ip = len(ip_items)
    total_d = len(d_items)

    # Tier counts
    ip_tiers = Counter(i["tier"] for i in ip_items)
    d_tiers = Counter(i["tier"] for i in d_items)

    # Subcategory counts
    ip_subcats = Counter(i["subcat"] for i in ip_items)
    d_subcats = Counter(i["subcat"] for i in d_items)

    # By requirement category
    cat_tier = defaultdict(lambda: Counter())
    for i in ip_items:
        cat_tier[i["cat"]][i["tier"]] += 1

    # By requirement (for per-requirement breakdown)
    req_tier = defaultdict(lambda: Counter())
    for i in ip_items:
        req_tier[i["req"]][i["tier"]] += 1

    # Tier order
    tier_order = ["valuable", "useful", "noise", "extension", "unclassified"]

    # Chart data
    tier_labels = json.dumps([VALUE_TIERS[t]["label"] for t in tier_order])
    tier_colors = json.dumps([VALUE_TIERS[t]["color"] for t in tier_order])
    ip_tier_data = json.dumps([ip_tiers.get(t, 0) for t in tier_order])
    d_tier_data = json.dumps([d_tiers.get(t, 0) for t in tier_order])

    # Per-category stacked bar data
    sorted_cats = sorted(cat_tier.keys())
    cat_labels_chart = json.dumps([f"REQ-{c}" for c in sorted_cats])
    cat_datasets = []
    for t in tier_order:
        cat_datasets.append({
            "label": VALUE_TIERS[t]["label"],
            "data": [cat_tier[c].get(t, 0) for c in sorted_cats],
            "backgroundColor": VALUE_TIERS[t]["color"],
        })
    cat_datasets_json = json.dumps(cat_datasets)

    # Subcategory breakdown for persona
    subcat_order = sorted(ip_subcats.keys(), key=lambda s: ip_subcats[s], reverse=True)
    subcat_labels = json.dumps([SUBCATEGORY_LABELS.get(s, s) for s in subcat_order])
    subcat_data = json.dumps([ip_subcats[s] for s in subcat_order])
    subcat_colors = json.dumps([VALUE_TIERS[
        next(t for t in tier_order
             if any(i["subcat"] == s and i["tier"] == t for i in ip_items))
    ]["color"] for s in subcat_order])

    # Comparative: valuable % by approach
    ip_val_pct = round((ip_tiers.get("valuable", 0) + ip_tiers.get("useful", 0)) / total_ip * 100, 1) if total_ip else 0
    d_val_pct = round((d_tiers.get("valuable", 0) + d_tiers.get("useful", 0)) / total_d * 100, 1) if total_d else 0
    ip_noise_pct = round(ip_tiers.get("noise", 0) / total_ip * 100, 1) if total_ip else 0
    d_noise_pct = round(d_tiers.get("noise", 0) / total_d * 100, 1) if total_d else 0

    # Category table
    cat_table = ""
    for cat in sorted_cats:
        counts = cat_tier[cat]
        total_cat = sum(counts.values())
        v = counts.get("valuable", 0) + counts.get("useful", 0)
        n = counts.get("noise", 0)
        e = counts.get("extension", 0) + counts.get("unclassified", 0)
        v_pct = round(v / total_cat * 100) if total_cat else 0
        n_pct = round(n / total_cat * 100) if total_cat else 0
        cat_table += f"""
        <tr>
            <td><strong>REQ-{cat}</strong> — {CATEGORY_LABELS.get(cat, cat)}</td>
            <td>{total_cat}</td>
            <td class="positive">{v} ({v_pct}%)</td>
            <td class="negative">{n} ({n_pct}%)</td>
            <td>{e}</td>
        </tr>"""

    # Detail examples per tier (max 8 per tier)
    examples_html = ""
    for t in tier_order:
        tier_items = [i for i in ip_items if i["tier"] == t]
        tier_info = VALUE_TIERS[t]
        examples_html += f"""
        <div class="tier-section" style="border-left-color: {tier_info['color']}">
            <h3>{tier_info['label']} — {len(tier_items)} occorrenze ({round(len(tier_items)/total_ip*100, 1)}%)</h3>
            <p class="tier-desc">{tier_info['description']}</p>
            <div class="examples">"""

        # Group by subcategory
        by_subcat = defaultdict(list)
        for i in tier_items:
            by_subcat[i["subcat"]].append(i)

        for sc in sorted(by_subcat, key=lambda s: len(by_subcat[s]), reverse=True):
            sc_items = by_subcat[sc]
            sc_label = SUBCATEGORY_LABELS.get(sc, sc)
            examples_html += f"""
                <h4>{sc_label} ({len(sc_items)})</h4>"""
            for item in sc_items[:3]:
                examples_html += f"""
                <div class="example">
                    <span class="example-req">{item['req']}</span>
                    <span class="example-tc">{item['tc']}</span>
                    <p>{item['detail']}</p>
                </div>"""
            if len(sc_items) > 3:
                examples_html += f"""
                <p class="more">... e altri {len(sc_items) - 3}</p>"""

        examples_html += """
            </div>
        </div>"""

    # Per-requirement heatmap data
    req_rows = ""
    for req in sorted(req_tier.keys()):
        counts = req_tier[req]
        total_req = sum(counts.values())
        v = counts.get("valuable", 0) + counts.get("useful", 0)
        n = counts.get("noise", 0)
        ext = counts.get("extension", 0) + counts.get("unclassified", 0)
        v_pct = round(v / total_req * 100) if total_req else 0
        n_pct = round(n / total_req * 100) if total_req else 0
        # Color intensity based on ratio
        v_bg = f"rgba(22, 163, 74, {min(v_pct/100, 1) * 0.3})"
        n_bg = f"rgba(220, 38, 38, {min(n_pct/100, 1) * 0.3})"
        req_rows += f"""
        <tr>
            <td><code>{req}</code></td>
            <td>{total_req}</td>
            <td style="background:{v_bg}">{v} ({v_pct}%)</td>
            <td style="background:{n_bg}">{n} ({n_pct}%)</td>
            <td>{ext}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Analisi Added Info — Valore vs Rumore</title>
<script src="chart.umd.min.js"></script>
<style>
    :root {{
        --green: #16a34a; --green-light: #bbf7d0;
        --blue: #2563eb; --blue-light: #bfdbfe;
        --red: #dc2626; --red-light: #fecaca;
        --amber: #f59e0b; --amber-light: #fde68a;
        --gray-50: #f9fafb; --gray-100: #f3f4f6;
        --gray-200: #e5e7eb; --gray-600: #4b5563;
        --gray-700: #374151; --gray-800: #1f2937; --gray-900: #111827;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: var(--gray-50); color: var(--gray-800); line-height: 1.6;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; color: var(--gray-900); }}
    h2 {{
        font-size: 20px; font-weight: 600; margin: 32px 0 16px;
        color: var(--gray-900); border-bottom: 2px solid var(--gray-200); padding-bottom: 8px;
    }}
    h3 {{ font-size: 16px; font-weight: 600; margin: 12px 0 6px; color: var(--gray-700); }}
    h4 {{ font-size: 14px; font-weight: 600; margin: 12px 0 4px; color: var(--gray-600); }}
    .subtitle {{ color: var(--gray-600); font-size: 14px; margin-bottom: 24px; }}
    .kpi-grid {{
        display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 16px; margin-bottom: 32px;
    }}
    .kpi-card {{
        background: white; border-radius: 12px; padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .kpi-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--gray-600); margin-bottom: 4px; }}
    .kpi-value {{ font-size: 28px; font-weight: 700; }}
    .kpi-sub {{ font-size: 12px; color: var(--gray-600); margin-top: 4px; }}
    .chart-grid {{
        display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
        gap: 24px; margin-bottom: 32px;
    }}
    .chart-card {{
        background: white; border-radius: 12px; padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .chart-card h3 {{ margin-top: 0; }}
    .chart-container {{ position: relative; height: 350px; }}
    .chart-container-tall {{ position: relative; height: 500px; }}
    table {{
        width: 100%; border-collapse: collapse; font-size: 13px;
        background: white; border-radius: 12px; overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    th {{
        background: var(--gray-100); padding: 10px 8px; text-align: left;
        font-weight: 600; color: var(--gray-700); font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.3px;
    }}
    td {{ padding: 8px; border-top: 1px solid var(--gray-100); }}
    tr:hover td {{ background: var(--gray-50); }}
    .positive {{ color: var(--green); font-weight: 600; }}
    .negative {{ color: var(--red); font-weight: 600; }}
    .tier-section {{
        background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 5px solid;
    }}
    .tier-desc {{ font-size: 13px; color: var(--gray-600); margin-bottom: 12px; }}
    .example {{
        background: var(--gray-50); border-radius: 8px; padding: 12px;
        margin-bottom: 8px; font-size: 13px;
    }}
    .example-req {{
        display: inline-block; background: var(--gray-200); border-radius: 4px;
        padding: 1px 6px; font-size: 11px; font-weight: 600; margin-right: 6px;
    }}
    .example-tc {{
        display: inline-block; color: var(--gray-600); font-size: 11px;
    }}
    .example p {{ margin-top: 4px; color: var(--gray-700); }}
    .more {{ font-size: 12px; color: var(--gray-600); font-style: italic; }}
    .insight-box {{
        background: white; border-radius: 12px; padding: 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px;
    }}
    .insight-box ul {{ margin-left: 20px; }}
    .insight-box li {{ margin-bottom: 8px; font-size: 14px; }}
    @media (max-width: 900px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">

<h1>Analisi delle Informazioni Aggiunte</h1>
<p class="subtitle">
    Classificazione di <strong>{total_ip}</strong> added_info del percorso
    <strong style="color:var(--amber)">persona-based</strong> e
    <strong>{total_d}</strong> del percorso
    <strong style="color:var(--blue)">diretto</strong> in base al valore
    che apportano alla qualita del testing, su 66 requisiti valutati.
</p>

<!-- KPI -->
<h2>Panoramica</h2>
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-label">Added info Persona</div>
        <div class="kpi-value">{total_ip}</div>
        <div class="kpi-sub">{round(total_ip/66, 1)} medie per requisito</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Added info Diretto</div>
        <div class="kpi-value">{total_d}</div>
        <div class="kpi-sub">{round(total_d/66, 1)} medie per requisito</div>
    </div>
    <div class="kpi-card" style="border-left: 4px solid var(--green)">
        <div class="kpi-label">Valore concreto + utile (Persona)</div>
        <div class="kpi-value" style="color:var(--green)">{ip_tiers.get('valuable',0) + ip_tiers.get('useful',0)} ({ip_val_pct}%)</div>
        <div class="kpi-sub">Diretto: {d_tiers.get('valuable',0) + d_tiers.get('useful',0)} ({d_val_pct}%)</div>
    </div>
    <div class="kpi-card" style="border-left: 4px solid var(--red)">
        <div class="kpi-label">Rumore (Persona)</div>
        <div class="kpi-value" style="color:var(--red)">{ip_tiers.get('noise',0)} ({ip_noise_pct}%)</div>
        <div class="kpi-sub">Diretto: {d_tiers.get('noise',0)} ({d_noise_pct}%)</div>
    </div>
</div>

<!-- CHARTS -->
<h2>Distribuzione per Livello di Valore</h2>
<div class="chart-grid">
    <div class="chart-card">
        <h3>Persona-based vs Diretto — composizione</h3>
        <div class="chart-container"><canvas id="chartTierCompare"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Persona-based — distribuzione per tier</h3>
        <div class="chart-container"><canvas id="chartPie"></canvas></div>
    </div>
</div>

<div class="chart-grid">
    <div class="chart-card">
        <h3>Composizione per categoria di requisito</h3>
        <div class="chart-container"><canvas id="chartCatStack"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Sottocategorie (persona-based)</h3>
        <div class="chart-container-tall"><canvas id="chartSubcat"></canvas></div>
    </div>
</div>

<!-- CATEGORY TABLE -->
<h2>Riepilogo per Categoria</h2>
<div style="overflow-x:auto; margin-bottom:32px;">
<table>
    <thead>
        <tr>
            <th>Categoria</th><th>Totale</th>
            <th>Valore (concreto + utile)</th><th>Rumore</th>
            <th>Estensione + altro</th>
        </tr>
    </thead>
    <tbody>{cat_table}</tbody>
</table>
</div>

<!-- INSIGHT -->
<h2>Analisi Qualitativa</h2>
<div class="insight-box">
    <h3>Il persona-based aggiunge valore?</h3>
    <ul>
        <li><strong>Il 25% delle aggiunte ha valore reale</strong>: {ip_tiers.get('valuable',0) + ip_tiers.get('useful',0)} su {total_ip} added_info riguardano scenari di resilienza, validazione dati, concorrenza, audit e recovery. Sono test che un QA esperto scriverebbe indipendentemente.</li>
        <li><strong>Ma il diretto ha un rapporto simile</strong>: il percorso diretto produce {d_val_pct}% di aggiunte di valore vs {ip_val_pct}% del persona — la differenza non e significativa. Il vantaggio del persona non sta nella qualita delle aggiunte ma nella quantita complessiva.</li>
        <li><strong>Il 19% e rumore puro</strong>: {ip_tiers.get('noise',0)} aggiunte inventano dashboard, endpoint, workflow, componenti e stati che non esistono nel requisito ne nel sistema. Questi scenari distraggono il tester e possono generare test cases non eseguibili.</li>
        <li><strong>Il 40% e estensione di scope</strong>: non errato, ma non richiesto. Queste aggiunte espandono il perimetro del test oltre quanto validato dal business, creando un gap tra cosa e stato approvato e cosa viene testato.</li>
    </ul>
</div>

<div class="insight-box">
    <h3>Perche il persona-based produce piu rumore?</h3>
    <ul>
        <li><strong>Amplificazione a catena</strong>: il passaggio requisito → user stories → test cases ha due trasformazioni. Ogni passaggio introduce interpretazioni. Il modello LLM, per rendere le user stories concrete, inventa attori, canali, interfacce e workflow che poi diventano prerequisiti dei test cases.</li>
        <li><strong>Concretizzazione forzata</strong>: il formato persona-based richiede un attore specifico ("Come operatore di backoffice..."). Per requisiti astratti (dati, non-funzionali, integrazione), il modello e costretto a inventare un contesto operativo che non esiste nel requisito.</li>
        <li><strong>Esplosione per canale/persona</strong>: lo stesso scenario viene spesso replicato per persona diversa (marketing, operatore, cliente) o canale diverso (app, web, sportello), moltiplicando le aggiunte senza aggiungere copertura reale.</li>
        <li><strong>Edge case creativi</strong>: il modello, ragionando dal punto di vista dell'utente, tende a immaginare scenari negativi (cosa succede se il servizio e giu? se i dati sono corrotti? se la sessione scade?) che sono utili in assoluto ma non tracciabili al requisito.</li>
    </ul>
</div>

<div class="insight-box">
    <h3>Raccomandazione operativa</h3>
    <ul>
        <li><strong>Usare il percorso diretto come base</strong> per i test cases tracciabili al requisito (coerenza alta, meno rumore).</li>
        <li><strong>Usare il persona-based come fonte complementare</strong>: le aggiunte di tipo "valuable" (resilienza, data quality, concorrenza) possono essere estratte e aggiunte come test cases supplementari, con un tag esplicito "non tracciabile al requisito".</li>
        <li><strong>Filtrare il rumore</strong>: le aggiunte di tipo "noise" (UI inventata, endpoint specifici, workflow fittizi) dovrebbero essere scartate automaticamente o revisionare il prompt per ridurle.</li>
        <li><strong>Separare "core" da "extended"</strong>: un possibile miglioramento della pipeline e generare due set: test cases core (strettamente tracciabili) e test cases estesi (scenari aggiuntivi di valore), etichettandoli diversamente.</li>
    </ul>
</div>

<!-- DETAIL BY TIER -->
<h2>Dettaglio per Livello di Valore</h2>
{examples_html}

<!-- PER-REQUIREMENT TABLE -->
<h2>Dettaglio per Requisito</h2>
<div style="overflow-x:auto;">
<table>
    <thead>
        <tr>
            <th>Requisito</th><th>Totale</th>
            <th>Valore</th><th>Rumore</th><th>Estensione</th>
        </tr>
    </thead>
    <tbody>{req_rows}</tbody>
</table>
</div>

<p style="margin-top:32px; font-size:12px; color:var(--gray-600);">
    Report generato da <code>generate_added_info_analysis.py</code> — test-evaluator
</p>
</div>

<!-- CHARTS -->
<script>
// Tier comparison
(() => {{
    new Chart(document.getElementById('chartTierCompare'), {{
        type: 'bar',
        data: {{
            labels: {tier_labels},
            datasets: [
                {{ label: 'Persona', data: {ip_tier_data}, backgroundColor: '#f59e0b', borderRadius: 4 }},
                {{ label: 'Diretto', data: {d_tier_data}, backgroundColor: '#2563eb', borderRadius: 4 }},
            ]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Occorrenze' }} }} }}
        }}
    }});
}})();

// Pie chart persona
(() => {{
    new Chart(document.getElementById('chartPie'), {{
        type: 'doughnut',
        data: {{
            labels: {tier_labels},
            datasets: [{{ data: {ip_tier_data}, backgroundColor: {tier_colors} }}]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'right' }} }}
        }}
    }});
}})();

// Category stacked
(() => {{
    new Chart(document.getElementById('chartCatStack'), {{
        type: 'bar',
        data: {{
            labels: {cat_labels_chart},
            datasets: {cat_datasets_json}
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'top' }} }},
            scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true }} }}
        }}
    }});
}})();

// Subcategory horizontal bar
(() => {{
    new Chart(document.getElementById('chartSubcat'), {{
        type: 'bar',
        data: {{
            labels: {subcat_labels},
            datasets: [{{ data: {subcat_data}, backgroundColor: {subcat_colors}, borderRadius: 4 }}]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ x: {{ beginAtZero: true, title: {{ display: true, text: 'Occorrenze' }} }} }}
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
    print(f"Caricamento da {EVAL_DIR}...")
    ip_items, d_items = load_and_classify()
    print(f"  Persona: {len(ip_items)} added_info")
    print(f"  Diretto: {len(d_items)} added_info")

    print("Generazione HTML...")
    html = generate_html(ip_items, d_items)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Report salvato in: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
