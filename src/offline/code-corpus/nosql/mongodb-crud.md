---
language: python
tags: [mongodb, nosql, database, crud]
title: MongoDB CRUD with PyMongo
description: Connecting to MongoDB, inserting, finding, updating, deleting documents, query operators, and projections
source: pattern
---

```python
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from datetime import datetime, timedelta
import pprint

# ---------------------------------------------------------------------------
# Connect to MongoDB
# ---------------------------------------------------------------------------

# Default connection (local)
client = MongoClient("mongodb://localhost:27017/")

# With authentication
# client = MongoClient(
#     "mongodb://user:password@localhost:27017/admin?authSource=admin"
# )

# Connection string with options
# client = MongoClient(
#     "mongodb+srv://user:password@cluster.mongodb.net/"
#     "?retryWrites=true&w=majority"
# )

# Test the connection
try:
    client.admin.command("ping")
    print("Connected to MongoDB!")
except ConnectionFailure:
    print("Server not available")

# Database and collection references
db = client["shop"]                   # Database (created lazily)
users = db["users"]                   # Collection
orders = db["orders"]
products = db["products"]

# ---------------------------------------------------------------------------
# Create — insert_one / insert_many
# ---------------------------------------------------------------------------

# Insert a single document
user_doc = {
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "age": 30,
    "address": {
        "street": "123 Main St",
        "city": "NYC",
        "zip": "10001",
    },
    "interests": ["reading", "hiking"],
    "created_at": datetime.utcnow(),
}
result = users.insert_one(user_doc)
print(f"Inserted user with _id: {result.inserted_id}")

# Insert multiple documents
new_users = [
    {"name": "Bob Smith",    "email": "bob@example.com",   "age": 25, "city": "LA"},
    {"name": "Charlie Brown","email": "charlie@example.com","age": 35, "city": "Chicago"},
    {"name": "Diana Ross",   "email": "diana@example.com",  "age": 28, "city": "NYC"},
    {"name": "Eve Adams",    "email": "eve@example.com",    "age": 32, "city": "LA"},
]
result = users.insert_many(new_users)
print(f"Inserted {len(result.inserted_ids)} users")

# ---------------------------------------------------------------------------
# Read — find / find_one
# ---------------------------------------------------------------------------

# Find one document
alice = users.find_one({"name": "Alice Johnson"})
pprint.pprint(alice)

# Find all documents (returns a cursor)
for user in users.find():
    print(f"{user['name']} — {user.get('city', 'N/A')}")

# Find with query operators
# Age greater than 28
query = {"age": {"$gt": 28}}
for user in users.find(query):
    print(f"{user['name']} is {user['age']}")

# Age in a range
query = {"age": {"$gte": 25, "$lte": 35}}

# Using $in
query = {"city": {"$in": ["NYC", "LA"]}}

# Using $regex (case-insensitive)
query = {"name": {"$regex": "^[AE]", "$options": "i"}}

# Combining multiple conditions
query = {
    "age": {"$gte": 28},
    "city": {"$in": ["NYC", "Chicago"]},
}

# $exists — field exists
query = {"address": {"$exists": True}}

# ---------------------------------------------------------------------------
# Projections — controlling which fields are returned
# ---------------------------------------------------------------------------

# Include only name and email (exclude _id by default)
for user in users.find({}, {"_id": 0, "name": 1, "email": 1}):
    print(user)  # {"name": ..., "email": ...}

# Exclude specific fields
for user in users.find({}, {"interests": 0, "address": 0}):
    pass

# ---------------------------------------------------------------------------
# Update — update_one / update_many
# ---------------------------------------------------------------------------

# Update one document — set fields
result = users.update_one(
    {"name": "Alice Johnson"},
    {"$set": {"age": 31, "updated_at": datetime.utcnow()}},
)
print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")

# Increment a numeric field
result = users.update_one(
    {"name": "Bob Smith"},
    {"$inc": {"age": 1}},
)

# Add to an array ($push)
result = users.update_one(
    {"name": "Alice Johnson"},
    {"$push": {"interests": "photography"}},
)

# Add multiple elements to an array ($push with $each)
result = users.update_one(
    {"name": "Alice Johnson"},
    {"$push": {"interests": {"$each": ["cooking", "yoga"]}}},
)

# Remove from an array ($pull)
result = users.update_one(
    {"name": "Alice Johnson"},
    {"$pull": {"interests": "reading"}},
)

# Update many (all users in NYC get a tag)
result = users.update_many(
    {"city": "NYC"},
    {"$set": {"region": "East Coast"}},
)
print(f"Modified {result.modified_count} documents")

# Upsert — update or insert if not exists
result = users.update_one(
    {"email": "frank@example.com"},
    {"$set": {"name": "Frank", "age": 40}},
    upsert=True,
)
print(f"Upserted ID: {result.upserted_id}")

# ---------------------------------------------------------------------------
# Delete — delete_one / delete_many
# ---------------------------------------------------------------------------

# Delete one document
result = users.delete_one({"name": "Eve Adams"})
print(f"Deleted {result.deleted_count} document(s)")

# Delete many
result = users.delete_many({"age": {"$lt": 20}})
print(f"Deleted {result.deleted_count} document(s)")

# Delete all documents (but keep the collection)
# result = users.delete_many({})

# Drop the entire collection
# users.drop()

# ---------------------------------------------------------------------------
# Counting and sorting
# ---------------------------------------------------------------------------

total = users.count_documents({})
print(f"Total users: {total}")

nyc_count = users.count_documents({"city": "NYC"})

# Sort: 1 = ascending, -1 = descending
for user in users.find().sort("age", -1).limit(5):
    print(f"{user['name']}: {user['age']}")

# Compound sort
for user in users.find().sort([("city", 1), ("age", -1)]):
    print(f"{user['city']}: {user['name']} ({user['age']})")

# Limit and skip (pagination)
# page = users.find().sort("_id", 1).skip(20).limit(10)

# ---------------------------------------------------------------------------
# Clean up
# ---------------------------------------------------------------------------
# client.close()
```