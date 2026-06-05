---
language: shell
tags: [docker, cli]
title: Docker Commands
description: Common Docker workflows: build, run, compose, cleanup, debugging.
source: pattern
---

```shell
#!/usr/bin/env bash
# ======= Build & Run =======
docker build -t myapp:latest .
docker run -d --name myapp -p 8080:80 myapp:latest

# ======= Docker Compose =======
docker compose up -d                            # start all services
docker compose down                             # stop and remove
docker compose logs -f                          # follow all logs
docker compose logs web -f                      # follow one service
docker compose exec web bash                    # shell into running container
docker compose restart web                      # restart one service

# ======= Images & Containers =======
docker ps                                       # running containers
docker ps -a                                    # all containers
docker images                                   # all images
docker rmi <image_id>                           # remove image
docker rm <container_id>                        # remove container
docker system prune -f                          # clean up dangling resources
docker system prune -a --volumes                # clean up EVERYTHING

# ======= Debugging =======
docker logs <container_id>                      # see logs
docker exec -it <container_id> sh               # shell into container
docker inspect <container_id>                   # detailed info
docker stats                                    # live resource usage

# ======= Copy files =======
docker cp <container_id>:/app/output.txt ./
docker cp ./input.txt <container_id>:/app/
```
