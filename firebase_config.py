import firebase_admin
from firebase_admin import credentials, firestore, auth  # ← Add auth here

# Load your service account key
cred = credentials.Certificate("partymatch-key.json")

firebase_admin.initialize_app(cred)

# Get Firestore DB
db = firestore.client()
