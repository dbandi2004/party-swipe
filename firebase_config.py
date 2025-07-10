import firebase_admin
from firebase_admin import credentials, firestore

# Load your service account key
cred = credentials.Certificate("partymatch-3504a-firebase-adminsdk-fbsvc-8329e80f14.json")
firebase_admin.initialize_app(cred)

# Get Firestore DB
db = firestore.client()
