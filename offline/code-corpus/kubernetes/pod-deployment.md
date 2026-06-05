---
language: kubernetes
tags: [deployment, pods, replicas, strategy, probes]
title: Pods & Deployments
description: Deployment spec, replicas, strategy, selector, containers, ports, probes.
source: pattern
---

```kubernetes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
  namespace: production
  labels:
    app: web
    tier: frontend
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
        version: "1.2.3"
    spec:
      containers:
        - name: app
          image: myregistry.azurecr.io/web-app:1.2.3
          imagePullPolicy: Always
          ports:
            - containerPort: 8080
              protocol: TCP
              name: http
            - containerPort: 8443
              protocol: TCP
              name: https
          env:
            - name: NODE_ENV
              value: "production"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: url
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 15
            timeoutSeconds: 3
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          startupProbe:
            httpGet:
              path: /startup
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 5
            failureThreshold: 30
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 1001
            capabilities:
              drop: ["ALL"]
      terminationGracePeriodSeconds: 60
      imagePullSecrets:
        - name: registry-credentials
---
apiVersion: v1
kind: Pod
metadata:
  name: web-app-canary
  namespace: production
  labels:
    app: web
    version: canary
spec:
  containers:
    - name: app
      image: myregistry.azurecr.io/web-app:canary
      ports:
        - containerPort: 8080

```
