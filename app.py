import csv
import json
import logging
import os
import re
import uuid
from flask import Flask, Response, jsonify, render_template, request, send_file
from flask import stream_with_context

import local_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = Flask(__name__)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ARTICLE_FIELDS = ["source", "date", "title", "url", "body_text", "section"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/yene_status")
def yene_status():
    """Return local DB coverage for all known sources — used by the UI."""
    from scrapers import _SCRAPERS
    result = {}
    for source_id in _SCRAPERS:
        cov = local_db.coverage(source_id)
        if cov:
            result[source_id] = {"min": cov[0], "max": cov[1], "count": cov[2]}
        else:
            result[source_id] = None
    return jsonify(result)


@app.route("/scrape")
def scrape():
    sources   = request.args.getlist("sources")
    query     = request.args.get("query", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to", "").strip()
    fmt       = request.args.get("format", "csv")
    delay     = float(request.args.get("delay", "1.5"))
    use_local = request.args.get("use_local", "1") == "1"

    if not sources:
        return jsonify({"error": "No sources selected"}), 400

    from scrapers import get_scraper

    def generate():
        articles   = []
        fail_count = 0

        for source_id in sources:
            scraper = get_scraper(source_id)
            if not scraper:
                yield _sse({"type": "log", "level": "error",
                            "msg": f"Unknown source: {source_id}"})
                continue

            # ── try local archive first ───────────────────────────────────────
            used_local = False
            if use_local:
                cov = local_db.coverage(source_id)
                if cov:
                    db_min, db_max, db_count = cov

                    # Determine if the requested range is inside the DB
                    req_from = date_from or db_min
                    req_to   = date_to   or db_max
                    in_range = (db_min <= req_from and db_max >= req_to)
                    partial  = not in_range and not (req_to < db_min or req_from > db_max)

                    if in_range or partial:
                        tag = "local archive" if in_range else "local archive (partial)"
                        yield _sse({
                            "type": "log", "level": "info",
                            "msg": (
                                f"▶ {scraper.name} — using {tag} "
                                f"(DB: {db_min} → {db_max}, {db_count:,} art.)"
                                + (f"  ⚠ requested from {req_from}, DB starts {db_min}"
                                   if partial and req_from < db_min else "")
                            ),
                        })

                        count_before = len(articles)
                        for art in local_db.query(source_id, query, date_from, date_to):
                            articles.append(art)
                            yield _sse({
                                "type": "progress",
                                "source": source_id,
                                "total": len(articles),
                                "title": art.get("title", "")[:90],
                            })

                        source_count = len(articles) - count_before
                        fts_note = " (FTS5)" if query and local_db.has_fts(source_id) else ""
                        yield _sse({
                            "type": "log", "level": "info",
                            "msg": f"  ✓ {scraper.name}: {source_count} articles (local{fts_note})",
                        })
                        used_local = True

            # ── fall back to online scraping ──────────────────────────────────
            if not used_local:
                if use_local:
                    yield _sse({"type": "log", "level": "info",
                                "msg": f"▶ {scraper.name} — no local archive, scraping online"})
                else:
                    yield _sse({"type": "log", "level": "info",
                                "msg": f"▶ {scraper.name}"})

                count_before = len(articles)
                try:
                    for event in scraper.run(
                        query=query, date_from=date_from,
                        date_to=date_to, delay=delay,
                    ):
                        if event.get("type") == "article":
                            articles.append(event["data"])
                            yield _sse({
                                "type": "progress",
                                "source": source_id,
                                "total": len(articles),
                                "title": event["data"].get("title", "")[:90],
                            })
                        elif event.get("type") == "fail":
                            fail_count += 1
                            yield _sse({"type": "log", "level": "warn",
                                        "msg": f"  ✗ {event.get('url', '')}"})
                        elif event.get("type") == "log":
                            yield _sse(event)
                except Exception as e:
                    app.logger.exception("Scraper error for %s", source_id)
                    yield _sse({"type": "log", "level": "error",
                                "msg": f"Scraper crashed: {e}"})

                source_count = len(articles) - count_before
                yield _sse({
                    "type": "log", "level": "info",
                    "msg": f"  ✓ {scraper.name}: {source_count} articles",
                })

        # ── write output ──────────────────────────────────────────────────────
        if not articles:
            yield _sse({"type": "done", "count": 0, "file": None, "fails": fail_count})
            return

        def clean_row(a):
            row = {k: a.get(k, "") for k in ARTICLE_FIELDS}
            # Collapse any whitespace (including \n from API excerpts stored in Yene DBs)
            row["body_text"] = re.sub(r"\s+", " ", row["body_text"]).strip()
            return row

        job_id     = uuid.uuid4().hex[:10]
        query_slug = re.sub(r"[^\w]+", "_", query.strip())[:40].strip("_") if query.strip() else "sin_query"
        base_name  = f"culpem_{query_slug}_{job_id}"

        if fmt == "jsonl":
            filename = f"{base_name}.jsonl"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                for a in articles:
                    f.write(json.dumps(clean_row(a), ensure_ascii=False) + "\n")
        else:
            filename = f"{base_name}.csv"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=ARTICLE_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for a in articles:
                    writer.writerow(clean_row(a))

        import datetime
        meta = {
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
            "query":      query,
            "sources":    sources,
            "date_from":  date_from or None,
            "date_to":    date_to   or None,
            "format":     fmt,
            "n_articles": len(articles),
            "n_failed":   fail_count,
            "file":       filename,
        }
        with open(os.path.join(OUTPUT_DIR, f"{base_name}.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        yield _sse({"type": "done", "count": len(articles),
                    "file": filename, "fails": fail_count})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download/<filename>")
def download(filename):
    if not filename.startswith("culpem_") or ".." in filename or "/" in filename:
        return "Not found", 404
    if not filename.endswith((".csv", ".jsonl", ".json")):
        return "Not found", 404
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return "Not found", 404
    return send_file(filepath, as_attachment=True)


def _sse(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True)
