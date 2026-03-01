from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image
import os
import struct
import io
import base64
import json

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "files"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Mesh Parser ──────────────────────────────────────

def parse_mesh_v1(data):
    lines = data.decode("utf-8").splitlines()
    vertices = []
    faces = []
    if len(lines) < 3:
        return None, None
    num_faces = int(lines[1].strip())
    raw = lines[2].strip()
    nums = []
    for val in raw.replace("[", "").replace("]", " ").split():
        try:
            nums.append(float(val))
        except:
            pass
    stride = 9
    verts_per_face = 3
    total_per_face = stride * verts_per_face
    for f in range(num_faces):
        base = f * total_per_face
        face_verts = []
        for v in range(verts_per_face):
            vbase = base + v * stride
            if vbase + 2 < len(nums):
                x = nums[vbase]
                y = nums[vbase + 1]
                z = nums[vbase + 2]
                vertices.append((x, y, z))
                face_verts.append(len(vertices))
        if len(face_verts) == 3:
            faces.append(face_verts)
    return vertices, faces


def parse_mesh_v2(data):
    try:
        header_end = data.index(b"\n") + 1
        offset = header_end
        sizeof_mesh_header = struct.unpack_from("<H", data, offset)[0]; offset += 2
        num_lods           = struct.unpack_from("<H", data, offset)[0]; offset += 2
        num_verts          = struct.unpack_from("<I", data, offset)[0]; offset += 4
        num_faces          = struct.unpack_from("<I", data, offset)[0]; offset += 4
        offset = header_end + sizeof_mesh_header
        vertices = []
        uvs = []
        normals = []
        for i in range(num_verts):
            x, y, z = struct.unpack_from("<fff", data, offset); offset += 12
            nx, ny, nz = struct.unpack_from("<fff", data, offset); offset += 12
            u, v = struct.unpack_from("<ff", data, offset); offset += 8
            vertices.append((x, y, z))
            normals.append((nx, ny, nz))
            uvs.append((u, v))
        faces = []
        for i in range(num_faces):
            v1, v2, v3 = struct.unpack_from("<III", data, offset); offset += 12
            faces.append((v1 + 1, v2 + 1, v3 + 1))
        return vertices, faces, normals, uvs
    except Exception as e:
        print(f"[MESH v2 ERROR] {e}")
        return None, None, None, None


def mesh_to_obj(data):
    try:
        header = data[:12].decode("utf-8", errors="ignore")
    except:
        header = ""
    obj_lines = ["# Converted from Roblox .mesh"]
    if "version 1" in header:
        vertices, faces = parse_mesh_v1(data)
        normals, uvs = None, None
    else:
        vertices, faces, normals, uvs = parse_mesh_v2(data)
    if not vertices or not faces:
        return None
    for v in vertices:
        obj_lines.append(f"v {v[0]} {v[1]} {v[2]}")
    if normals:
        for n in normals:
            obj_lines.append(f"vn {n[0]} {n[1]} {n[2]}")
    if uvs:
        for uv in uvs:
            obj_lines.append(f"vt {uv[0]} {uv[1]}")
    for f in faces:
        if normals and uvs:
            obj_lines.append(f"f {f[0]}/{f[0]}/{f[0]} {f[1]}/{f[1]}/{f[1]} {f[2]}/{f[2]}/{f[2]}")
        else:
            obj_lines.append(f"f {f[0]} {f[1]} {f[2]}")
    return "\n".join(obj_lines)


def png_to_rgba(data):
    try:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        width, height = img.size
        flat = []
        for r, g, b, a in img.getdata():
            flat.extend([r, g, b, a])
        b64 = base64.b64encode(bytes(flat)).decode("utf-8")
        return {"width": width, "height": height, "data": b64}
    except Exception as e:
        print(f"[PNG ERROR] {e}")
        return None

# ── Routes ───────────────────────────────────────────

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    rel_path = request.form.get("path", f.filename)
    data = f.read()
    rel_path, data = process_file(rel_path, data)
    if rel_path is None:
        return jsonify({"error": "Unsupported file type"}), 400
    save(rel_path, data)
    return jsonify({"success": True, "path": rel_path})


@app.route("/upload-raw", methods=["POST"])
def upload_raw():
    body = request.get_json()
    if not body or "name" not in body or "data" not in body:
        return jsonify({"error": "Missing name or data"}), 400
    name = body["name"]
    # Decode from latin-1 safe encoding
    try:
        data = body["data"].encode("latin-1")
    except:
        data = body["data"].encode("utf-8")
    name, data = process_file(name, data)
    if name is None:
        return jsonify({"error": "Unsupported"}), 400
    save(name, data)
    return jsonify({"success": True, "path": name})


@app.route("/files", methods=["GET"])
def list_files():
    file_list = []
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for fname in files:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, UPLOAD_FOLDER).replace("\\", "/")
            file_list.append(rel)
    return jsonify(file_list)


@app.route("/download/<path:filepath>", methods=["GET"])
def download(filepath):
    return send_from_directory(UPLOAD_FOLDER, filepath)


@app.route("/delete/<path:filepath>", methods=["DELETE"])
def delete(filepath):
    full = os.path.join(UPLOAD_FOLDER, filepath)
    if os.path.exists(full):
        os.remove(full)
        return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404


@app.route("/clear", methods=["POST"])
def clear():
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for fname in files:
            os.remove(os.path.join(root, fname))
    return jsonify({"success": True})

# ── Helpers ───────────────────────────────────────────

def process_file(rel_path, data):
    if rel_path.endswith(".mesh"):
        obj_data = mesh_to_obj(data)
        if obj_data:
            rel_path = rel_path.replace(".mesh", ".obj")
            data = obj_data.encode("utf-8")
            print(f"[CONVERTED] .mesh → {rel_path}")
    elif rel_path.endswith((".png", ".jpg", ".jpeg")):
        rgba = png_to_rgba(data)
        if rgba:
            rel_path = rel_path.rsplit(".", 1)[0] + ".rgba.json"
            data = json.dumps(rgba).encode("utf-8")
            print(f"[CONVERTED] image → {rel_path}")
    elif rel_path.endswith((".mp3", ".ogg", ".wav")):
        print(f"[SKIPPED] audio: {rel_path}")
        return None, None
    return rel_path, data


def save(rel_path, data):
    save_path = os.path.join(UPLOAD_FOLDER, rel_path)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(data)
    print(f"[SAVED] {rel_path}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
