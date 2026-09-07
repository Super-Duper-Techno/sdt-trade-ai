"""
SDT Trade AI — dashboard server.

Run with `python app.py` (or double-click run_windows.bat / run_mac.command /
run_linux.sh). Opens http://127.0.0.1:5000 in your browser automatically.
"""
import threading
import webbrowser

from flask import Flask, jsonify, request, render_template

from engine_runtime import runtime

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(runtime.snapshot())


@app.route("/api/login_url")
def api_login_url():
    try:
        return jsonify({"url": runtime.login_url()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/connect", methods=["POST"])
def api_connect():
    token = request.json.get("request_token", "").strip()
    try:
        runtime.connect(token)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/config", methods=["POST"])
def api_config():
    try:
        body = dict(request.json)
        if "tradingsymbols" in body and isinstance(body["tradingsymbols"], str):
            body["tradingsymbols"] = [s.strip().upper() for s in body["tradingsymbols"].split(",") if s.strip()]
        runtime.update_config(**body)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/paper_mode", methods=["POST"])
def api_paper_mode():
    try:
        runtime.set_paper_mode(bool(request.json.get("enabled", True)))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/start", methods=["POST"])
def api_start():
    try:
        runtime.start()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/stop", methods=["POST"])
def api_stop():
    runtime.stop()
    return jsonify({"ok": True})


@app.route("/api/kill", methods=["POST"])
def api_kill():
    runtime.manual_kill()
    return jsonify({"ok": True})


@app.route("/api/resume", methods=["POST"])
def api_resume():
    runtime.resume()
    return jsonify({"ok": True})


@app.route("/api/reset_day", methods=["POST"])
def api_reset_day():
    try:
        runtime.reset_day()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/report")
def api_report():
    return jsonify(runtime.report())


def _open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.2, _open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
