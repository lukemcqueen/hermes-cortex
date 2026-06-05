---
language: docker
tags: [compose, multi-service, networks, volumes]
title: Docker Compose Multi-Service
description: depends_on, volumes, networks, env_file, healthcheck, restart policies.
source: pattern
---

```docker
services:
  api:
    build:
      context: ./api
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    env_file:
      - ./api/.env
    volumes:
      - api-data:/app/data
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - backend
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d
    networks:
      - backend
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d myapp"]
      interval: 10s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - backend
    restart: unless-stopped

volumes:
  api-data:
  pgdata:
  redis-data:

networks:
  backend:
    driver: bridge

```
