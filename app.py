import os
import tempfile
from typing import Optional

from flask import Flask, Response, flash, redirect, render_template_string, request, send_file, url_for
from uuid import uuid4

import vertical_analysis
from orchestra_signals_engine import process_signals


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# In-memory download registry (token -> (path, suggested_filename))
DOWNLOADS = {}


INDEX_HTML = """
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>The Orchestra Earned Media Diagnostic System – ReputeAI</title>
    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
    <link href=\"https://fonts.googleapis.com/css2?family=Lato:wght@700;900&family=Poppins:wght@400;500&display=swap\" rel=\"stylesheet\">
    <style>
      :root {
        --text: #1c2d50;       /* Dark Blue */
        --accent: #fc5f36;     /* Dark Orange */
        --border: #808080;     /* Medium Gray */
        --bg: #ffffff;         /* White */
      }
      * { box-sizing: border-box; }
      body {
        margin: 0; padding: 0; background: var(--bg); color: var(--text);
        font-family: 'Poppins', system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      }
      .bar { height: 6px; background: var(--accent); }
      .wrap { max-width: 980px; margin: 32px auto; padding: 0 20px; }
      .hero { display: flex; align-items: center; gap: 16px; margin-bottom: 8px; }
      .logo { width: 56px; height: 56px; border-radius: 12px; object-fit: cover; }
      h1 { font-family: 'Lato', sans-serif; font-weight: 900; font-size: 32px; margin: 0; }
      .sub { margin: 6px 0 18px; color: #6b7280; font-size: 16px; }
      .card { border: 1px solid #eee; border-radius: 12px; padding: 18px; }
      .note { color: #6b7280; font-size: 14px; margin-bottom: 12px; }
      .grid { display: grid; grid-template-columns: 1fr; gap: 14px; }
      label { font-weight: 600; font-family: 'Lato', sans-serif; }
      input[type=file] { margin-top: 6px; }
      .row { margin-top: 12px; }
      .btn { background: var(--accent); color: #fff; border: none; padding: 10px 14px; border-radius: 8px; cursor: pointer; }
      .btn:disabled { opacity: .6; cursor: not-allowed; }
      .messages { margin-bottom: 8px; }
      .messages .error { color: #991b1b; }
      .messages .success { color: #065f46; }
      .divider { border-top: 1px solid #eee; margin: 18px 0; }
      footer { color: #6b7280; font-size: 12px; margin-top: 24px; }
    </style>
  </head>
  <body>
    <div class=\"bar\"></div>
    <main class=\"wrap\">
      <section class=\"hero\">
        <img class=\"logo\" src=\"{{ url_for('logo') }}\" alt=\"ReputeAI Logo\" />
        <div>
          <h1>The Orchestra Earned Media Diagnostic System</h1>
          <div class=\"sub\">Analysis powered by ReputeAI</div>
        </div>
      </section>

      <section class=\"card\">
        <div class=\"messages\">
          {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
              {% for category, message in messages %}
                <div class=\"{{ category }}\">{{ message }}</div>
              {% endfor %}
            {% endif %}
          {% endwith %}
        </div>

        <p class=\"note\">Upload a CSV, then click Start Analysis. When processing finishes you'll see Pass 1 and Pass 2 download buttons.</p>
        <div class=\"divider\"></div>
        <form method=\"post\" action=\"{{ url_for('process_both') }}\" enctype=\"multipart/form-data\">
          <div class=\"grid\">
            <div>
              <label for=\"csv\">CSV File</label><br/>
              <input id=\"csv\" type=\"file\" name=\"file\" accept=\".csv\" required />
            </div>
          </div>
          <div class=\"row\">
            <button class=\"btn\" type=\"submit\">Start Analysis</button>
          </div>
        </form>
      </section>

      
    </main>
  </body>
  </html>
"""

DOWNLOAD_HTML = """
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Download Results</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
      .msg { font-weight: 700; margin-bottom: 12px; }
      .note { color: #6b7280; margin-top: 8px; }
      .btn { background: #fc5f36; color: #fff; border: none; padding: 10px 14px; border-radius: 8px; cursor: pointer; text-decoration: none; }
    </style>
    <script>
      window.addEventListener('DOMContentLoaded', function(){
        const a = document.getElementById('autodl');
        if (a) a.click();
      });
    </script>
  </head>
  <body>
    <div class=\"msg\">{{ message }}</div>
    <a id=\"autodl\" class=\"btn\" href=\"{{ url_for('download_token', token=token) }}\">Download CSV</a>
    <div class=\"note\">If your download doesn't start automatically, click the button.</div>
  </body>
  </html>
"""


@app.get("/")
def index() -> Response:
    return render_template_string(INDEX_HTML)


@app.post("/process/both")
def process_both() -> Response:
    uploaded = request.files.get("file")
    if not uploaded or uploaded.filename == "":
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("index"))

    # Save to a temp file
    suffix = "_input.csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        uploaded.save(tmp.name)
        tmp_path = tmp.name

    try:
        out_path1 = vertical_analysis.process(tmp_path)
    except Exception as e:
        flash(f"Processing failed: {e}", "error")
        return redirect(url_for("index"))

    if not out_path1 or not os.path.exists(out_path1):
        flash("No output produced.", "error")
        return redirect(url_for("index"))

    # Run Pass 2 (signals) using same upload
    try:
        out_path2 = process_signals(tmp_path)
    except Exception as e:
        flash(f"Signals processing failed: {e}", "error")
        return redirect(url_for("index"))

    if not out_path2 or not os.path.exists(out_path2):
        flash("No signals output produced.", "error")
        return redirect(url_for("index"))

    # Register both downloads with clear names
    token1 = uuid4().hex
    token2 = uuid4().hex
    DOWNLOADS[token1] = (out_path1, f"Pass1_{os.path.basename(out_path1)}")
    DOWNLOADS[token2] = (out_path2, f"Pass2_{os.path.basename(out_path2)}")

    # Render a page with both buttons
    html = f"""
    <!doctype html><html><head>
      <meta charset='utf-8'/><title>Analysis Complete</title>
      <style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem}}
      .done{{font-weight:700;margin:4px 0 12px}} .row{{margin:.75rem 0}}
      .btn{{background:#fc5f36;color:#fff;border:none;padding:10px 14px;border-radius:8px;text-decoration:none}}
      </style>
    </head><body>
      <div class='done'>… Pass 1 Complete</div>
      <div class='row'><a class='btn' href='{{{{ url_for('download_token', token="{token1}") }}}}'>Download Pass 1 CSV</a></div>
      <div class='done'>… Pass 2 Complete</div>
      <div class='row'><a class='btn' href='{{{{ url_for('download_token', token="{token2}") }}}}'>Download Pass 2 CSV</a></div>
    </body></html>
    """
    return render_template_string(html)


@app.post("/process/pass2")
def process_pass2() -> Response:
    uploaded = request.files.get("file")
    if not uploaded or uploaded.filename == "":
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("index"))

    suffix = "_input.csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        uploaded.save(tmp.name)
        tmp_path = tmp.name

    try:
        out_path = process_signals(tmp_path)
    except Exception as e:
        flash(f"Processing failed: {e}", "error")
        return redirect(url_for("index"))

    if not out_path or not os.path.exists(out_path):
        flash("No output produced.", "error")
        return redirect(url_for("index"))

    base_in = os.path.basename(out_path)
    suggest_name = f"Pass2_{base_in}"
    token = uuid4().hex
    DOWNLOADS[token] = (out_path, suggest_name)
    return render_template_string(DOWNLOAD_HTML, message="Pass 2 Complete", token=token)


@app.get("/download/<token>")
def download_token(token: str) -> Response:
    item = DOWNLOADS.pop(token, None)
    if not item:
        flash("Download expired or invalid.", "error")
        return redirect(url_for("index"))
    path, suggest = item
    if not os.path.exists(path):
        flash("File not found.", "error")
        return redirect(url_for("index"))
    return send_file(path, mimetype="text/csv", as_attachment=True, download_name=suggest)


@app.get("/logo")
def logo() -> Response:
    # Serve the Repute logo stored in project root
    path = os.path.join(os.path.dirname(__file__), "Repute Logo Only No Text.jpg")
    if os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    # Fallback: simple 1x1 pixel if logo not found
    return Response(status=404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)


