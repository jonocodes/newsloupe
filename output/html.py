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
        should_read = r.max_score >= read_threshold
        read_symbol = "✓" if should_read else "✗"
        read_class = "read-yes" if should_read else "read-no"

        # Build score badges
        ml_badge = ""
        if r.ml_score is not None:
            ml_pct = int(r.ml_score * 100)
            ml_badge = f'<span class="score-badge ml" title="ML click probability">ML {ml_pct}%</span>'

        rows.append(f"""
        <tr data-object-id="{r.story.object_id}">
          <td class="rank">{i}.</td>
          <td class="title-cell">
            <div class="title-line">
              <a href="{r.story.url}" target="_blank" class="article-link" data-object-id="{r.story.object_id}">{r.story.title}</a>
            </div>
            <div class="subtext">
              <span class="score-badge tfidf" title="TF-IDF: {r.tfidf_score:.3f}">TF {int(r.tfidf_score * 100)}%</span>
              <span class="score-badge embed" title="Embedding: {r.embedding_score:.3f}">EM {int(r.embedding_score * 100)}%</span>
              {ml_badge}
              <span class="{read_class}" title="Top 25%">{read_symbol}</span>
              <span class="sep">|</span>
              <a href="{r.story.hn_url}" target="_blank" class="discuss">discuss</a>
              <span class="sep">|</span>
              <span class="hn-meta">{r.story.points} pts · {r.story.num_comments} comments</span>
            </div>
          </td>
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
  body {{ font-family: Verdana, Geneva, sans-serif; background: #f6f6ef; color: #000; padding: 0; margin: 0; }}

  .header {{ background: #ff6600; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-size: 14px; font-weight: bold; color: #000; margin: 0; }}
  .header-controls {{ display: flex; align-items: center; gap: 8px; }}
  #rescore-btn {{ padding: 4px 10px; background: #fff; border: 1px solid #ccc; border-radius: 3px; cursor: pointer; font-size: 11px; font-family: Verdana, Geneva, sans-serif; }}
  #rescore-btn:hover {{ background: #f0f0f0; }}
  #rescore-msg {{ font-size: 11px; color: #fff; }}

  .meta {{ background: #f6f6ef; padding: 6px 12px; border-bottom: 1px solid #ff6600; font-size: 10px; color: #828282; }}
  .meta-item {{ display: inline; margin-right: 12px; }}

  .legend {{ background: #ffffd8; border: 1px solid #ff6600; padding: 8px 12px; margin: 12px; font-size: 10px; color: #000; line-height: 1.6; }}
  .legend-item {{ display: inline; margin-right: 16px; }}
  .legend-item strong {{ font-weight: bold; }}

  table {{ width: 100%; border-collapse: collapse; background: #f6f6ef; }}
  tbody tr {{ background: #f6f6ef; }}
  tbody tr:hover {{ background: #ffffd8; }}

  td {{ padding: 4px 8px; vertical-align: top; border-bottom: 1px solid #e8e8e8; }}
  .rank {{ color: #828282; font-size: 11px; text-align: right; padding-right: 6px; width: 30px; }}

  .title-cell {{ padding: 6px 8px; }}
  .title-line {{ margin-bottom: 4px; }}
  .article-link {{ color: #000; text-decoration: none; font-size: 11pt; line-height: 1.4; }}
  .article-link:visited {{ color: #828282; }}
  .article-link:hover {{ text-decoration: underline; }}

  .subtext {{ font-size: 9pt; color: #828282; line-height: 1.6; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
  .subtext a {{ color: #828282; text-decoration: none; }}
  .subtext a:hover {{ text-decoration: underline; }}
  .sep {{ color: #ccc; }}

  .score-badge {{ display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 9px; font-weight: bold; white-space: nowrap; }}
  .score-badge.tfidf {{ background: #d4edda; color: #155724; }}
  .score-badge.embed {{ background: #d1ecf1; color: #0c5460; }}
  .score-badge.ml {{ background: #fff3cd; color: #856404; }}

  .read-yes {{ color: #2d8a2d; font-weight: bold; font-size: 11px; }}
  .read-no {{ color: #ccc; font-size: 11px; }}

  .hn-meta {{ color: #828282; font-size: 9pt; }}
  .discuss {{ color: #828282 !important; }}

  @media (max-width: 768px) {{
    body {{ font-size: 12px; }}
    .header {{ padding: 6px 8px; }}
    h1 {{ font-size: 12px; }}
    .rank {{ display: none; }}
    .title-cell {{ padding: 8px 6px; }}
    .article-link {{ font-size: 11px; }}
    .subtext {{ font-size: 8pt; gap: 4px; }}
    .score-badge {{ font-size: 8px; padding: 1px 4px; }}
    .legend {{ margin: 8px; padding: 6px 8px; font-size: 9px; }}
    .legend-item {{ display: block; margin-right: 0; }}
  }}

  @media print {{ #rescore-btn, .legend {{ display: none; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>newsloupe</h1>
  <div class="header-controls">
    {rescore_button_html}
    <span id="rescore-msg"></span>
  </div>
</div>
<div class="meta">
  <span class="meta-item">Updated: {ts}</span>
  <span class="meta-item">Source: {source}</span>
  <span class="meta-item">Stories: {len(sorted_results)}</span>
</div>
<div class="legend">
  <span class="legend-item"><strong>TF</strong>=keyword match</span>
  <span class="legend-item"><strong>EM</strong>=semantic similarity</span>
  <span class="legend-item"><strong>ML</strong>=predicted click probability</span>
  <span class="legend-item"><strong>✓</strong>=top 25%</span>
</div>
<table id="results-table">
  <tbody>
    {rows_html}
  </tbody>
</table>
<script>
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

// Track clicks on article links (including right-click and middle-click)
document.addEventListener("DOMContentLoaded", function() {{
  function trackClick(objectId) {{
    if (!objectId) return;
    fetch("/api/click", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{object_id: objectId}}),
      keepalive: true
    }}).catch(function(err) {{
      console.error("Failed to track click:", err);
    }});
  }}

  document.querySelectorAll("a.article-link").forEach(function(link) {{
    var objectId = link.getAttribute("data-object-id");

    // Track left-click and middle-click
    link.addEventListener("click", function(e) {{
      trackClick(objectId);
    }});

    // Track right-click (context menu)
    link.addEventListener("contextmenu", function(e) {{
      trackClick(objectId);
    }});

    // Track auxiliary button clicks (middle-click, back/forward buttons)
    link.addEventListener("auxclick", function(e) {{
      trackClick(objectId);
    }});
  }});
}});
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
