--- Full content (truncated) ---
---
name: fitness-nutrition
description: >
  Gym workout planner and nutrition tracker. Search 690+ exercises by muscle,
  equipment, or category via wger. Look up macros and calories for 380,000+
  foods via USDA FoodData Central. Compute BMI, TDEE, one-rep max, macro
  splits, and body fat — pure Python, no pip installs. Built for anyone
  chasing gains, cutting weight, or just trying to eat better.
platforms: [linux, macos, windows]
version: 1.0.0
authors:
  - haileymarshall
license: MIT
metadata:
  hermes:
    tags: [health, fitness, nutrition, gym, workout, diet, exercise]
    category: health
    prerequisites:
      commands: [curl, python3]
required_environment_variables:
  - name: USDA_API_KEY
    prompt: "USDA FoodData Central API key (free)"
    help: "Get one free at https://fdc.nal.usda.gov/api-key-signup/ — or skip to use DEMO_KEY with lower rate limits"
    required_for: "higher rate limits on food/nutrition lookups (DEMO_KEY works without signup)"
    optional: true
---
... [truncated]
--- End skill ---