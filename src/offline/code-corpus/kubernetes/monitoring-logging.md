---
language: yaml
tags: [kubernetes, monitoring, prometheus, logging, observability]
title: K8s Monitoring and Logging
description: Prometheus Operator with ServiceMonitor and PodMonitor, Grafana dashboards, Loki for logging, metrics-server for HPA, custom metrics adapter, AlertManager rules, EFK stack.
source: pattern
---

```yaml
# =============================================================================
# PROMETHEUS OPERATOR — ServiceMonitor & PodMonitor
# =============================================================================

# --- Prometheus Operator (requires prometheus-operator CRDs installed) ---

# ServiceMonitor: Scrape metrics from a Service via endpoint selectors
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: web-app-monitor
  namespace: monitoring
  labels:
    release: kube-prometheus-stack  # Must match Prometheus CR selector
    app: web-app
spec:
  selector:
    matchLabels:
      app: web-app  # Selects Service with this label
  namespaceSelector:
    any: true  # Scrape across all namespaces
    # matchNames: ["production"]  # Or restrict to specific namespaces
  endpoints:
    - port: metrics        # Named port on the Service
      path: /metrics       # Standard Prometheus metrics path
      interval: 15s        # Scrape interval
      scrapeTimeout: 10s
      scheme: http
      honorLabels: true
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_node_name]
          action: replace
          targetLabel: node
        - sourceLabels: [__meta_kubernetes_namespace]
          action: replace
          targetLabel: namespace
      metricRelabelings:
        - sourceLabels: [__name__]
          regex: "http_request_duration_seconds_.*"
          action: keep       # Only keep duration metrics
---
# ServiceMonitor with TLS and basic auth
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: internal-api-monitor
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  selector:
    matchLabels:
      app: internal-api
  namespaceSelector:
    matchNames: ["production"]
  endpoints:
    - port: https-metrics
      path: /metrics
      scheme: https
      interval: 30s
      tlsConfig:
        insecureSkipVerify: false
        ca:
          secret:
            name: monitoring-ca
            key: ca.crt
        cert:
          secret:
            name: monitoring-certs
            key: tls.crt
        keySecret:
          name: monitoring-certs
          key: tls.key
      basicAuth:
        username:
          name: metrics-auth
          key: username
        password:
          name: metrics-auth
          key: password
---
# PodMonitor: Scrape metrics directly from Pods (no Service required)
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: sidecar-monitor
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  selector:
    matchLabels:
      metrics-sidecar: "true"
  namespaceSelector:
    any: true
  podMetricsEndpoints:
    - port: metrics
      path: /metrics
      interval: 15s
      relabelings:
        - action: labelmap
          regex: __meta_kubernetes_pod_label_(.+)
---
# Prometheus CR (custom resource that controls Prometheus itself)
apiVersion: monitoring.coreos.com/v1
kind: Prometheus
metadata:
  name: k8s
  namespace: monitoring
spec:
  version: v2.45.0
  serviceAccountName: prometheus
  serviceMonitorSelector:
    matchLabels:
      release: kube-prometheus-stack
  podMonitorSelector:
    matchLabels:
      release: kube-prometheus-stack
  ruleSelector:
    matchLabels:
      release: kube-prometheus-stack
  alerting:
    alertmanagers:
      - namespace: monitoring
        name: alertmanager-operated
        port: web
  resources:
    requests:
      memory: 2Gi
      cpu: 500m
    limits:
      memory: 4Gi
      cpu: 1000m
  retention: 15d
  retentionSize: 50GB
  storage:
    volumeClaimTemplate:
      spec:
        storageClassName: standard
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 100Gi
  additionalScrapeConfigs:
    name: additional-scrape-configs
    key: prometheus-additional.yaml

# =============================================================================
# GRAFANA DASHBOARD (as code — using Grafana Operator)
# =============================================================================

apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: kubernetes-cluster-dashboard
  namespace: monitoring
  labels:
    app: grafana
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana"
  configMapRef:
    name: cluster-dashboard-config
    key: cluster-dashboard.json
  # Or inline JSON:
  # json: >
  #   { "title": "Kubernetes Cluster", ... }

# --- Grafana datasource (Loki) ---
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDatasource
metadata:
  name: loki-datasource
  namespace: monitoring
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana"
  datasource:
    name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: false
    editable: false
    jsonData:
      maxLines: 1000
      timeout: 60

# =============================================================================
# LOKI — LOG AGGREGATION
# =============================================================================

# --- Loki Stack (via helm: grafana/loki-stack) ---
# Simple Loki instance with file-based storage
apiVersion: loki.grafana.com/v1
kind: LokiStack
metadata:
  name: loki
  namespace: monitoring
spec:
  size: 1x.small  # 1x.small, 1x.medium, 1x.large
  storage:
    schemas:
      - version: v13
        effectiveDate: "2024-01-01"
    secret:
      name: loki-storage
      type: s3
  tenants:
    mode: openshift-logging
  limits:
    global:
      maxEntriesLimitPerQuery: 10000
      ingestionRateMb: 10
      ingestionBurstSizeMb: 20
---
# Promtail: Log shipping DaemonSet (scrape pod logs)
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: promtail
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: promtail
  template:
    metadata:
      labels:
        app: promtail
    spec:
      serviceAccountName: promtail
      containers:
        - name: promtail
          image: grafana/promtail:2.9.0
          args:
            - -config.file=/etc/promtail/config.yaml
          volumeMounts:
            - name: config
              mountPath: /etc/promtail
            - name: varlog
              mountPath: /var/log
            - name: docker-containers
              mountPath: /var/lib/docker/containers
              readOnly: true
            - name: pods
              mountPath: /var/log/pods
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: promtail-config
        - name: varlog
          hostPath:
            path: /var/log
        - name: docker-containers
          hostPath:
            path: /var/lib/docker/containers
        - name: pods
          hostPath:
            path: /var/log/pods
---
# Promtail config (promtail-config ConfigMap)
apiVersion: v1
kind: ConfigMap
metadata:
  name: promtail-config
  namespace: monitoring
data:
  config.yaml: |
    server:
      http_listen_port: 9080
      grpc_listen_port: 0
    positions:
      filename: /var/log/positions.yaml
    clients:
      - url: http://loki:3100/loki/api/v1/push
    scrape_configs:
      - job_name: kubernetes-pods
        pipeline_stages:
          - cri: {}
          - regex:
              expression: "^(?s)(?P<time>\\S+?)\\s+(?P<stream>stdout|stderr)\\s+(?P<flags>\\S+?)\\s+(?P<content>.*)$"
          - timestamp:
              source: time
              format: RFC3339Nano
          - labels:
              stream:
        kubernetes_sd_configs:
          - role: pod
        relabel_configs:
          - action: labelmap
            regex: __meta_kubernetes_pod_label_(.+)
          - source_labels: [__meta_kubernetes_namespace]
            action: replace
            target_label: namespace
          - source_labels: [__meta_kubernetes_pod_name]
            action: replace
            target_label: pod
          - source_labels: [__meta_kubernetes_pod_container_name]
            action: replace
            target_label: container
          - replacement: /var/log/pods/*$1/*.log
            separator: /
            source_labels:
              - __meta_kubernetes_pod_uid
              - __meta_kubernetes_pod_container_name
            target_label: __path__

# =============================================================================
# METRICS-SERVER FOR HPA
# =============================================================================

# --- metrics-server (via helm: metrics-server/metrics-server) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-server
  namespace: kube-system
  labels:
    k8s-app: metrics-server
spec:
  replicas: 2
  selector:
    matchLabels:
      k8s-app: metrics-server
  template:
    metadata:
      labels:
        k8s-app: metrics-server
    spec:
      containers:
        - name: metrics-server
          image: registry.k8s.io/metrics-server/metrics-server:v0.7.1
          args:
            - --kubelet-insecure-tls
            - --kubelet-preferred-address-types=InternalIP,Hostname,InternalDNS,ExternalDNS
            - --metric-resolution=15s
          ports:
            - containerPort: 4443
              name: https
          readinessProbe:
            httpGet:
              path: /readyz
              port: 4443
              scheme: HTTPS
          livenessProbe:
            httpGet:
              path: /livez
              port: 4443
              scheme: HTTPS
---
# HorizontalPodAutoscaler using metrics-server resource metrics
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: web-app-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web-app
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max

# =============================================================================
# CUSTOM METRICS ADAPTER (Prometheus Adapter)
# =============================================================================

# --- Prometheus Adapter (custom.metrics.k8s.io) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus-adapter
  namespace: monitoring
spec:
  replicas: 2
  selector:
    matchLabels:
      app: prometheus-adapter
  template:
    metadata:
      labels:
        app: prometheus-adapter
    spec:
      containers:
        - name: adapter
          image: registry.k8s.io/prometheus-adapter/prometheus-adapter:v0.11.2
          args:
            - --secure-port=6443
            - --tls-cert-file=/etc/certs/tls.crt
            - --tls-private-key-file=/etc/certs/tls.key
            - --prometheus-url=http://prometheus-operated:9090/
            - --metrics-relist-interval=30s
            - --v=4
          ports:
            - containerPort: 6443
          volumeMounts:
            - name: config
              mountPath: /etc/adapter
              readOnly: true
            - name: certs
              mountPath: /etc/certs
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: adapter-config
        - name: certs
          secret:
            secretName: adapter-certs
---
# Prometheus Adapter config — custom metrics rules
apiVersion: v1
kind: ConfigMap
metadata:
  name: adapter-config
  namespace: monitoring
data:
  config.yaml: |
    rules:
      - seriesQuery: 'http_requests_total{namespace!="",pod!=""}'
        resources:
          overrides:
            namespace: {resource: "namespace"}
            pod: {resource: "pod"}
        name:
          matches: "^(.*)_total$"
          as: "${1}_per_second"
        metricsQuery: 'sum(rate(<<.Series>>{<<.LabelMatchers>>}[2m])) by (<<.GroupBy>>)'
      - seriesQuery: 'http_request_duration_seconds_sum{namespace!="",pod!=""}'
        resources:
          overrides:
            namespace: {resource: "namespace"}
            pod: {resource: "pod"}
        name:
          matches: "http_request_duration_seconds"
          as: "http_request_duration_avg_seconds"
        metricsQuery: 'sum(rate(<<.Series>>{<<.LabelMatchers>>}[1m])) by (<<.GroupBy>>) / sum(rate(http_request_duration_seconds_count{<<.LabelMatchers>>}[1m])) by (<<.GroupBy>>)'
      - seriesQuery: 'rabbitmq_queue_messages{namespace!="",pod!=""}'
        resources:
          overrides:
            namespace: {resource: "namespace"}
            pod: {resource: "pod"}
        name:
          matches: "rabbitmq_queue_messages"
          as: "rabbitmq_queue_depth"
        metricsQuery: '<<.Series>>{<<.LabelMatchers>>}'
---
# HPA using custom metrics from prometheus-adapter
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: web-app-custom-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web-app
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: 1000
    - type: Pods
      pods:
        metric:
          name: rabbitmq_queue_depth
        target:
          type: AverageValue
          averageValue: 50

# =============================================================================
# ALERTMANAGER RULES
# =============================================================================

# --- PrometheusRule (alerting and recording rules) ---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: kubernetes-alerts
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  groups:
    - name: kubernetes-apps
      interval: 30s
      rules:
        - alert: HighErrorRate
          expr: |
            sum(rate(http_requests_total{status=~"5.."}[5m])) /
            sum(rate(http_requests_total[5m])) > 0.05
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "High HTTP error rate ({{ $value | humanizePercentage }})"
            description: |
              {{ $labels.namespace }}/{{ $labels.pod }} is returning
              {{ $value | humanizePercentage }} 5xx errors.
        - alert: HighLatency
          expr: |
            histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "High latency (P95 > 1s) on {{ $labels.pod }}"
        - alert: PodNotReady
          expr: kube_pod_status_phase{phase="Running"} == 0
          for: 15m
          labels:
            severity: warning
          annotations:
            summary: "Pod {{ $labels.pod }} is not ready"
        - alert: PersistentVolumeUsageCritical
          expr: |
            (kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes) > 0.9
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "PVC {{ $labels.persistentvolumeclaim }} usage > 90%"
        - alert: HpaMaxedOut
          expr: kube_horizontalpodautoscaler_spec_max_replicas == kube_horizontalpodautoscaler_status_current_replicas
          for: 15m
          labels:
            severity: warning
          annotations:
            summary: "HPA {{ $labels.horizontalpodautoscaler }} is at max replicas"
    - name: kubernetes-cluster
      interval: 1m
      rules:
        - alert: NodeNotReady
          expr: kube_node_status_condition{condition="Ready",status="true"} == 0
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "Node {{ $labels.node }} is NotReady"
        - alert: NodeMemoryPressure
          expr: kube_node_status_condition{condition="MemoryPressure",status="true"} == 1
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Node {{ $labels.node }} has memory pressure"
        - alert: KubeAPIDown
          expr: absent(up{job="apiserver"}) == 1
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "Kubernetes API server is down"
    - name: custom-app-rules
      interval: 30s
      rules:
        - alert: QueueDepthHigh
          expr: rabbitmq_queue_depth > 100
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Queue depth {{ $value }} on {{ $labels.pod }}"
        - record: namespace:http_requests_per_second:avg5m
          expr: |
            sum(rate(http_requests_total[5m])) by (namespace)

# =============================================================================
# EFK STACK (Elasticsearch, Fluentd, Kibana)
# =============================================================================

# --- Elasticsearch (via ECK Operator: elastic/elasticsearch-operator) ---
apiVersion: elasticsearch.k8s.elastic.co/v1
kind: Elasticsearch
metadata:
  name: elasticsearch-cluster
  namespace: logging
spec:
  version: 8.11.0
  nodeSets:
    - name: master
      count: 3
      config:
        node.roles: ["master"]
        node.store.allow_mmap: false
      podTemplate:
        spec:
          containers:
            - name: elasticsearch
              resources:
                requests:
                  memory: 2Gi
                  cpu: 500m
                limits:
                  memory: 4Gi
      volumeClaimTemplates:
        - metadata:
            name: elasticsearch-data
          spec:
            storageClassName: standard
            accessModes: ["ReadWriteOnce"]
            resources:
              requests:
                storage: 50Gi
    - name: data
      count: 3
      config:
        node.roles: ["data", "ingest"]
        node.store.allow_mmap: false
      podTemplate:
        spec:
          containers:
            - name: elasticsearch
              resources:
                requests:
                  memory: 8Gi
                  cpu: 2
                limits:
                  memory: 16Gi
      volumeClaimTemplates:
        - metadata:
            name: elasticsearch-data
          spec:
            storageClassName: standard
            accessModes: ["ReadWriteOnce"]
            resources:
              requests:
                storage: 200Gi
---
# --- Kibana (via ECK Operator) ---
apiVersion: kibana.k8s.elastic.co/v1
kind: Kibana
metadata:
  name: kibana
  namespace: logging
spec:
  version: 8.11.0
  count: 2
  elasticsearchRef:
    name: elasticsearch-cluster
  config:
    server.publicBaseUrl: "https://kibana.example.com"
  podTemplate:
    spec:
      containers:
        - name: kibana
          resources:
            requests:
              memory: 1Gi
              cpu: 500m
            limits:
              memory: 2Gi
---
# --- Fluentd DaemonSet (log collector) ---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd
  namespace: logging
  labels:
    app: fluentd
spec:
  selector:
    matchLabels:
      app: fluentd
  template:
    metadata:
      labels:
        app: fluentd
    spec:
      serviceAccountName: fluentd
      containers:
        - name: fluentd
          image: fluent/fluentd-kubernetes-daemonset:v1.16-debian-elasticsearch8-1
          env:
            - name: FLUENT_ELASTICSEARCH_HOST
              value: "elasticsearch-cluster-es-http"
            - name: FLUENT_ELASTICSEARCH_PORT
              value: "9200"
            - name: FLUENT_ELASTICSEARCH_SCHEME
              value: "https"
            - name: FLUENT_ELASTICSEARCH_SSL_VERIFY
              value: "true"
            - name: FLUENT_ELASTICSEARCH_USER
              value: "elastic"
            - name: FLUENT_ELASTICSEARCH_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: elasticsearch-cluster-es-elastic-user
                  key: elastic
            - name: FLUENT_ELASTICSEARCH_LOGSTASH_PREFIX
              value: "kubernetes-logs"
          resources:
            requests:
              memory: 512Mi
              cpu: 200m
            limits:
              memory: 1Gi
              cpu: 500m
          volumeMounts:
            - name: varlog
              mountPath: /var/log
              readOnly: true
            - name: docker-containers
              mountPath: /var/lib/docker/containers
              readOnly: true
            - name: fluentd-config
              mountPath: /fluentd/etc
              readOnly: true
      volumes:
        - name: varlog
          hostPath:
            path: /var/log
        - name: docker-containers
          hostPath:
            path: /var/lib/docker/containers
        - name: fluentd-config
          configMap:
            name: fluentd-config
---
# --- Fluentd configuration (ConfigMap) ---
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluentd-config
  namespace: logging
data:
  fluent.conf: |
    <source>
      @type tail
      @id tail-containers
      path /var/log/containers/*.log
      pos_file /var/log/fluentd-containers.pos
      tag kubernetes.*
      read_from_head true
      <parse>
        @type json
        time_key time
        time_format %Y-%m-%dT%H:%M:%S.%NZ
      </parse>
    </source>

    <filter kubernetes.**>
      @type kubernetes_metadata
      @id filter_kube_metadata
    </filter>

    <match kubernetes.**>
      @type elasticsearch
      @id elasticsearch_output
      host "#{ENV['FLUENT_ELASTICSEARCH_HOST']}"
      port "#{ENV['FLUENT_ELASTICSEARCH_PORT']}"
      scheme "#{ENV['FLUENT_ELASTICSEARCH_SCHEME']}"
      ssl_verify "#{ENV['FLUENT_ELASTICSEARCH_SSL_VERIFY']}"
      user "#{ENV['FLUENT_ELASTICSEARCH_USER']}"
      password "#{ENV['FLUENT_ELASTICSEARCH_PASSWORD']}"
      index_name "#{ENV['FLUENT_ELASTICSEARCH_LOGSTASH_PREFIX']}"
      type_name fluentd
      logstash_format true
      logstash_prefix "#{ENV['FLUENT_ELASTICSEARCH_LOGSTASH_PREFIX']}"
      logstash_dateformat %Y.%m.%d
      include_tag_key true
      <buffer>
        @type file
        path /var/log/fluentd-buffer
        flush_mode interval
        retry_type exponential_backoff
        flush_interval 5s
        retry_forever false
        retry_max_interval 30
        chunk_limit_size 8MB
        queue_limit_length 8
        overflow_action block
      </buffer>
    </match>
EOF
```