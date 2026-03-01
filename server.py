from flask import Flask, request, jsonify, send_from_directory
import os

app = Flask(__name__)
UPLOAD_FOLDER = "files"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Upload a file
@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    f = request.files["file"]
    rel_path = request.form.get("path", f.filename)
    save_path = os.path.join(UPLOAD_FOLDER, rel_path)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    f.save(save_path)
    print(f"[UPLOADED] {rel_path}")
    return jsonify({"success": True, "path": rel_path})

# List all files
@app.route("/files", methods=["GET"])
def list_files():
    file_list = []
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for fname in files:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, UPLOAD_FOLDER).replace("\\", "/")
            file_list.append(rel)
    return jsonify(file_list)

# Download a file
@app.route("/download/<path:filepath>", methods=["GET"])
def download(filepath):
    return send_from_directory(UPLOAD_FOLDER, filepath)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
