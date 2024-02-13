import os
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "")
print(MONGODB_URL)
client = MongoClient(MONGODB_URL)
db = client.entri_lunch_2023
users_collection = db.users
poll_collection = db.poll
