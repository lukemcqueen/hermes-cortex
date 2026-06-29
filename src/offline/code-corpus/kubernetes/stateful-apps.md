---
language: yaml
tags: [kubernetes, statefulset, databases, operators, storage]
title: Stateful Applications on K8s
description: StatefulSet with stable network identity, headless services, persistent volumes with PVC templates, init containers for db bootstrapping, operators basics with CRDs and controller, backup with Velero.
source: pattern
---

```yaml
# =============================================================================
# STATEFULSET WITH STABLE NETWORK IDENTITY
# =============================================================================

# --- Headless Service (stable DNS names: pod-name.service-name.namespace.svc.cluster.local) ---
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
  namespace: databases
  labels:
    app: postgres
spec:
  clusterIP: None  # Headless — DNS returns pod IPs directly
  ports:
    - name: postgres
      port: 5432
      targetPort: 5432
  selector:
    app: postgres
---
# --- StatefulSet with stable network identity ---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: databases
spec:
  serviceName: postgres-headless  # Links to headless service for stable DNS
  replicas: 3
  podManagementPolicy: OrderedReady  # Default: one at a time, in order
  # podManagementPolicy: Parallel  # For faster scaling
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      partition: 0  # For canary updates: update only pods with ordinal >= partition
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      terminationGracePeriodSeconds: 60
      # Init container for DB bootstrapping
      initContainers:
        - name: init-db
          image: postgres:16
          command:
            - /bin/sh
            - -ec
            - |
              # Check if this is the first pod (postgres-0)
              if [ "$(hostname)" = "postgres-0" ]; then
                echo "Primary node — initializing database..."
                if [ ! -f /var/lib/postgresql/data/PG_VERSION ]; then
                  initdb -D /var/lib/postgresql/data \
                    --auth-host=scram-sha-256 \
                    --auth-local=peer
                fi
              else
                echo "Replica node — waiting for primary..."
                until pg_isready -h postgres-0.postgres-headless.databases.svc.cluster.local -q; do
                  sleep 2
                done
              fi
          env:
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-creds
                  key: postgres-password
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
              subPath: pgdata
              readOnly: false
      containers:
        - name: postgres
          image: postgres:16
          ports:
            - containerPort: 5432
              name: postgres
          env:
            - name: POSTGRES_USER
              value: app
            - name: POSTGRES_DB
              value: platform
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-creds
                  key: postgres-password
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          resources:
            requests:
              cpu: 1000m
              memory: 2Gi
            limits:
              cpu: 4000m
              memory: 8Gi
          livenessProbe:
            exec:
              command:
                - pg_isready
                - -h
                - localhost
                - -U
                - app
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 6
          readinessProbe:
            exec:
              command:
                - psql
                - -h
                - localhost
                - -U
                - app
                - -d
                - platform
                - -c
                - "SELECT 1"
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
              subPath: pgdata
            - name: wal
              mountPath: /var/lib/postgresql/data/pg_wal
              subPath: wal
            - name: config
              mountPath: /etc/postgresql
              readOnly: true
          securityContext:
            runAsNonRoot: true
            runAsUser: 999
            runAsGroup: 999
            fsGroup: 999
      volumes:
        - name: config
          configMap:
            name: postgres-config
  # PVC Template — each pod gets its own PVC
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: premium-rwo
        resources:
          requests:
            storage: 100Gi
    - metadata:
        name: wal
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: premium-rwo
        resources:
          requests:
            storage: 20Gi

# =============================================================================
# READWRITEMANY PVC (shared access for clustered apps)
# =============================================================================

apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-data-pvc
  namespace: databases
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: nfs-csi
  resources:
    requests:
      storage: 500Gi

# =============================================================================
# OPERATORS BASICS — CRDs + Controller
# =============================================================================

# --- CustomResourceDefinition (CRD) for a Database resource ---
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: databases.example.com
spec:
  group: example.com
  names:
    kind: Database
    listKind: DatabaseList
    plural: databases
    singular: database
    shortNames:
      - db
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          required:
            - spec
          properties:
            spec:
              type: object
              required:
                - engine
                - version
                - storage
              properties:
                engine:
                  type: string
                  enum: [postgres, mysql, redis]
                  description: "Database engine type"
                version:
                  type: string
                  description: "Database version (e.g., 16, 8.0)"
                storage:
                  type: string
                  pattern: "^[0-9]+(Gi|Ti)$"
                  description: "Storage size (e.g., 100Gi)"
                replicas:
                  type: integer
                  minimum: 1
                  maximum: 10
                  default: 1
                  description: "Number of replicas"
                backup:
                  type: object
                  properties:
                    enabled:
                      type: boolean
                      default: false
                    schedule:
                      type: string
                      description: "Cron schedule for backups"
                    retention:
                      type: integer
                      default: 7
                      description: "Days to retain backups"
                resources:
                  type: object
                  properties:
                    requests:
                      type: object
                      properties:
                        cpu: { type: string }
                        memory: { type: string }
                    limits:
                      type: object
                      properties:
                        cpu: { type: string }
                        memory: { type: string }
                networkPolicy:
                  type: object
                  properties:
                    allowedNamespaces:
                      type: array
                      items:
                        type: string
            status:
              type: object
              properties:
                phase:
                  type: string
                  enum: [Creating, Ready, Updating, Failed, Deleting]
                observedGeneration:
                  type: integer
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type: { type: string }
                      status: { type: string }
                      reason: { type: string }
                      message: { type: string }
                      lastTransitionTime: { type: string, format: date-time }
      subresources:
        status: {}
      additionalPrinterColumns:
        - name: Engine
          type: string
          jsonPath: .spec.engine
        - name: Version
          type: string
          jsonPath: .spec.version
        - name: Replicas
          type: integer
          jsonPath: .spec.replicas
        - name: Status
          type: string
          jsonPath: .status.phase
        - name: Age
          type: date
          jsonPath: .metadata.creationTimestamp

# --- Custom Resource Instance (using the CRD above) ---
apiVersion: example.com/v1
kind: Database
metadata:
  name: production-pg
  namespace: databases
spec:
  engine: postgres
  version: "16"
  storage: "200Gi"
  replicas: 3
  backup:
    enabled: true
    schedule: "0 2 * * *"  # Daily at 2am
    retention: 30
  resources:
    requests:
      cpu: "2000m"
      memory: "4Gi"
    limits:
      cpu: "8000m"
      memory: "16Gi"
  networkPolicy:
    allowedNamespaces:
      - production
      - staging
      - monitoring

# --- Basic Operator Deployment (controller that reconciles Database CR) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: database-operator
  namespace: operators
  labels:
    app: database-operator
spec:
  replicas: 1
  selector:
    matchLabels:
      app: database-operator
  template:
    metadata:
      labels:
        app: database-operator
    spec:
      serviceAccountName: database-operator-sa
      containers:
        - name: operator
          image: myregistry.io/database-operator:v1.0.0
          args:
            - --leader-elect=true
            - --metrics-bind-address=:8080
            - --health-probe-bind-address=:8081
          ports:
            - containerPort: 8080
              name: metrics
            - containerPort: 8081
              name: healthz
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8081
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8081
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          env:
            - name: WATCH_NAMESPACE
              value: databases
            - name: OPERATOR_NAME
              value: database-operator
---
# Operator RBAC (needs access to manage the resources it creates)
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: database-operator-role
rules:
  - apiGroups: ["example.com"]
    resources: ["databases", "databases/status", "databases/finalizers"]
    verbs: ["*"]
  - apiGroups: ["apps"]
    resources: ["statefulsets"]
    verbs: ["*"]
  - apiGroups: [""]
    resources: ["services", "configmaps", "secrets", "persistentvolumeclaims",
                 "events", "pods", "endpoints"]
    verbs: ["*"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["*"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies"]
    verbs: ["*"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["*"]

# =============================================================================
# BACKUP WITH VELERO
# =============================================================================

# --- Velero Installation (via helm: vmware-tanzu/velero) ---
# values.yaml for helm install
initContainers:
  - name: velero-plugin-for-aws
    image: velero/velero-plugin-for-aws:v1.9.0
    volumeMounts:
      - mountPath: /target
        name: plugins
configuration:
  provider: aws
  backupStorageLocation:
    name: default
    bucket: my-cluster-backups
    prefix: velero
    config:
      region: us-east-1
      s3ForcePathStyle: "false"
  volumeSnapshotLocation:
    name: default
    config:
      region: us-east-1
credentials:
  useSecret: true
  existingSecret: velero-credentials
snapshotEnabled: true
deployRestic: true
schedules:
  default-daily:
    schedule: "0 1 * * *"  # Daily at 1am
    template:
      ttl: "720h"  # 30 days retention
      includedNamespaces:
        - databases
        - production
      excludedResources:
        - pods
        - events
      includeClusterResources: true
      snapshotVolumes: true
      storageLocation: default

# --- Schedule Backup (Velero Schedule resource) ---
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: daily-database-backup
  namespace: velero
spec:
  schedule: "0 2 * * *"
  template:
    includedNamespaces:
      - databases
    includedResources:
      - persistentvolumeclaims
      - statefulsets
      - services
    labelSelector:
      matchLabels:
        backup-type: database
    ttl: 720h
    snapshotVolumes: true
    storageLocation: default
    volumeSnapshotLocations:
      - default

# --- On-Demand Backup ---
apiVersion: velero.io/v1
kind: Backup
metadata:
  name: manual-database-backup-20240628
  namespace: velero
spec:
  includedNamespaces:
    - databases
  includedResources:
    - persistentvolumeclaims
    - statefulsets
    - services
    - configmaps
    - secrets
  labelSelector:
    matchLabels:
      app: postgres
  snapshotVolumes: true
  storageLocation: default
  ttl: 8760h  # 1 year retention for manual backups
  hooks:
    resources:
      - name: pre-backup-hook
        includedNamespaces:
          - databases
        labelSelector:
          matchLabels:
            app: postgres
        pre:
          - exec:
              container: postgres
              command:
                - /bin/bash
                - -c
                - |
                  pg_dump -U app -d platform -Fc -f /tmp/pre-backup-dump.sqlc
                  echo "Pre-backup dump complete"
              onError: Fail
              timeout: 60s
        post:
          - exec:
              container: postgres
              command:
                - /bin/sh
                - -c
                - |
                  rm -f /tmp/pre-backup-dump.sqlc
                  echo "Cleanup complete"
              onError: Continue
              timeout: 30s

# --- Restore from Backup ---
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: restore-databases-20240628
  namespace: velero
spec:
  backupName: manual-database-backup-20240628
  includedNamespaces:
    - databases
  restoreVolumes: true
  preserveNodePorts: false
  namespaceMapping:
    databases: databases-restored  # Restore to a different namespace
  labelSelector:
    matchLabels:
      app: postgres
  hooks:
    resources:
      - name: post-restore-hook
        includedNamespaces:
          - databases-restored
        post:
          - exec:
              container: postgres
              command:
                - /bin/bash
                - -c
                - |
                  pg_restore -U app -d platform -Fc /tmp/pre-backup-dump.sqlc
                  echo "Restore complete"
              onError: Fail
              timeout: 300s

# =============================================================================
# STATEFUL APP: REDIS CLUSTER
# =============================================================================

apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cluster
  namespace: databases
spec:
  serviceName: redis-cluster-headless
  replicas: 6
  selector:
    matchLabels:
      app: redis-cluster
  template:
    metadata:
      labels:
        app: redis-cluster
    spec:
      terminationGracePeriodSeconds: 60
      initContainers:
        - name: config-builder
          image: redis:7.2
          command:
            - /bin/sh
            - -ec
            - |
              # Build redis.conf from environment variables
              cat > /etc/redis/redis.conf <<EOF
              port 6379
              cluster-enabled yes
              cluster-config-file /data/nodes.conf
              cluster-node-timeout 5000
              appendonly yes
              protected-mode no
              bind 0.0.0.0
              dir /data
              EOF
          volumeMounts:
            - name: redis-config
              mountPath: /etc/redis
      containers:
        - name: redis
          image: redis:7.2
          command:
            - redis-server
            - /etc/redis/redis.conf
          ports:
            - containerPort: 6379
              name: client
            - containerPort: 16379
              name: gossip
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: 2000m
              memory: 4Gi
          volumeMounts:
            - name: data
              mountPath: /data
              subPath: redis-data
            - name: redis-config
              mountPath: /etc/redis
      volumes:
        - name: redis-config
          emptyDir: {}
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: standard
        resources:
          requests:
            storage: 50Gi
---
# Headless service for Redis cluster
apiVersion: v1
kind: Service
metadata:
  name: redis-cluster-headless
  namespace: databases
  labels:
    app: redis-cluster
spec:
  clusterIP: None
  ports:
    - name: client
      port: 6379
      targetPort: 6379
    - name: gossip
      port: 16379
      targetPort: 16379
  selector:
    app: redis-cluster
---
# Read-only service for Redis cluster (load-balanced)
apiVersion: v1
kind: Service
metadata:
  name: redis-cluster
  namespace: databases
  labels:
    app: redis-cluster
spec:
  type: ClusterIP
  ports:
    - name: redis
      port: 6379
      targetPort: 6379
  selector:
    app: redis-cluster
EOF