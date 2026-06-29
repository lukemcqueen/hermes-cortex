---
language: yaml
tags: [github-actions, docker, container, ci]
title: GitHub Actions for Docker
description: Complete GitHub Actions CI/CD pipelines for Docker including build and push to registries, multi-platform builds, docker-compose integration tests, and containerized services
source: pattern
---

# GitHub Actions for Docker

## Basic Docker Build and Push

```yaml
name: Docker Build and Push

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  REGISTRY: docker.io
  IMAGE_NAME: ${{ github.repository_owner }}/my-app

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}
      
      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: |
            ${{ env.IMAGE_NAME }}
            ghcr.io/${{ github.repository }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,format=short
            type=ref,event=pr
          flavor: |
            latest=auto
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## Multi-Platform Builds

```yaml
name: Multi-Platform Docker Build

on:
  push:
    branches: [main]
    tags: ['v*']

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64,amd64
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
      
      - name: Build and push multi-platform
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64,linux/arm/v7
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: |
            type=gha,scope=${{ github.ref_name }}
            type=gha,scope=main
          cache-to: type=gha,mode=max,scope=${{ github.ref_name }}
          provenance: true
          sbom: true
```

## Docker Compose for Integration Tests

```yaml
name: Docker Compose Integration Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  integration:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Build services
        run: docker compose build
      
      - name: Start services
        run: |
          docker compose up -d
          # Wait for services to be healthy
          docker compose ps
      
      - name: Wait for service readiness
        run: |
          # Poll until the API service responds
          for i in $(seq 1 30); do
            if curl -s http://localhost:8080/health > /dev/null 2>&1; then
              echo "Service is ready!"
              break
            fi
            echo "Waiting for service... ($i/30)"
            sleep 2
          done
      
      - name: Run integration tests
        run: |
          docker compose exec -T app npm run test:integration
        env:
          CI: true
      
      - name: Collect logs on failure
        if: failure()
        run: |
          docker compose logs
      
      - name: Stop services
        if: always()
        run: docker compose down -v

  # Alternative: Run tests alongside the app service
  test-with-dependency-services:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping | grep PONG"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      minio:
        image: minio/minio:latest
        env:
          MINIO_ROOT_USER: testuser
          MINIO_ROOT_PASSWORD: testpassword
        ports:
          - 9000:9000
          - 9001:9001
        options: >-
          --health-cmd "curl -s http://localhost:9000/minio/health/live"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run tests
        run: |
          docker compose -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from test
```

## Containerized Services in CI Matrix

```yaml
name: Docker Service Matrix

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        postgres-version: ['15', '16', '17']
        node-version: ['18', '20']
    
    services:
      postgres:
        image: postgres:${{ matrix.postgres-version }}
        env:
          POSTGRES_DB: test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
      
      - run: npm ci
      
      - run: npm test
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test
          PG_VERSION: ${{ matrix.postgres-version }}
```

## Full Build, Test, and Deploy with Docker

```yaml
name: Docker Full CI/CD

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Build Docker images for testing
        run: |
          docker compose -f docker-compose.test.yml build
      
      - name: Run tests in Docker
        run: |
          docker compose -f docker-compose.test.yml run --rm test
        env:
          CI: true
      
      - name: Build application image
        run: |
          docker build -t app:test .
      
      - name: Run container smoke test
        run: |
          docker run -d --name app-test -p 8080:3000 app:test
          sleep 3
          curl -f http://localhost:8080/health || exit 1
          docker stop app-test
          docker rm app-test
  
  lint-dockerfile:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Lint Dockerfile with hadolint
        uses: hadolint/hadolint-action@v3.1.0
        with:
          dockerfile: Dockerfile
          failure-threshold: warning
      
      - name: Check Dockerfile best practices
        run: |
          docker run --rm -v $PWD:/workspace hadolint/hadolint:latest \
            /workspace/Dockerfile
  
  build-and-push:
    needs: [test, lint-dockerfile]
    if: github.event_name != 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,format=short
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: true
  
  deploy:
    needs: build-and-push
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment: production
    
    steps:
      - name: Deploy to Kubernetes
        run: |
          echo "Deploying ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.ref_name }}"
          # kubectl set image deployment/my-app my-app=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.ref_name }}
      
      - name: Deploy to Docker Swarm
        if: false  # Example
        run: |
          docker stack deploy -c docker-compose.prod.yml my-app --with-registry-auth
```

## Scan Images for Vulnerabilities

```yaml
name: Docker Security Scan

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'  # Every Monday at 6 AM

jobs:
  scan:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Build image
        run: docker build -t app:scan .
      
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: 'app:scan'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'
          exit-code: '1'
      
      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
      
      - name: Run Docker Scout
        uses: docker/scout-action@v1
        with:
          command: quickview
          image: app:scan
          only-severities: critical,high
```

## Reusable Docker Workflow

```yaml
# .github/workflows/docker-build-reusable.yml
name: Docker Build Reusable

on:
  workflow_call:
    inputs:
      image-name:
        required: true
        type: string
      context:
        required: false
        type: string
        default: '.'
      dockerfile:
        required: false
        type: string
        default: 'Dockerfile'
      platforms:
        required: false
        type: string
        default: 'linux/amd64'
      push:
        required: false
        type: boolean
        default: true
      tags:
        required: false
        type: string
        default: 'type=raw,value=latest'
    secrets:
      REGISTRY_USERNAME:
        required: false
      REGISTRY_PASSWORD:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to Docker Hub
        if: secrets.REGISTRY_USERNAME
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Generate tags
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ inputs.image-name }}
          tags: ${{ inputs.tags }}
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ${{ inputs.context }}
          file: ${{ inputs.dockerfile }}
          platforms: ${{ inputs.platforms }}
          push: ${{ inputs.push }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max


# Usage in a project:
# .github/workflows/my-app.yml
# name: My App CI
#
# on:
#   push:
#     branches: [main]
#
# jobs:
#   docker:
#     uses: ./.github/workflows/docker-build-reusable.yml
#     with:
#       image-name: ghcr.io/my-org/my-app
#       platforms: linux/amd64,linux/arm64
#       tags: |
#         type=raw,value=latest
#         type=sha,format=short
#     secrets:
#       REGISTRY_USERNAME: ${{ secrets.DOCKER_USERNAME }}
#       REGISTRY_PASSWORD: ${{ secrets.DOCKER_PASSWORD }}
```

## Docker Compose Files for CI

```yaml
# docker-compose.test.yml — Used in CI for integration testing
# This companion file enables services and runs tests in containers.
#
# version: '3.8'
#
# services:
#   app:
#     build:
#       context: .
#       target: test
#     environment:
#       NODE_ENV: test
#       DATABASE_URL: postgresql://testuser:testpass@postgres:5432/testdb
#       REDIS_URL: redis://redis:6379
#     depends_on:
#       postgres:
#         condition: service_healthy
#       redis:
#         condition: service_healthy
#     command: npm run test:integration
#
#   postgres:
#     image: postgres:16-alpine
#     environment:
#       POSTGRES_DB: testdb
#       POSTGRES_USER: testuser
#       POSTGRES_PASSWORD: testpass
#     healthcheck:
#       test: ["CMD-SHELL", "pg_isready -U testuser -d testdb"]
#       interval: 5s
#       timeout: 5s
#       retries: 5
#
#   redis:
#     image: redis:7-alpine
#     healthcheck:
#       test: ["CMD", "redis-cli", "ping"]
#       interval: 5s
#       timeout: 5s
#       retries: 5


# docker-compose.prod.yml — Staging/production deployment
#
# version: '3.8'
#
# services:
#   app:
#     image: ghcr.io/my-org/my-app:latest
#     ports:
#       - "80:3000"
#     environment:
#       NODE_ENV: production
#       DATABASE_URL: ${DATABASE_URL}
#       REDIS_URL: ${REDIS_URL}
#     deploy:
#       replicas: 3
#       restart_policy:
#         condition: any
#     healthcheck:
#       test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
#       interval: 30s
#       timeout: 10s
#       retries: 3
#
#   nginx:
#     image: nginx:alpine
#     ports:
#       - "443:443"
#     volumes:
#       - ./nginx.conf:/etc/nginx/nginx.conf:ro
#     depends_on:
#       - app
```

## Caching Optimizations for Docker Builds

```yaml
name: Optimized Docker Builds

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Cache Docker layers
        uses: actions/cache@v4
        with:
          path: /tmp/.buildx-cache
          key: ${{ runner.os }}-buildx-${{ hashFiles('Dockerfile', '**/package-lock.json') }}
          restore-keys: |
            ${{ runner.os }}-buildx-
      
      - name: Build with cache
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: |
            type=local,src=/tmp/.buildx-cache
            type=gha
          cache-to: |
            type=local,dest=/tmp/.buildx-cache-new,mode=max
            type=gha,mode=max
      
      # Prune cache to avoid unlimited growth
      - name: Move cache
        run: |
          rm -rf /tmp/.buildx-cache
          mv /tmp/.buildx-cache-new /tmp/.buildx-cache
```