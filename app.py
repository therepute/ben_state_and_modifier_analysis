import os
import tempfile
from typing import Optional

from flask import Flask, Response, flash, redirect, render_template_string, request, send_file, url_for

import vertical_analysis


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")


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

        <p class=\"note\">Upload a CSV, then click Run to generate an enriched CSV with states, modifiers, and validation fields.</p>
        <div class=\"divider\"></div>
        <form method=\"post\" action=\"{{ url_for('process_upload') }}\" enctype=\"multipart/form-data\">
          <div class=\"grid\">
            <div>
              <label for=\"csv\">CSV File</label><br/>
              <input id=\"csv\" type=\"file\" name=\"file\" accept=\".csv\" required />
            </div>
          </div>
          <div class=\"row\">
            <button class=\"btn\" type=\"submit\">Run Vertical Analysis</button>
          </div>
        </form>
      </section>

      
    </main>
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
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("index"))

    # Save to a temp file
    suffix = "_input.csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        uploaded.save(tmp.name)
        tmp_path = tmp.name

    try:
        out_path = vertical_analysis.process(tmp_path)
    except Exception as e:
        flash(f"Processing failed: {e}", "error")
        return redirect(url_for("index"))

    if not out_path or not os.path.exists(out_path):
        flash("No output produced.", "error")
        return redirect(url_for("index"))

    base_name = os.path.basename(out_path)
    return send_file(out_path, mimetype="text/csv", as_attachment=True, download_name=base_name)


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


