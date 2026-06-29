---
language: javascript
tags: [mongodb, aggregation, pipeline, database]
title: MongoDB Aggregation Pipeline
description: Aggregation pipeline stages — $match, $group, $sort, $project, $unwind, $lookup (JOIN), $bucket, and practical examples
source: pattern
---

```javascript
// MongoDB Aggregation Pipeline
// Run these in mongosh, Compass, or any MongoDB driver
// Collection: orders

// ---------------------------------------------------------------------------
// Sample documents for context
// ---------------------------------------------------------------------------
// db.orders.insertMany([
//   { _id: 1, customer: "Alice",  product: "Widget",   qty: 2,  price: 9.99,  date: ISODate("2025-01-15") },
//   { _id: 2, customer: "Bob",    product: "Gadget",   qty: 1,  price: 24.99, date: ISODate("2025-01-16") },
//   { _id: 3, customer: "Alice",  product: "Widget",   qty: 3,  price: 9.99,  date: ISODate("2025-02-10") },
//   { _id: 4, customer: "Charlie",product: "Gadget",   qty: 5,  price: 24.99, date: ISODate("2025-02-12") },
//   { _id: 5, customer: "Bob",    product: "Doohickey",qty: 2,  price: 14.99, date: ISODate("2025-03-05") },
//   { _id: 6, customer: "Alice",  product: "Gadget",   qty: 1,  price: 24.99, date: ISODate("2025-03-20") },
// ]);

// db.customers.insertMany([
//   { _id: 1, name: "Alice",  city: "NYC",     tier: "Gold"   },
//   { _id: 2, name: "Bob",    city: "LA",      tier: "Silver" },
//   { _id: 3, name: "Charlie",city: "Chicago",  tier: "Gold"   },
// ]);

// ---------------------------------------------------------------------------
// Stage 1: $match — filter documents (like WHERE)
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $match: { customer: "Alice" } }
]);

// With multiple conditions
db.orders.aggregate([
  { $match: {
      date: { $gte: ISODate("2025-02-01") },
      qty:  { $gte: 2 }
  }}
]);

// ---------------------------------------------------------------------------
// Stage 2: $group — aggregate/group documents (like GROUP BY)
// ---------------------------------------------------------------------------

// Total quantity per customer
db.orders.aggregate([
  { $group: {
      _id: "$customer",
      totalQty: { $sum: "$qty" },
      totalAmount: { $sum: { $multiply: ["$qty", "$price"] } },
  }}
]);

// Available accumulators: $sum, $avg, $min, $max, $first, $last, $push, $addToSet

// Average price per product
db.orders.aggregate([
  { $group: {
      _id: "$product",
      avgPrice: { $avg: "$price" },
      count: { $sum: 1 },
  }}
]);

// Collect all customers per product
db.orders.aggregate([
  { $group: {
      _id: "$product",
      customers: { $addToSet: "$customer" },
  }}
]);

// ---------------------------------------------------------------------------
// Stage 3: $sort — order results
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $group: {
      _id: "$customer",
      total: { $sum: { $multiply: ["$qty", "$price"] } },
  }},
  { $sort: { total: -1 } },     // Highest spender first
]);

// ---------------------------------------------------------------------------
// Stage 4: $project — reshape documents (like SELECT with transformations)
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $project: {
      _id: 0,                             // Hide _id
      customer: 1,                        // Include
      product: 1,
      total: { $multiply: ["$qty", "$price"] },  // Computed field
      year: { $year: "$date" },           // Extract year from date
      month: { $month: "$date" },
  }}
]);

// ---------------------------------------------------------------------------
// Stage 5: $unwind — deconstruct arrays
// ---------------------------------------------------------------------------

// Sample: db.inventory.insertOne({
//   item: "ABC", sizes: ["S", "M", "L"]
// })

db.inventory.aggregate([
  { $unwind: "$sizes" }
]);
// Result:
// { item: "ABC", sizes: "S" }
// { item: "ABC", sizes: "M" }
// { item: "ABC", sizes: "L" }

// Preserve empty arrays with preserveNullAndEmptyArrays
db.inventory.aggregate([
  { $unwind: { path: "$sizes", preserveNullAndEmptyArrays: true } }
]);

// ---------------------------------------------------------------------------
// Stage 6: $lookup — perform a LEFT JOIN with another collection
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $lookup: {
      from: "customers",
      localField: "customer",
      foreignField: "name",
      as: "customer_info",
  }},
  { $unwind: "$customer_info" },          // Flatten the joined array
  { $project: {
      product: 1,
      qty: 1,
      price: 1,
      customer: 1,
      city: "$customer_info.city",
      tier: "$customer_info.tier",
  }}
]);

// ---------------------------------------------------------------------------
// Full pipeline: match → group → sort → project
// ---------------------------------------------------------------------------

// Monthly revenue by product
db.orders.aggregate([
  { $match: { date: { $gte: ISODate("2025-01-01") } }},
  { $group: {
      _id: {
          year: { $year: "$date" },
          month: { $month: "$date" },
          product: "$product",
      },
      revenue: { $sum: { $multiply: ["$qty", "$price"] } },
      orders: { $sum: 1 },
  }},
  { $sort: { "_id.year": 1, "_id.month": 1, revenue: -1 }},
  { $project: {
      _id: 0,
      year: "$_id.year",
      month: "$_id.month",
      product: "$_id.product",
      revenue: { $round: ["$revenue", 2] },
      orders: 1,
  }}
]);

// ---------------------------------------------------------------------------
// $bucket — histogram / Categorize values into buckets
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $bucket: {
      groupBy: "$qty",
      boundaries: [0, 2, 5, 10, 100],
      default: "Other",
      output: {
          count: { $sum: 1 },
          products: { $push: "$product" },
      },
  }}
]);
// Result:
// { _id: 0, count: 1, products: ["Widget"] }      // qty in [0,2)
// { _id: 2, count: 3, products: ["Widget","Doohickey","Gadget"] } // qty in [2,5)
// { _id: 5, count: 1, products: ["Gadget"] }       // qty in [5,10)
// ...

// ---------------------------------------------------------------------------
// $facet — multiple pipelines in one pass
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $facet: {
      "byCustomer": [
          { $group: { _id: "$customer", total: { $sum: { $multiply: ["$qty", "$price"] } } }},
          { $sort: { total: -1 }},
      ],
      "byProduct": [
          { $group: { _id: "$product", count: { $sum: 1 }}},
          { $sort: { count: -1 }},
      ],
      "stats": [
          { $group: {
              _id: null,
              avgOrderValue: { $avg: { $multiply: ["$qty", "$price"] } },
              totalOrders: { $sum: 1 },
          }},
      ],
  }}
]);

// ---------------------------------------------------------------------------
// $addFields and $set — add/overwrite fields
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $addFields: {
      total: { $multiply: ["$qty", "$price"] },
      discount: { $cond: [
          { $gte: ["$qty", 3] },
          0.1,    // 10% discount for bulk
          0,      // no discount
      ]},
  }},
  { $addFields: {
      finalTotal: { $subtract: [
          "$total",
          { $multiply: ["$total", "$discount"] },
      ]},
  }},
]);

// ---------------------------------------------------------------------------
// $out — write pipeline results to a new collection
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $group: {
      _id: "$customer",
      total: { $sum: { $multiply: ["$qty", "$price"] } },
  }},
  { $out: "customer_summary" }
]);

// ---------------------------------------------------------------------------
// Practical: Running total with $setWindowFields (MongoDB 5.0+)
// ---------------------------------------------------------------------------

db.orders.aggregate([
  { $sort: { date: 1 }},
  { $setWindowFields: {
      sortBy: { date: 1 },
      output: {
          runningTotal: {
              $sum: { $multiply: ["$qty", "$price"] },
              window: { documents: ["unbounded", "current"] },
          },
      },
  }},
]);
```