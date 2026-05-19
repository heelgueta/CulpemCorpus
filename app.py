import csv
import json
import logging
import os
import uuid
from flask import Flask, Response, jsonify, render_template, request, send_file
from flask import stream_with_context

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = Flask(__name__)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ARTICLE_FIELDS = ["source", "date", "title", "url", "body_text", "section"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scrape")
def scrape():
    sources = request.args.getlist("sources")
    query = request.args.get("query", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    fmt = request.args.get("format", "csv")
    delay = float(request.args.get("delay", "1.5"))

    if not sources:
        return jsonify({"error": "No sources selected"}), 400

    from scrapers import get_scraper

    def generate():
        articles = []
        fail_count = 0

        for source_id in sources:
            scraper = get_scraper(source_id)
            if not scraper:
                yield _sse({"type": "log", "level": "error", "msg": f"Unknown source: {source_id}"})
                continue

            yield _sse({"type": "log", "level": "info", "msg": f"▶ Starting {scraper.name}"})

            count_before = len(articles)
            try:
                for event in scraper.run(
                    query=query,
                    date_from=date_from,
                    date_to=date_to,
                    delay=delay,
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
                yield _sse({"type": "log", "level": "error", "msg": f"Scraper crashed: {e}"})

            source_count = len(articles) - count_before
            yield _sse({
                "type": "log", "level": "info",
                "msg": f"  ✓ {scraper.name}: {source_count} articles collected",
            })

        if not articles:
            yield _sse({"type": "done", "count": 0, "file": None, "fails": fail_count})
            return

        # Write output file
        job_id = uuid.uuid4().hex[:10]
        if fmt == "jsonl":
            filename = f"culpem_{job_id}.jsonl"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                for a in articles:
                    row = {k: a.get(k, "") for k in ARTICLE_FIELDS}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            filename = f"culpem_{job_id}.csv"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=ARTICLE_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for a in articles:
                    writer.writerow({k: a.get(k, "") for k in ARTICLE_FIELDS})

        yield _sse({"type": "done", "count": len(articles), "file": filename, "fails": fail_count})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download/<filename>")
def download(filename):
    if not filename.startswith("culpem_") or ".." in filename or "/" in filename:
        return "Not found", 404
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return "Not found", 404
    return send_file(filepath, as_attachment=True)


def _sse(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True)
