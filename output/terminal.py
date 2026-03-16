from datetime import date
from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text


def _score_color(score: float) -> str:
    if score >= 0.5:
        return "green"
    elif score >= 0.25:
        return "yellow"
    else:
        return "dim"


def _fmt_score(score: float) -> Text:
    color = _score_color(score)
    return Text(f"{score:.2f}", style=color)


def _fmt_delta(delta: float) -> Text:
    color = "green" if delta >= 0 else "red"
    sign = "+" if delta >= 0 else ""
    return Text(f"{sign}{delta:.2f}", style=color)


def render_terminal(results, sort_by: str = "hn", read_threshold: float = 0.3):
    if sort_by == "hn":
        sorted_results = list(results)
    else:
        sort_key = {
            "tfidf": lambda r: r.tfidf_score,
            "embed": lambda r: r.embedding_score,
            "max": lambda r: r.max_score,
        }[sort_by]
        sorted_results = sorted(results, key=sort_key, reverse=True)

    console = Console()
    today = date.today().strftime("%Y-%m-%d")
    console.print(f"\n[bold]HN Front Page — Scored Against Your Interests ({today})[/bold]\n")

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Title", max_width=60)
    table.add_column("TF-IDF", width=7, justify="right")
    table.add_column("Embed", width=7, justify="right")
    table.add_column("Δ", width=7, justify="right")
    table.add_column("Read", width=5, justify="center")
    table.add_column("HN Link", max_width=40)

    for i, r in enumerate(sorted_results, 1):
        title = r.story.title[:60] if len(r.story.title) > 60 else r.story.title
        hn_link = r.story.hn_url[:40] if len(r.story.hn_url) > 40 else r.story.hn_url
        should_read = r.max_score >= read_threshold
        read_cell = Text("✓", style="bold green") if should_read else Text("✗", style="dim red")
        table.add_row(
            str(i),
            title,
            _fmt_score(r.tfidf_score),
            _fmt_score(r.embedding_score),
            _fmt_delta(r.delta),
            read_cell,
            hn_link,
        )

    console.print(table)
