---
language: kubernetes
tags: [helm, chart, values, templates, helpers]
title: Helm Charts
description: Chart.yaml, values.yaml, templates, _helpers.tpl, with range, include, template.
source: pattern
---

```kubernetes
# --- Chart.yaml ---
apiVersion: v2
name: web-app
description: A Helm chart for the web application
type: application
version: 0.1.0
appVersion: "1.2.3"
home: https://github.com/example/web-app
maintainers:
  - name: Platform Team
    email: platform@example.com
dependencies:
  - name: postgresql
    version: "~12.0"
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled
  - name: redis
    version: "~17.0"
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled

# --- values.yaml ---
replicaCount: 3

image:
  repository: myregistry.azurecr.io/web-app
  tag: "1.2.3"
  pullPolicy: Always

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: app.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: web-app-tls
      hosts:
        - app.example.com

resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

env:
  NODE_ENV: production
  LOG_LEVEL: info

postgresql:
  enabled: true
  auth:
    database: myapp
    username: app

redis:
  enabled: true
  architecture: standalone

# --- templates/_helpers.tpl ---
{{- define "web-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "web-app.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "web-app.labels" -}}
helm.sh/chart: "{{ include "web-app.name" . }}-{{ .Chart.Version }}"
app.kubernetes.io/name: "{{ include "web-app.name" . }}"
app.kubernetes.io/instance: "{{ .Release.Name }}"
app.kubernetes.io/version: "{{ .Chart.AppVersion }}"
app.kubernetes.io/managed-by: "{{ .Release.Service }}"
{{- end }}

# --- templates/deployment.yaml ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "web-app.fullname" . }}
  labels:
    {{- include "web-app.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ include "web-app.name" . }}
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {{ include "web-app.name" . }}
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: 8080
              name: http
          env:
            {{- range $key, $val := .Values.env }}
            - name: {{ $key }}
              value: {{ $val | quote }}
            {{- end }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
EOF

```
