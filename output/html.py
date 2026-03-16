import sys
from datetime import datetime


def _score_bg(score: float) -> str:
    r = int(255 - score * 100)
    g = int(200 + score * 55)
    b = int(200 - score * 150)
    return f"rgb({r},{g},{b})"


def render_html_string(
    results,
    sort_by: str = "hn",
    last_updated: datetime = None,
    include_rescore_button: bool = False,
    read_threshold: float = 0.3,
    source: str = "scraper",
) -> str:
    if sort_by == "hn":
        sorted_results = list(results)
    else:
        sort_key = {
            "tfidf": lambda r: r.tfidf_score,
            "embed": lambda r: r.embedding_score,
            "max": lambda r: r.max_score,
        }[sort_by]
        sorted_results = sorted(results, key=sort_key, reverse=True)
    ts = (last_updated or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

    rescore_button_html = ""
    if include_rescore_button:
        rescore_button_html = """
        <button id="rescore-btn" onclick="rescore()">Re-score</button>
"""

    rows = []
    for i, r in enumerate(sorted_results, 1):
        tfidf_bg = _score_bg(r.tfidf_score)
        embed_bg = _score_bg(r.embedding_score)
        delta_color = "#2d8a2d" if r.delta >= 0 else "#c0392b"
        sign = "+" if r.delta >= 0 else ""
        tfidf_bar = int(r.tfidf_score * 60)
        embed_bar = int(r.embedding_score * 60)
        should_read = r.max_score >= read_threshold
        read_symbol = "✓" if should_read else "✗"
        read_style = "color:#2d8a2d;font-weight:bold" if should_read else "color:#bbb"
        rows.append(f"""
        <tr>
          <td class="rank">{i}</td>
          <td><a href="{r.story.url}" target="_blank">{r.story.title}</a></td>
          <td style="background:{tfidf_bg}">
            <div class="score-cell">
              <span>{r.tfidf_score:.2f}</span>
              <div class="bar" style="width:{tfidf_bar}px"></div>
            </div>
          </td>
          <td style="background:{embed_bg}">
            <div class="score-cell">
              <span>{r.embedding_score:.2f}</span>
              <div class="bar" style="width:{embed_bar}px"></div>
            </div>
          </td>
          <td style="color:{delta_color}">{sign}{r.delta:.2f}</td>
          <td style="{read_style};text-align:center">{read_symbol}</td>
          <td><a href="{r.story.hn_url}" target="_blank">discuss</a></td>
        </tr>""")

    rows_html = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>newsloupe — HN Scored</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; color: #222; padding: 20px; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-size: 1.2rem; font-weight: 600; }}
  .ts {{ color: #666; font-size: 0.85rem; }}
  #rescore-btn {{ padding: 6px 14px; background: #f0f0f0; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }}
  #rescore-btn:hover {{ background: #e0e0e0; }}
  #rescore-msg {{ font-size: 0.85rem; color: #666; margin-left: 8px; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  thead th {{ background: #222; color: white; padding: 10px 12px; text-align: left; cursor: pointer; user-select: none; white-space: nowrap; position: sticky; top: 0; }}
  thead th:hover {{ background: #444; }}
  tbody tr:nth-child(even) {{ background: #fafafa; }}
  tbody tr:hover {{ background: #eef4ff; }}
  td {{ padding: 8px 12px; font-size: 0.875rem; vertical-align: middle; }}
  td a {{ color: #1a73e8; text-decoration: none; }}
  td a:hover {{ text-decoration: underline; }}
  .rank {{ color: #999; width: 36px; text-align: right; }}
  .score-cell {{ display: flex; align-items: center; gap: 6px; }}
  .bar {{ height: 6px; background: #2d8a2d; border-radius: 2px; flex-shrink: 0; }}
  .meta {{ display: flex; gap: 16px; align-items: baseline; flex-wrap: wrap; margin-top: 4px; }}
  .meta-item {{ font-size: 0.8rem; color: #888; }}
  .meta-item span {{ color: #444; font-weight: 500; }}
  .legend {{ background: white; border-radius: 6px; padding: 12px 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-size: 0.82rem; color: #555; display: flex; gap: 24px; flex-wrap: wrap; }}
  .legend-item strong {{ color: #222; }}
  @media print {{ #rescore-btn {{ display: none; }} }}
  @media (max-width: 600px) {{ td, th {{ padding: 6px 8px; font-size: 0.8rem; }} .legend {{ gap: 12px; }} }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>newsloupe</h1>
    <div class="meta">
      <div class="meta-item">Updated: <span>{ts}</span></div>
      <div class="meta-item">Source: <span>{source}</span></div>
      <div class="meta-item">Stories: <span>{len(sorted_results)}</span></div>
    </div>
  </div>
  <div style="display:flex;align-items:center">
    {rescore_button_html}
    <span id="rescore-msg"></span>
  </div>
</div>
<div class="legend">
  <div class="legend-item"><strong>TF-IDF</strong> — keyword overlap between the article title and your interests. Fast and literal.</div>
  <div class="legend-item"><strong>Embed</strong> — semantic similarity via sentence embeddings. Catches meaning even when words differ.</div>
  <div class="legend-item"><strong>Δ</strong> — embed minus TF-IDF. Large positive means embeddings found a match keywords missed.</div>
  <div class="legend-item"><strong>Read</strong> — ✓ if score is in the top 25% of today's articles.</div>
</div>
<div class="table-wrap">
<table id="results-table">
  <thead>
    <tr>
      <th onclick="sortTable(0)">#</th>
      <th onclick="sortTable(1)">Title</th>
      <th onclick="sortTable(2)">TF-IDF</th>
      <th onclick="sortTable(3)">Embed</th>
      <th onclick="sortTable(4)">Δ</th>
      <th onclick="sortTable(5)">Read</th>
      <th>HN</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
</div>
<script>
var sortDir = {{}};
function sortTable(col) {{
  var table = document.getElementById("results-table");
  var tbody = table.tBodies[0];
  var rows = Array.from(tbody.rows);
  sortDir[col] = !sortDir[col];
  rows.sort(function(a, b) {{
    var av = a.cells[col].innerText.trim();
    var bv = b.cells[col].innerText.trim();
    var an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return sortDir[col] ? bn - an : an - bn;
    return sortDir[col] ? av.localeCompare(bv) : bv.localeCompare(av);
  }});
  rows.forEach(function(r) {{ tbody.appendChild(r); }});
}}
function rescore() {{
  var btn = document.getElementById("rescore-btn");
  var msg = document.getElementById("rescore-msg");
  btn.disabled = true;
  btn.textContent = "Scoring...";
  msg.textContent = "";
  fetch("/rescore", {{method: "POST"}})
    .then(function(r) {{ if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }})
    .then(function() {{ location.reload(); }})
    .catch(function(e) {{
      msg.textContent = "Error: " + e.message;
      btn.disabled = false;
      btn.textContent = "Re-score";
    }});
}}
</script>
</body>
</html>"""


def render_html(results, output_path: str = "output.html", sort_by: str = "max", read_threshold: float = 0.3):
    html = render_html_string(results, sort_by=sort_by, include_rescore_button=False, read_threshold=read_threshold)
    try:
        with open(output_path, "w") as f:
            f.write(html)
    except OSError as e:
        print(f"Error: cannot write HTML to {output_path}: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"HTML report written to {output_path}", file=sys.stderr)
