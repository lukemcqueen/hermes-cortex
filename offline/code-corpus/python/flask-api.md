---
language: python
tags: [web, api]
title: Flask REST API
description: Minimal Flask REST API with JSON endpoints and error handling.
source: framework
---

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory store for demo
items = {}

@app.route('/api/items', methods=['GET'])
def list_items():
    return jsonify(list(items.values()))

@app.route('/api/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    item = items.get(item_id)
    if not item:
        return jsonify({'error': 'not found'}), 404
    return jsonify(item)

@app.route('/api/items', methods=['POST'])
def create_item():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'name required'}), 400
    item_id = max(items.keys(), default=0) + 1
    items[item_id] = {'id': item_id, 'name': data['name']}
    return jsonify(items[item_id]), 201

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    if item_id not in items:
        return jsonify({'error': 'not found'}), 404
    del items[item_id]
    return '', 204

if __name__ == '__main__':
    app.run(debug=True)

```
