---
language: docker
tags: [networking, volumes, bridge, bind-mount, tmpfs]
title: Docker Networking & Volumes
description: Bridge/host/overlay networks, named volumes, bind mounts, tmpfs mounts.
source: pattern
---

```docker
# Create a custom bridge network
docker network create --driver bridge --subnet 172.20.0.0/16 --gateway 172.20.0.1 app-net

# Run containers on the custom network
docker run -d --name app --network app-net --ip 172.20.0.10 nginx:alpine
docker run -d --name cache --network app-net --ip 172.20.0.20 redis:7-alpine

# Named volume with driver options
docker volume create --driver local \
  --opt type=nfs \
  --opt o=addr=192.168.1.100,rw \
  --opt device=:/exported/path \
  shared-data

# Bind mount with :ro and SELinux relabeling
docker run -d --name web \
  -v /host/www:/usr/share/nginx/html:ro,Z \
  nginx:alpine

# tmpfs for ephemeral state
docker run -d --name session \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  redis:7-alpine

# Inspect network
docker network inspect app-net

# Connect running container to network
docker network connect --alias api backend api-container

```
