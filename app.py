import os
import tempfile
from typing import Optional

from flask import Flask, Response, flash, redirect, render_template_string, request, send_file, url_for, jsonify
from uuid import uuid4
import threading

import vertical_analysis
from orchestra_signals_engine import process_signals


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# In-memory registries (simple, volatile)
# Uploads: upload_token -> tmp_path
UPLOADS: dict[str, str] = {}
# Downloads: download_token -> (file_path, suggested_filename)
DOWNLOADS: dict[str, tuple[str, str]] = {}
# Pass2 jobs: up_token -> {status: str, dl_token: str | None, error: str | None}
PASS2_JOBS: dict[str, dict] = {}


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

        <p class=\"note\">Upload a CSV, then run Pass 1 (states/modifiers) and Pass 2 (signals) as independent steps.</p>
        <div class=\"divider\"></div>
        <form method=\"post\" action=\"{{ url_for('upload') }}\" enctype=\"multipart/form-data\">
          <label for=\"csv\">CSV File</label><br/>
          <input id=\"csv\" type=\"file\" name=\"file\" accept=\".csv\" required />
          <div class=\"row\"><button class=\"btn\" type=\"submit\">Upload File</button></div>
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

DASHBOARD_HTML = """
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Orchestra – Run Passes</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
      .panel { border:1px solid #eee; border-radius:12px; padding:16px; max-width:800px; }
      .row { display:grid; grid-template-columns: 180px 1fr 180px; gap:12px; align-items:center; padding:8px 0; border-bottom:1px solid #f2f2f2; }
      .row:last-child { border-bottom:none; }
      .btn { background:#fc5f36; color:#fff; border:none; padding:8px 12px; border-radius:8px; cursor:pointer; }
      .btn[disabled] { opacity:.5; cursor:not-allowed; }
      .status { color:#1c2d50; font-weight:600; }
      .note { color:#6b7280; margin-bottom:8px; }
      a.download { display:inline-block; background:#1c2d50; color:#fff; text-decoration:none; padding:8px 12px; border-radius:8px; text-align:center; }
    </style>
  </head>
  <body>
    <div class=\"panel\">
      <div class=\"note\">Upload ready. Run each pass independently. Your upload token: <code>{{ up_token }}</code></div>
      
      <!-- Column Mapping Preview -->
      <div style=\"margin-bottom: 16px; padding: 12px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #1c2d50;\">
        <h3 style=\"margin: 0 0 8px 0; font-size: 16px; color: #1c2d50;\">📋 Column Mapping Preview</h3>
        <div id=\"mapping_content\">{{ mapping_preview|safe }}</div>
      </div>
      <form method=\"post\" action=\"{{ url_for('run_pass1') }}\">
        <input type=\"hidden\" name=\"u\" value=\"{{ up_token }}\" />
        <div class=\"row\">
          <div><button class=\"btn\" type=\"submit\">Start Pass 1</button></div>
          <div class=\"status\" id=\"pass1_status\">{{ pass1_status }}</div>
          <div id=\"pass1_dl\">{% if pass1_dl_token %}<a class=\"download\" href=\"{{ url_for('download_token', token=pass1_dl_token) }}\">Download</a>{% else %}&nbsp;{% endif %}</div>
        </div>
      </form>
      <form method=\"post\" action=\"{{ url_for('run_pass2') }}\">
        <input type=\"hidden\" name=\"u\" value=\"{{ up_token }}\" />
        <div class=\"row\">
          <div><button class=\"btn\" type=\"submit\" {% if not pass1_complete %}disabled{% endif %}>Start Pass 2</button></div>
          <div class=\"status\" id=\"pass2_status\">{{ pass2_status }}</div>
          <div id=\"pass2_dl\">{% if pass2_dl_token %}<a class=\"download\" href=\"{{ url_for('download_token', token=pass2_dl_token) }}\">Download</a>{% else %}&nbsp;{% endif %}</div>
        </div>
      </form>
      
      <!-- Reset Button -->
      <div style=\"margin-top: 20px; padding-top: 16px; border-top: 1px solid #eee;\">
        <form method=\"post\" action=\"{{ url_for('reset') }}\" onsubmit=\"return confirm('This will clear all data and return to the upload page. Continue?')\">
          <input type=\"hidden\" name=\"u\" value=\"{{ up_token }}\" />
          <button class=\"btn\" type=\"submit\" style=\"background-color: #6b7280; font-size: 14px;\">🔄 Reset & Start Over</button>
        </form>
        <div style=\"color: #6b7280; font-size: 12px; margin-top: 4px;\">
          This will clear the uploaded file and all results, returning you to the upload page.
        </div>
      </div>
    </div>
    <script>
      (function(){
        const statusEl = document.getElementById('pass2_status');
        const dlEl = document.getElementById('pass2_dl');
        const upTokenEl = document.querySelector('input[name="u"]');
        if (!statusEl || !dlEl || !upTokenEl) return;
        const upToken = upTokenEl.value;
        function poll(){
          fetch('/status/pass2?u=' + encodeURIComponent(upToken))
            .then(function(r){ return r.ok ? r.json() : null; })
            .then(function(data){
              if (!data) return;
              if (data.status_text) statusEl.textContent = data.status_text;
              if (data.dl_token) {
                var href = '{{ url_for('download_token', token='__TOKEN__') }}'.replace('__TOKEN__', data.dl_token);
                dlEl.innerHTML = '<a class="download" href="' + href + '">Download</a>';
                return;
              }
              setTimeout(poll, 2000);
            })
            .catch(function(){ setTimeout(poll, 3000); });
        }
        var txt = (statusEl.textContent || '').toLowerCase();
        if (txt.indexOf('running') !== -1 || txt.indexOf('queued') !== -1) {
          poll();
        }
      })();
    </script>
  </body>
  </html>
"""


@app.get("/")
def index() -> Response:
    return render_template_string(INDEX_HTML)


@app.post("/upload")
def upload() -> Response:
    uploaded = request.files.get("file")
    if not uploaded or uploaded.filename == "":
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("index"))
    with tempfile.NamedTemporaryFile(delete=False, suffix="_input.csv") as tmp:
        uploaded.save(tmp.name)
        up_token = uuid4().hex
        UPLOADS[up_token] = tmp.name
        
        # Generate mapping preview immediately after upload
        mapping_preview = ""
        try:
            mapping_preview = vertical_analysis.initialize_mappings_from_csv(tmp.name)
        except Exception as e:
            print(f"Warning: Could not generate mapping preview: {e}")
            mapping_preview = f"<p style='color: #dc2626;'>⚠️ Could not analyze CSV structure: {e}</p>"
    
    return render_template_string(
        DASHBOARD_HTML,
        up_token=up_token,
        pass1_status="Ready",
        pass2_status="Waiting for Pass 1",
        pass1_complete=False,
        pass1_dl_token="",
        pass2_dl_token="",
        mapping_preview=mapping_preview,
    )


@app.post("/run/pass1")
def run_pass1() -> Response:
    up_token = request.form.get("u", "")
    tmp_path = UPLOADS.get(up_token)
    if not tmp_path:
        flash("Upload not found. Please upload your CSV again.", "error")
        return redirect(url_for("index"))

    # Pass 1 (vertical analysis)
    try:
        out_path1 = vertical_analysis.process(tmp_path)
    except Exception as e:
        flash(f"Processing failed (Pass 1): {e}", "error")
        return redirect(url_for("index"))

    if not out_path1 or not os.path.exists(out_path1):
        flash("No output produced.", "error")
        return redirect(url_for("index"))

    token1 = uuid4().hex
    DOWNLOADS[token1] = (out_path1, f"Pass1_{os.path.basename(out_path1)}")
    return render_template_string(
        DASHBOARD_HTML,
        up_token=up_token,
        pass1_status="Pass 1 Complete",
        pass2_status="Ready",
        pass1_complete=True,
        pass1_dl_token=token1,
        pass2_dl_token="",
        mapping_preview=vertical_analysis.get_last_mapping_preview(),
    )


@app.post("/run/pass2")
def run_pass2() -> Response:
    up_token = request.form.get("u", "")
    tmp_path = UPLOADS.get(up_token)
    if not tmp_path:
        flash("Upload not found. Please upload your CSV again.", "error")
        return redirect(url_for("index"))

    job = PASS2_JOBS.get(up_token)
    if not job or job.get("status") in {"error", "done"}:
        PASS2_JOBS[up_token] = {"status": "queued", "dl_token": None, "error": None}

        def _run():
            PASS2_JOBS[up_token]["status"] = "running"
            try:
                # Prefer Pass 1 output if exists (so signals build on states/modifiers)
                out_path1 = None
                for token, (path, name) in list(DOWNLOADS.items()):
                    if path.startswith(os.path.dirname(tmp_path)) and os.path.basename(path).startswith("Pass1_"):
                        out_path1 = path
                        break
                source_path = out_path1 if out_path1 and os.path.exists(out_path1) else tmp_path
                out_path2 = process_signals(source_path)
                if not out_path2 or not os.path.exists(out_path2):
                    raise RuntimeError("No output produced")
                token2 = uuid4().hex
                DOWNLOADS[token2] = (out_path2, f"Pass2_{os.path.basename(out_path2)}")
                PASS2_JOBS[up_token]["dl_token"] = token2
                PASS2_JOBS[up_token]["status"] = "done"
            except Exception as e:
                PASS2_JOBS[up_token]["status"] = "error"
                PASS2_JOBS[up_token]["error"] = str(e)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    return render_template_string(
        DASHBOARD_HTML,
        up_token=up_token,
        pass1_status="Pass 1 Complete",
        pass2_status="Pass 2 Running…",
        pass1_complete=True,
        pass1_dl_token="",
        pass2_dl_token="",
        mapping_preview=vertical_analysis.get_last_mapping_preview(),
    )


@app.get("/status/pass2")
def pass2_status() -> Response:
    up_token = request.args.get("u", "")
    job = PASS2_JOBS.get(up_token)
    if not job:
        return jsonify({"status": "idle", "status_text": "Ready"})
    status = job.get("status") or "idle"
    status_text = {
        "queued": "Pass 2 Queued",
        "running": "Pass 2 Running…",
        "done": "Pass 2 Complete",
        "error": f"Failed: {job.get('error','')}",
    }.get(status, "Ready")
    return jsonify({"status": status, "status_text": status_text, "dl_token": job.get("dl_token")})


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


@app.post("/reset")
def reset() -> Response:
    up_token = request.form.get("u", "")
    
    # Clean up uploaded file
    tmp_path = UPLOADS.pop(up_token, None)
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass  # Ignore cleanup errors
    
    # Clean up associated downloads
    to_remove = []
    for token, (path, name) in DOWNLOADS.items():
        if tmp_path and path.startswith(os.path.dirname(tmp_path)):
            to_remove.append(token)
            try:
                os.unlink(path)
            except OSError:
                pass  # Ignore cleanup errors
    
    for token in to_remove:
        DOWNLOADS.pop(token, None)
    
    # Clean up Pass 2 jobs
    PASS2_JOBS.pop(up_token, None)
    
    flash("Session reset. Please upload a new CSV file.", "success")
    return redirect(url_for("index"))


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


