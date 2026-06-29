---
language: javascript
tags: [mongodb, indexes, performance, database]
title: MongoDB Indexing
description: Creating indexes, compound indexes, text indexes, TTL indexes, explain(), covered queries, and index strategies
source: pattern
---

```javascript
// MongoDB Indexing
// Run these in mongosh or any MongoDB driver

// ---------------------------------------------------------------------------
// Checking the current indexes on a collection
// ---------------------------------------------------------------------------

// List all indexes on the collection
db.users.getIndexes();
// Returns: [{ "v": 2, "key": { "_id": 1 }, "name": "_id_" }]
// _id is always indexed by default

// ---------------------------------------------------------------------------
// Creating a single-field index
// ---------------------------------------------------------------------------

// Ascending index on "email"
db.users.createIndex({ email: 1 });

// Descending index on "createdAt"
db.users.createIndex({ createdAt: -1 });

// The direction matters for sort order and compound indexes.
// For a single field, ascending vs descending makes no difference
// for equality queries — use 1 by convention.

// Named index (auto-named if omitted: "email_1")
db.users.createIndex({ email: 1 }, { name: "idx_email" });

// ---------------------------------------------------------------------------
// Compound indexes
// ---------------------------------------------------------------------------

// Index on (city, age) — supports queries on:
//   - city alone
//   - city AND age together
db.users.createIndex({ city: 1, age: -1 });

// Index on (status, createdAt) — good for queries like:
//   db.orders.find({ status: "pending" }).sort({ createdAt: -1 })
db.orders.createIndex({ status: 1, createdAt: -1 });

// Compound index with uniqueness across the combination
db.users.createIndex(
  { firstName: 1, lastName: 1 },
  { unique: true }
);

// ---------------------------------------------------------------------------
// Unique indexes
// ---------------------------------------------------------------------------

// Ensure email uniqueness
db.users.createIndex({ email: 1 }, { unique: true });

// With partial filter — only enforce uniqueness for active users
db.users.createIndex(
  { email: 1 },
  { unique: true, partialFilterExpression: { status: "active" } }
);

// ---------------------------------------------------------------------------
// Text indexes — full-text search on string fields
// ---------------------------------------------------------------------------

// Single field text index
db.articles.createIndex({ title: "text" });

// Compound text index on multiple fields (weights control relevance)
db.articles.createIndex(
  { title: "text", body: "text", tags: "text" },
  {
    weights: { title: 10, tags: 5, body: 1 },
    name: "search_index",
  }
);

// Search using the text index
db.articles.find(
  { $text: { $search: "mongodb indexing performance" } },
  { score: { $meta: "textScore" } }
).sort({ score: { $meta: "textScore" } });

// Exact phrase search (wrap in quotes)
db.articles.find({ $text: { $search: "\"compound index\"" } });

// Exclude a term (prepend with -)
db.articles.find({ $text: { $search: "mongodb -mysql" } });

// ---------------------------------------------------------------------------
// TTL indexes — auto-expire documents
// ---------------------------------------------------------------------------

// Delete documents 24 hours after `createdAt` timestamp
db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 }    // 24 hours
);

// Delete documents at a specific future date
// (use a field with a future Date value instead)
db.offers.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }        // Delete when expiresAt is reached
);

// ---------------------------------------------------------------------------
// Sparse indexes — only index documents with the field
// ---------------------------------------------------------------------------

db.users.createIndex(
  { phone: 1 },
  { sparse: true }    // Skip documents that don't have "phone"
);

// ---------------------------------------------------------------------------
// Partial indexes — index only matching documents
// ---------------------------------------------------------------------------

// Index only orders with status "pending"
db.orders.createIndex(
  { createdAt: 1 },
  { partialFilterExpression: { status: "pending" } }
);

// Compare: partial index is more flexible than sparse

// ---------------------------------------------------------------------------
// explain() — understanding query execution
// ---------------------------------------------------------------------------

// Explain a query
db.users.find({ email: "alice@example.com" }).explain("executionStats");
// Key fields to read:
//   - winningPlan: which index was used (or COLLSCAN)
//   - executionStats.totalDocsExamined
//   - executionStats.totalKeysExamined
//   - executionStats.executionTimeMillis
//   - executionStats.nReturned

// Goal: totalDocsExamined ≈ nReturned (no fetch steps)
//       totalKeysExamined ≈ nReturned (selective index)

// Explain an aggregation
db.users.aggregate([
  { $match: { email: "alice@example.com" } }
]).explain("executionStats");

// ---------------------------------------------------------------------------
// Covered queries — index contains all required data
// ---------------------------------------------------------------------------

// If you query only indexed fields, MongoDB doesn't need to fetch documents.
// Covered query example:
db.users.createIndex({ email: 1, name: 1, age: 1 });

// This query is covered: all returned fields (email, name, age) are in the index,
// and _id is excluded:
db.users.find(
  { email: "alice@example.com" },
  { _id: 0, email: 1, name: 1, age: 1 }
);

// Check with explain(): IXSCAN only, no FETCH stage

// ---------------------------------------------------------------------------
// Index usage tips and strategies
// ---------------------------------------------------------------------------

// 1. Equality first, then sort, then range (ESR rule)
// For db.orders.find({ status: "active" }).sort({ createdAt: -1 })
//   .find({ createdAt: { $gt: ISODate("2025-01-01") } })
// Best index: { status: 1, createdAt: -1 }
//    (equality → sort → range)

// 2. Cardinality — index high-selectivity fields first
//    "email" is high cardinality (many unique values)
//    "status" is low cardinality (few unique values)
//    Put high-cardinality fields first in the compound index

// 3. Avoid over-indexing — each index costs:
//    - Disk space
//    - Write performance (every insert/update must update every index)
//    - RAM (indexes in working set)

// 4. Drop unused indexes
db.users.dropIndex("idx_email");  // By name
db.users.dropIndex({ email: 1 }); // By key spec

// 5. Drop multiple at once
db.users.dropIndexes(["idx_old_1", "idx_old_2"]);

// 6. Background index building (older MongoDB versions)
// db.users.createIndex({ email: 1 }, { background: true });

// In MongoDB 4.2+, all index builds are background by default

// 7. Use .hint() to force a specific index
db.users.find({ email: "alice@example.com" }).hint({ email: 1 });

// 8. Hidden index (MongoDB 4.4+) — test dropping without actually dropping
db.users.createIndex({ email: 1 }, { hidden: true });
// db.users.unhideIndex({ email: 1 });

// ---------------------------------------------------------------------------
// Checking index usage
// ---------------------------------------------------------------------------

// Get index usage statistics
db.users.aggregate([
  { $indexStats: {} }
]);
// Shows: name, accesses.ops (number of operations), since (timestamp)

// ---------------------------------------------------------------------------
// Geospatial indexes
// ---------------------------------------------------------------------------

// 2dsphere index for GeoJSON data
db.places.createIndex({ location: "2dsphere" });

// Query: nearby locations
db.places.find({
  location: {
    $near: {
      $geometry: { type: "Point", coordinates: [-73.97, 40.77] },
      $maxDistance: 1000,  // meters
      $minDistance: 10,
    }
  }
});

// ---------------------------------------------------------------------------
// Wildcard indexes — index unknown/arbitrary fields
// ---------------------------------------------------------------------------

// Index all fields in a document
db.products.createIndex({ "$**": "text" });

// Index all sub-fields of "attributes"
db.products.createIndex({ "attributes.$**": 1 });
```