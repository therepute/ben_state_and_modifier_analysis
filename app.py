import os
import tempfile
from typing import Optional

from flask import Flask, Response, flash, redirect, render_template_string, request, send_file, url_for

import vertical_analysis


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")


INDEX_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Orchestra Vertical Analysis</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
      .card { border: 1px solid #eee; border-radius: 10px; padding: 1.5rem; max-width: 800px; }
      .row { margin-top: 1rem; }
      .btn { background: #111827; color: #fff; border: none; padding: 0.6rem 1rem; border-radius: 6px; cursor: pointer; }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .note { color: #6b7280; font-size: 0.9rem; }
      .success { color: #065f46; }
      .error { color: #991b1b; }
    </style>
  </head>
  <body>
    <h1>Orchestra Vertical Analysis</h1>
    <p class="note">Upload a CSV, then click Run to generate an enriched CSV with states, modifiers, and validation fields.</p>
    <div class="card">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          <div class="row">
            {% for category, message in messages %}
              <div class="{{ category }}">{{ message }}</div>
            {% endfor %}
          </div>
        {% endif %}
      {% endwith %}
      <form method="post" action="{{ url_for('process_upload') }}" enctype="multipart/form-data">
        <div class="row">
          <label for="csv">CSV File</label><br/>
          <input id="csv" type="file" name="file" accept=".csv" required />
        </div>
        <div class="row">
          <button class="btn" type="submit">Run Vertical Analysis</button>
        </div>
      </form>
    </div>
  </body>
  </html>
"""


@app.get("/")
def index() -> Response:
    return render_template_string(INDEX_HTML)


@app.post("/process")
def process_upload() -> Response:
    uploaded = request.files.get("file")
    if not uploaded or uploaded.filename == "":
        flash("error|Please upload a CSV file.")
        return redirect(url_for("index"))

    # Save to a temp file
    suffix = "_input.csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        uploaded.save(tmp.name)
        tmp_path = tmp.name

    try:
        out_path = vertical_analysis.process(tmp_path)
    except Exception as e:
        flash(("error", f"Processing failed: {e}"))
        return redirect(url_for("index"))

    if not out_path or not os.path.exists(out_path):
        flash(("error", "No output produced."))
        return redirect(url_for("index"))

    base_name = os.path.basename(out_path)
    return send_file(out_path, mimetype="text/csv", as_attachment=True, download_name=base_name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)


