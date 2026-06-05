---
language: c
tags: [socket, tcp, server, bind, listen, accept, connect, networking]
title: TCP Socket Programming
description: socket/bind/listen/accept/connect — a minimal TCP echo server.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>

#define PORT 9090
#define BUF_SIZE 1024

int main(void) {
    int server_fd, client_fd;
    struct sockaddr_in addr;
    int opt = 1;

    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) { perror("socket"); return 1; }

    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof opt);

    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(PORT);

    if (bind(server_fd, (struct sockaddr *)&addr, sizeof addr) < 0) {
        perror("bind"); close(server_fd); return 1;
    }

    if (listen(server_fd, 5) < 0) {
        perror("listen"); close(server_fd); return 1;
    }
    printf("Echo server on port %d\n", PORT);

    client_fd = accept(server_fd, NULL, NULL);
    if (client_fd < 0) { perror("accept"); close(server_fd); return 1; }

    char buf[BUF_SIZE];
    ssize_t n;
    while ((n = read(client_fd, buf, sizeof buf - 1)) > 0) {
        buf[n] = '\0';
        printf("received: %s", buf);
        write(client_fd, buf, n);
    }

    close(client_fd);
    close(server_fd);
    return 0;
}

```
