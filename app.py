from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
from firebase_config import db
from firebase_admin import auth
from functools import wraps
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# ---------- AUTH DECORATOR FOR FLUTTERFLOW ----------
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        id_token = None

        if auth_header.startswith('Bearer '):
            id_token = auth_header.split('Bearer ')[1]

        if not id_token:
            return jsonify({'error': 'Missing ID token'}), 401

        try:
            decoded_token = auth.verify_id_token(id_token)
            request.user_id = decoded_token['uid']
        except Exception as e:
            return jsonify({'error': f'Invalid token: {str(e)}'}), 403

        return f(*args, **kwargs)
    return decorated

# ---------- WEB ROUTES ----------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    name = request.form.get('name')
    age = request.form.get('age')
    bio = request.form.get('bio')
    files = request.files.getlist('photos')

    photo_urls = []
    for f in files[:3]:
        if f.filename:
            filename = secure_filename(f.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            f.save(filepath)
            photo_urls.append(os.path.join("uploads", filename))

    user_data = {
        "name": name,
        "age": int(age),
        "bio": bio,
        "photos": photo_urls,
        "tags": [],
    }

    user_ref = db.collection("users").add(user_data)
    session['current_user_id'] = user_ref[1].id
    return redirect(url_for('profile'))

@app.route('/profile')
def profile():
    current_id = session.get('current_user_id')
    if not current_id:
        return redirect(url_for('index'))

    current_user_doc = db.collection("users").document(current_id).get()
    if not current_user_doc.exists:
        return "User not found", 404

    visible_users = [
        {**doc.to_dict(), "id": doc.id}
        for doc in db.collection("users").stream()
        if doc.id != current_id
    ]

    return render_template("profile.html", users=visible_users, current_user=current_id)

@app.route('/like')
def like():
    from_id = session.get("current_user_id")
    to_user_id = request.args.get("to_id")

    db.collection("likes").add({"from": from_id, "to": to_user_id})

    reverse_like = db.collection("likes")\
        .where("from", "==", to_user_id)\
        .where("to", "==", from_id).limit(1).stream()

    is_match = any(True for _ in reverse_like)

    if is_match:
        db.collection("matches").add({
            "users": sorted([from_id, to_user_id]),
            "timestamp": datetime.utcnow()
        })

    return {"match": is_match}

# ---------- CHAT BACKEND ----------

def get_or_create_chat(user1_id, user2_id):
    users_sorted = sorted([user1_id, user2_id])
    chat_query = db.collection("chats")\
        .where("users", "==", users_sorted).limit(1).stream()

    for chat in chat_query:
        return chat.id

    new_chat = db.collection("chats").add({
        "users": users_sorted,
        "created_at": datetime.utcnow()
    })
    return new_chat[1].id

@app.route('/chat/<other_id>')
def open_chat(other_id):
    current_id = session.get('current_user_id')
    if not current_id:
        return redirect(url_for('index'))

    chat_id = get_or_create_chat(current_id, other_id)
    return render_template("chat.html", chat_id=chat_id, to_id=other_id)

@app.route('/send_message', methods=['POST'])
def send_message():
    from_id = session.get("current_user_id")
    to_id = request.form.get("to_id")
    text = request.form.get("text")

    if not (from_id and to_id and text):
        return {"error": "Missing data"}, 400

    chat_id = get_or_create_chat(from_id, to_id)

    db.collection("chats").document(chat_id).collection("messages").add({
        "sender": from_id,
        "text": text,
        "timestamp": datetime.utcnow()
    })

    return {"success": True, "chat_id": chat_id}

@app.route('/messages/<chat_id>')
def get_messages(chat_id):
    messages_ref = db.collection("chats").document(chat_id).collection("messages")\
        .order_by("timestamp").stream()

    messages = [{
        "sender": m.to_dict()["sender"],
        "text": m.to_dict()["text"],
        "timestamp": m.to_dict()["timestamp"].isoformat()
    } for m in messages_ref]

    return {"messages": messages}

@app.route('/matches')
def matches():
    current_id = session.get("current_user_id")
    if not current_id:
        return redirect(url_for('index'))

    matched_users = []
    match_docs = db.collection("matches")\
        .where("users", "array_contains", current_id).stream()

    for doc in match_docs:
        match = doc.to_dict()
        others = [uid for uid in match["users"] if uid != current_id]
        if not others:
            continue
        other_id = others[0]
        user_doc = db.collection("users").document(other_id).get()
        if user_doc.exists:
            data = user_doc.to_dict()
            data["id"] = user_doc.id
            matched_users.append(data)

    return render_template("matches.html", matches=matched_users)

# ---------- FLUTTERFLOW API (WITH FIREBASE AUTH) ----------

@app.route('/api/users')
@require_auth
def api_users():
    user_id = request.user_id
    users = [
        {**doc.to_dict(), "id": doc.id}
        for doc in db.collection("users").stream()
        if doc.id != user_id
    ]
    return jsonify({"users": users})

@app.route('/api/matches')
@require_auth
def api_matches():
    user_id = request.user_id
    match_docs = db.collection("matches").where("users", "array_contains", user_id).stream()

    matches = []
    for doc in match_docs:
        match = doc.to_dict()
        others = [uid for uid in match["users"] if uid != user_id]
        if not others:
            continue
        other_id = others[0]
        user_doc = db.collection("users").document(other_id).get()
        if user_doc.exists:
            data = user_doc.to_dict()
            data["id"] = user_doc.id
            matches.append(data)

    return jsonify({"matches": matches})

@app.route('/api/like', methods=['POST'])
@require_auth
def api_like():
    from_id = request.user_id
    to_user_id = request.json.get("to_id")

    if not to_user_id:
        return {"error": "Missing to_id"}, 400

    db.collection("likes").add({
        "from": from_id,
        "to": to_user_id
    })

    reverse_like = db.collection("likes")\
        .where("from", "==", to_user_id)\
        .where("to", "==", from_id).limit(1).stream()

    is_match = any(True for _ in reverse_like)

    if is_match:
        db.collection("matches").add({
            "users": sorted([from_id, to_user_id]),
            "timestamp": datetime.utcnow()
        })

    return jsonify({"match": is_match})

# ---------- DEPLOY ----------
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, host='0.0.0.0', port=10000)
