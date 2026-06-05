---
language: kubernetes
tags: [configmap, secret, env, volume-mount, immutable]
title: ConfigMaps & Secrets
description: ConfigMap from literal/file, Secret, envFrom, volume mount, immutable.
source: pattern
---

```kubernetes
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: production
  labels:
    app: web
immutable: false
data:
  # Literal key-value pairs
  NODE_ENV: "production"
  LOG_LEVEL: "info"
  API_PORT: "8080"
  # Structured config
  app.yaml: |
    features:
      signup: true
      dark_mode: false
    limits:
      max_upload_mb: 50
      rate_per_minute: 100

---
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
  namespace: production
type: Opaque
stringData:
  url: "postgresql://app:${DB_PASSWORD}@db.internal:5432/mydb"
  username: "app"
  password: "s3cure-p@ssword"
---
# Secrets must be encoded in base64 when not using stringData
apiVersion: v1
kind: Secret
metadata:
  name: tls-cert
  namespace: production
type: kubernetes.io/tls
data:
  tls.crt: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...
  tls.key: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t...

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
  namespace: production
spec:
  template:
    spec:
      containers:
        - name: app
          image: web-app:latest
          envFrom:
            - configMapRef:
                name: app-config
            - secretRef:
                name: db-credentials
          env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: password
          volumeMounts:
            - name: config-volume
              mountPath: /etc/app
              readOnly: true
      volumes:
        - name: config-volume
          configMap:
            name: app-config
            items:
              - key: app.yaml
                path: app.yaml
---
# Immutable ConfigMap (cannot be updated, only recreated)
apiVersion: v1
kind: ConfigMap
metadata:
  name: base-config
  namespace: production
immutable: true
data:
  timezone: "UTC"
  locale: "en-US"

```
