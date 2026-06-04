---
name: docker
description: |
  Build, run, and debug Docker images and compose setups with reproducible,
  minimal, and secure configurations.

  Triggers when user mentions:
  - "docker"
  - "dockerfile"
  - "docker compose"
  - "container"
  - "devcontainer"
  - "image build"
---

# Docker

## Purpose
Use containers safely for:
- local development
- testing
- deployment images

Only when containerization is actually required.

---

## Core Rule

Do not introduce Docker unless the project already uses it or requires it.

---

## Output (STRICT ORDER)

1. **Docker Config** (Dockerfile / compose)
2. **Explanation** (≤3 sentences)
3. **Verification**

---

## When to Use

Use for:

- Dockerfile creation or fixes
- docker-compose setup
- devcontainer setup
- containerized test runs
- environment parity issues
- deployment image debugging

Do NOT use for:
- normal local development without containers
- solving non-environment bugs

---

## Workflow (STRICT)

1. Identify container need
2. Inspect existing Docker setup
3. Make minimal change
4. Build image
5. Run container/test
6. Verify behavior
7. Fix only container-related issues

---

## Commands

```bash
./run build
./run up
./run down
./run restart
./run logs
./run ps
```

---

## Dockerfile Rules

* use minimal base image
* pin major versions (or exact when needed)
* separate build and runtime stages (multi-stage build)
* minimize layers
* avoid unnecessary packages
* use `.dockerignore`
* avoid copying entire repo blindly

---

## Example (Multi-stage)

```dockerfile id="vxtzpf"
FROM node:20 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=builder /app/dist ./dist
CMD ["node", "dist/index.js"]
```

---

## docker-compose Rules

* define services clearly
* separate dev vs production assumptions
* use volumes only when needed
* avoid hardcoding ports unless necessary
* use environment variables for config
* when creating or updating Postgres services, use `postgres:18.3-trixie`
* when creating or updating Redis services, use `redis:8.6.3-alpine`
* run all compose operations via `./run up|down|logs|build|ps|restart` — not raw `docker compose`

---

## Environment & Secrets

* NEVER bake secrets into images
* use `.env` or runtime env variables
* do not commit `.env` files
* validate required env vars at runtime

---

## Healthchecks

Prefer explicit healthchecks:

```yaml id="6l0z6i"
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:3000"]
  interval: 10s
  timeout: 5s
  retries: 3
```

---

## Networking

* use service names for internal communication
* avoid localhost assumptions between containers
* expose only required ports

---

## Performance

* reduce image size
* avoid unnecessary rebuilds
* cache dependencies (COPY package.json first)
* use slim/alpine images when safe

---

## Testing in Containers

Run:

```bash id="ezz8qz"
docker compose run --rm app test
```

Rules:

* ensure tests run successfully inside container
* verify environment parity with production when needed

---

## Verification

```txt id="8p1t3o"
docker build succeeds
→ container starts without errors
→ app/test command runs correctly
→ logs show expected behavior
```

---

## Debugging

Check:

* build logs
* container logs
* missing dependencies
* incorrect working directory
* port conflicts
* environment variables

---

## Safety Rules

* do not delete volumes/data without approval
* do not expose unnecessary ports
* do not run privileged containers unless required
* avoid root user when possible

---

## Anti-Patterns

Avoid:

* copying entire repo unnecessarily
* large bloated images
* mixing dev and prod config
* hardcoding secrets
* ignoring `.dockerignore`
* rebuilding everything unnecessarily
* using Docker to mask code issues

---

## Integration with AgentKore

```txt
repo-discovery
→ docker
→ testing-strategy
→ change-test-loop
```

---

## Goal

Provide reproducible, minimal, and secure container setups that:

* work consistently across environments
* are easy to debug
* do not introduce unnecessary complexity