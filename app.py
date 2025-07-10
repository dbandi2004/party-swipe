from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
import os
import uuid
from firebase_config import db

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

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
        if f.filename != '':
            filename = secure_filename(f.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            f.save(filepath)
            photo_urls.append(filepath)

    user_data = {
        "name": name,
        "age": int(age),
        "bio": bio,
        "photos": photo_urls,
        "tags": [],
    }

    user_ref = db.collection("users").add(user_data)
    session['current_user_id'] = user_ref[1].id  # document ID
    return redirect(url_for('profile'))

@app.route('/profile')
def profile():
    current_id = session.get('current_user_id')
    if not current_id:
        return redirect(url_for('index'))

    current_user_doc = db.collection("users").document(current_id).get()
    if not current_user_doc.exists:
        return "User not found", 404

    all_users = db.collection("users").stream()
    visible_users = []

    for doc in all_users:
        if doc.id != current_id:
            user = doc.to_dict()
            user["id"] = doc.id
            visible_users.append(user)

    return render_template("profile.html", users=visible_users, current_user=current_id)

@app.route('/like')
def like():
    from_id = session.get("current_user_id")
    to_index = int(request.args.get("to"))

    # Get all users (same as profile order)
    all_users = list(db.collection("users").stream())
    to_user_doc = all_users[to_index]
    to_user_id = to_user_doc.id

    # Add the like to Firestore
    db.collection("likes").add({
        "from": from_id,
        "to": to_user_id
    })

    # Check if to_user has already liked from_user
    existing = db.collection("likes")\
        .where("from", "==", to_user_id)\
        .where("to", "==", from_id)\
        .stream()

    match = any(True for _ in existing)

    return {"match": match}

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
