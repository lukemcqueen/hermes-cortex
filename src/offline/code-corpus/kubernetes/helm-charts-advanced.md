---
language: yaml
tags: [kubernetes, helm, charts, deployment, package-management]
title: Helm Charts Advanced
description: Chart structure deep dive, values schema with JSON Schema, dependency management, hooks, template functions and pipelines, subcharts and global values, testing with helm test.
source: pattern
---

```yaml
# =============================================================================
# ADVANCED HELM CHART STRUCTURE
# =============================================================================

# --- Chart.yaml (with all fields) ---
apiVersion: v2
name: platform-app
description: Advanced multi-component Helm chart with subcharts and hooks
type: application
version: 2.1.0
appVersion: "4.5.0"
kubeVersion: ">=1.25.0-0"
home: https://github.com/example/platform-app
icon: https://example.com/icon.png
keywords:
  - platform
  - microservices
sources:
  - https://github.com/example/platform-app
maintainers:
  - name: Platform Team
    email: platform@example.com
    url: https://platform.example.com
deprecated: false
annotations:
  artifacthub.io/changes: |
    - kind: added
      description: Support for custom metrics adapter
    - kind: changed
      description: Upgraded postgresql dependency to 12.x

# --- values.schema.json (JSON Schema validation) ---
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["global", "app"],
  "properties": {
    "global": {
      "type": "object",
      "required": ["environment"],
      "properties": {
        "environment": {
          "type": "string",
          "enum": ["dev", "staging", "prod"],
          "description": "Deployment environment"
        },
        "imageRegistry": {
          "type": "string",
          "pattern": "^[a-zA-Z0-9.-]+(:[0-9]+)?/[a-z0-9]+(/[a-z0-9]+)*$",
          "description": "Global image registry override"
        }
      }
    },
    "app": {
      "type": "object",
      "required": ["replicaCount", "image"],
      "properties": {
        "replicaCount": {
          "type": "integer",
          "minimum": 1,
          "maximum": 50,
          "description": "Number of replicas"
        },
        "image": {
          "type": "object",
          "required": ["repository", "tag"],
          "properties": {
            "repository": { "type": "string", "minLength": 1 },
            "tag": { "type": "string", "pattern": "^(latest|[0-9]+\\.[0-9]+\\.[0-9]+(-[a-zA-Z0-9]+)?)$" },
            "pullPolicy": { "type": "string", "enum": ["Always", "IfNotPresent", "Never"] }
          }
        },
        "resources": {
          "type": "object",
          "properties": {
            "requests": {
              "type": "object",
              "properties": {
                "cpu": { "type": "string", "pattern": "^[0-9]+m?$" },
                "memory": { "type": "string", "pattern": "^[0-9]+(Ki|Mi|Gi|Ti)$" }
              }
            },
            "limits": {
              "type": "object",
              "properties": {
                "cpu": { "type": "string", "pattern": "^[0-9]+m?$" },
                "memory": { "type": "string", "pattern": "^[0-9]+(Ki|Mi|Gi|Ti)$" }
              }
            }
          }
        },
        "probes": {
          "type": "object",
          "properties": {
            "liveness": { "$ref": "#/definitions/probe" },
            "readiness": { "$ref": "#/definitions/probe" },
            "startup": { "$ref": "#/definitions/probe" }
          }
        }
      }
    },
    "ingress": {
      "type": "object",
      "properties": {
        "enabled": { "type": "boolean", "default": false },
        "className": { "type": "string" },
        "annotations": { "type": "object" },
        "tls": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "secretName": { "type": "string" },
              "hosts": {
                "type": "array",
                "items": { "type": "string", "format": "hostname" }
              }
            }
          }
        }
      }
    }
  },
  "definitions": {
    "probe": {
      "type": "object",
      "properties": {
        "httpGet": {
          "type": "object",
          "properties": {
            "path": { "type": "string" },
            "port": { "type": "integer" }
          }
        },
        "initialDelaySeconds": { "type": "integer", "minimum": 0 },
        "periodSeconds": { "type": "integer", "minimum": 1 },
        "timeoutSeconds": { "type": "integer", "minimum": 1 },
        "failureThreshold": { "type": "integer", "minimum": 1 }
      }
    }
  }
}

# =============================================================================
# DEPENDENCY MANAGEMENT (Chart.yaml dependencies)
# =============================================================================

# --- Chart.yaml dependency block (already shown above) ---
# Dependency file: charts/postgresql/, charts/redis/
# Override subchart values via:

# --- values.yaml with subchart overrides ---
global:
  environment: dev
  imageRegistry: docker.io/myorg

app:
  replicaCount: 3
  image:
    repository: myorg/platform-app
    tag: 4.5.0
    pullPolicy: IfNotPresent
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 1Gi

# Subchart value overrides (nested under the chart name)
postgresql:
  enabled: true
  global:
    postgresql:
      auth:
        postgresPassword: "#####"  # override via --set
        database: platform
        username: app
        existingSecret: platform-db-creds
  primary:
    persistence:
      size: 50Gi
      storageClass: premium-rwo
    resources:
      requests:
        cpu: 1000m
        memory: 2Gi
  readReplicas:
    replicaCount: 2
    persistence:
      enabled: false

redis:
  enabled: true
  architecture: replication
  auth:
    enabled: true
    existingSecret: platform-redis-creds
  master:
    persistence:
      size: 10Gi
  replica:
    replicaCount: 2

# --- Chart.lock (auto-generated by helm dependency update) ---
# dependencies:
# - name: postgresql
#   repository: https://charts.bitnami.com/bitnami
#   version: 12.1.0
# - name: redis
#   repository: https://charts.bitnami.com/bitnami
#   version: 17.3.0
# digest: sha256:abc123...

# =============================================================================
# HELM HOOKS
# =============================================================================

# --- templates/migration-job.yaml (post-install / post-upgrade hook) ---
apiVersion: batch/v1
kind: Job
metadata:
  name: "{{ .Release.Name }}-db-migration"
  annotations:
    "helm.sh/hook": post-install,post-upgrade
    "helm.sh/hook-weight": "-5"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migration
          image: "{{ .Values.app.image.repository }}:{{ .Values.app.image.tag }}"
          command: ["/app/bin/migrate"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: platform-db-url
                  key: url
---
# --- templates/pre-upgrade-backup.yaml (pre-upgrade hook) ---
apiVersion: batch/v1
kind: Job
metadata:
  name: "{{ .Release.Name }}-pre-upgrade-backup"
  annotations:
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "-10"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: backup
          image: bitnami/kubectl:latest
          command:
            - /bin/sh
            - -c
            - |
              kubectl exec deploy/{{ .Release.Name }}-app -- pg_dump -Fc > /tmp/backup.dump
              kubectl cp "{{ .Release.Name }}-app-pod:/tmp/backup.dump" /backups/pre-upgrade-{{ .Release.Revision }}.dump
---
# --- templates/test-db-connection.yaml (pre-delete hook) ---
apiVersion: batch/v1
kind: Job
metadata:
  name: "{{ .Release.Name }}-cleanup-check"
  annotations:
    "helm.sh/hook": pre-delete
    "helm.sh/hook-weight": "0"
    "helm.sh/hook-delete-policy": hook-succeeded
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: cleanup-check
          image: bitnami/kubectl:latest
          command:
            - /bin/sh
            - -c
            - |
              echo "Checking for remaining PVCs before deletion..."
              kubectl get pvc -l app.kubernetes.io/instance={{ .Release.Name }}
              # If data is critical, abort with non-zero exit
              if [ "$(kubectl get pvc -l app.kubernetes.io/instance={{ .Release.Name }} -o name | wc -l)" -gt 0 ]; then
                echo "WARNING: PVCs will be orphaned on deletion" >&2
              fi

# =============================================================================
# TEMPLATE FUNCTIONS AND PIPELINES
# =============================================================================

# --- templates/_helpers.tpl ---
{{- define "platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "platform.fullname" -}}
{{- if .Values.fullnameOverride }}
{{-   .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{-   $name := default .Chart.Name .Values.nameOverride }}
{{-   if contains $name .Release.Name }}
{{-     .Release.Name | trunc 63 | trimSuffix "-" }}
{{-   else }}
{{-     printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{-   end }}
{{- end }}
{{- end }}

{{- define "platform.labels" -}}
helm.sh/chart: "{{ include "platform.name" . }}-{{ .Chart.Version | replace "+" "_" }}"
{{- if .Values.global.environment }}
environment: {{ .Values.global.environment }}
{{- end }}
app.kubernetes.io/name: {{ include "platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: {{ .Values.app.component | default "backend" | quote }}
{{- end }}

{{- define "platform.image" -}}
{{- $registry := .Values.global.imageRegistry | default .Values.app.image.repository -}}
{{- printf "%s:%s" $registry .Values.app.image.tag -}}
{{- end }}

{{- define "platform.probe" -}}
{{- $probe := .probe -}}
{{- if $probe.httpGet }}
httpGet:
  path: {{ $probe.httpGet.path }}
  port: {{ $probe.httpGet.port }}
{{- else if $probe.exec }}
exec:
  command: {{ toYaml $probe.exec.command | nindent 4 }}
{{- else if $probe.tcpSocket }}
tcpSocket:
  port: {{ $probe.tcpSocket.port }}
{{- end }}
initialDelaySeconds: {{ $probe.initialDelaySeconds | default 5 }}
periodSeconds: {{ $probe.periodSeconds | default 10 }}
timeoutSeconds: {{ $probe.timeoutSeconds | default 1 }}
failureThreshold: {{ $probe.failureThreshold | default 3 }}
successThreshold: {{ $probe.successThreshold | default 1 }}
{{- end }}

# Pipelines and advanced template functions
{{- define "platform.resources" -}}
{{- $cpuRequests := .Values.app.resources.requests.cpu | default "100m" -}}
{{- $memRequests := .Values.app.resources.requests.memory | default "128Mi" -}}
{{- $cpuLimits   := .Values.app.resources.limits.cpu | default $cpuRequests -}}
{{- $memLimits   := .Values.app.resources.limits.memory | default (($memRequests | trimSuffix "i" | trimSuffix "Mi" | int | mulf 2 | printf "%dMi")) -}}
requests:
  cpu: "{{ $cpuRequests }}"
  memory: "{{ $memRequests }}"
limits:
  cpu: "{{ $cpuLimits }}"
  memory: "{{ $memLimits }}"
{{- end }}

# --- templates/configmap.yaml (using template functions) ---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "platform.fullname" . }}-config
  labels:
    {{- include "platform.labels" . | nindent 4 }}
data:
  # Using printf and ternary
  NODE_ENV: {{ .Values.global.environment | upper | quote }}
  LOG_LEVEL: {{ .Values.app.logLevel | default .Values.global.environment | ternary "debug" "info" (eq .Values.global.environment "dev") | quote }}
  
  # Using fromYaml/toYaml/toJson
  CONFIG_JSON: {{ .Values.app.additionalConfig | default dict | toJson | quote }}
  
  # Using regex patterns
  APP_VERSION: {{ .Chart.AppVersion | replace "+" "-" | quote }}
  
  # Using splitList and join
  FEATURE_FLAGS: {{ join "," (splitList "," (.Values.app.featureFlags | default "")) | quote }}
  
  # Using hasKey and dig
  {{- if hasKey .Values.app "customConfig" }}
  CUSTOM_CONFIG: |
    {{- .Values.app.customConfig | toYaml | nindent 4 }}
  {{- end }}

# --- templates/deployment.yaml (advanced template) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "platform.fullname" . }}
  labels:
    {{- include "platform.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.app.replicaCount }}
  {{- end }}
  revisionHistoryLimit: {{ .Values.app.revisionHistoryLimit | default 3 }}
  strategy:
    type: {{ .Values.app.strategy.type | default "RollingUpdate" }}
    {{- if eq (.Values.app.strategy.type | default "RollingUpdate") "RollingUpdate" }}
    rollingUpdate:
      maxSurge: {{ .Values.app.strategy.maxSurge | default "25%" }}
      maxUnavailable: {{ .Values.app.strategy.maxUnavailable | default 0 }}
    {{- end }}
  selector:
    matchLabels:
      {{- include "platform.labels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "platform.labels" . | nindent 8 }}
      {{- with .Values.app.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
    spec:
      {{- with .Values.app.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "platform.fullname" . }}
      securityContext:
        {{- toYaml .Values.app.podSecurityContext | default dict | nindent 8 }}
      {{- if .Values.app.initContainers }}
      initContainers:
        {{- toYaml .Values.app.initContainers | nindent 8 }}
      {{- end }}
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ include "platform.image" . }}"
          imagePullPolicy: {{ .Values.app.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.app.service.port | default 8080 }}
              protocol: TCP
          {{- if .Values.app.probes.liveness }}
          livenessProbe:
            {{- include "platform.probe" (dict "probe" .Values.app.probes.liveness) | nindent 12 }}
          {{- end }}
          {{- if .Values.app.probes.readiness }}
          readinessProbe:
            {{- include "platform.probe" (dict "probe" .Values.app.probes.readiness) | nindent 12 }}
          {{- end }}
          env:
            {{- range $key, $value := .Values.app.env }}
            - name: {{ $key }}
              value: {{ $value | quote }}
            {{- end }}
            {{- range .Values.app.envFromSecret }}
            - name: {{ .key }}
              valueFrom:
                secretKeyRef:
                  name: {{ .secret }}
                  key: {{ .key }}
            {{- end }}
          envFrom:
            - configMapRef:
                name: {{ include "platform.fullname" . }}-config
          resources:
            {{- include "platform.resources" . | nindent 12 }}
          volumeMounts:
            {{- toYaml .Values.app.extraVolumeMounts | default list | nindent 12 }}
      volumes:
        {{- toYaml .Values.app.extraVolumes | default list | nindent 8 }}
      {{- with .Values.app.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.app.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.app.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}

# =============================================================================
# GLOBAL VALUES AND SUBCHARTS
# =============================================================================

# --- values.yaml excerpt (global values propagate to subcharts) ---
global:
  environment: prod
  imageRegistry: docker.io/myorg
  storageClass: premium-rwo
  monitoring:
    enabled: true
    metricsPort: 9090

# Subcharts automatically receive global.* values.
# In a subchart template: {{ .Values.global.environment }}

# =============================================================================
# HELM TEST (helm test <release>)
# =============================================================================

# --- templates/tests/test-connection.yaml ---
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-connection-test"
  annotations:
    "helm.sh/hook": test
    "helm.sh/hook-delete-policy": hook-succeeded
spec:
  containers:
    - name: test-connection
      image: curlimages/curl:latest
      command:
        - /bin/sh
        - -ec
        - |
          echo "Testing service connectivity..."
          curl --fail --max-time 5 http://{{ include "platform.fullname" . }}:{{ .Values.app.service.port }}/health
          echo "Service is healthy!"
  restartPolicy: Never
---
# --- templates/tests/test-db-connection.yaml ---
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-db-test"
  annotations:
    "helm.sh/hook": test
    "helm.sh/hook-delete-policy": hook-succeeded
spec:
  containers:
    - name: test-db
      image: bitnami/postgresql:15
      command:
        - /bin/sh
        - -ec
        - |
          PGPASSWORD=$(cat /etc/db-creds/password) \
            psql -h {{ .Release.Name }}-postgresql -U app -d platform -c "SELECT 1;"
          echo "Database connection successful!"
      env:
        - name: PGSSLMODE
          value: require
      volumeMounts:
        - name: db-creds
          mountPath: /etc/db-creds
          readOnly: true
  volumes:
    - name: db-creds
      secret:
        secretName: platform-db-creds
  restartPolicy: Never
---
# --- templates/tests/test-helm-unit.yaml ---
# Uses helm-unittest plugin (helm unittest ./templates)
# Unit tests live in tests/ directory
apiVersion: v1
kind: Pod
metadata:
  name: "{{ .Release.Name }}-unit-test"
  annotations:
    "helm.sh/hook": test
    "helm.sh/hook-delete-policy": hook-succeeded
spec:
  containers:
    - name: unittest
      image: alpine/helm:latest
      command:
        - /bin/sh
        - -ec
        - |
          cd /chart
          helm unittest ./templates
  restartPolicy: Never
EOF
```