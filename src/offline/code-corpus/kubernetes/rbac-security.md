---
language: yaml
tags: [kubernetes, rbac, security, network-policy, auth]
title: K8s RBAC and Security
description: Role/ClusterRole, RoleBinding/ClusterRoleBinding, ServiceAccount, Pod Security Standards, Pod Security Admission, NetworkPolicy allow/deny rules, namespace isolation, pod-level.
source: pattern
---

```yaml
# =============================================================================
# KUBERNETES RBAC — ROLE-BASED ACCESS CONTROL
# =============================================================================

# --- Namespace-scoped Role ---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: app-team
  name: app-developer
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "pods/portforward", "services", "configmaps", "secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch", "create"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch", "create", "update"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]  # Allows kubectl exec
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list", "watch"]
---
# --- Cluster-scoped ClusterRole ---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cluster-admin-viewer
rules:
  - apiGroups: [""]
    resources: ["nodes", "namespaces", "persistentvolumes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses", "csidrivers"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods", "nodes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["componentstatuses"]
    verbs: ["get", "list"]
---
# --- ClusterRole for read-only access to all namespaced resources ---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: readonly-global
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps", "secrets", "endpoints",
                 "persistentvolumeclaims", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch"]
  # Non-resource URLs for API discovery
  - nonResourceURLs: ["/api", "/apis", "/metrics", "/healthz", "/version"]
    verbs: ["get"]
---
# --- RoleBinding (binds Role to a ServiceAccount in the same namespace) ---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  namespace: app-team
  name: app-developer-binding
subjects:
  - kind: ServiceAccount
    name: app-sa
    namespace: app-team
  - kind: User
    name: alice@example.com
    apiGroup: rbac.authorization.k8s.io
  - kind: Group
    name: app-developers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: app-developer
  apiGroup: rbac.authorization.k8s.io
---
# --- ClusterRoleBinding (binds ClusterRole to all authenticated users) ---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: readonly-global-binding
subjects:
  - kind: Group
    name: system:authenticated
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: readonly-global
  apiGroup: rbac.authorization.k8s.io
---
# --- Aggregate ClusterRole (labels-based aggregation) ---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: app-operator
  labels:
    rbac.authorization.k8s.io/aggregate-to-admin: "true"
    rbac.authorization.k8s.io/aggregate-to-edit: "true"
rules:
  - apiGroups: ["example.crd.io"]
    resources: ["applications", "applications/status"]
    verbs: ["*"]
---
# --- ServiceAccount with image pull secrets ---
apiVersion: v1
kind: ServiceAccount
metadata:
  namespace: app-team
  name: app-sa
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/app-irsa-role
secrets:
  - name: docker-registry-creds
imagePullSecrets:
  - name: docker-registry-creds
---
# --- ServiceAccount for CI/CD pipeline (cluster-wide) ---
apiVersion: v1
kind: ServiceAccount
metadata:
  namespace: ci-cd
  name: pipeline-sa
automountServiceAccountToken: true
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: pipeline-cluster-admin
subjects:
  - kind: ServiceAccount
    name: pipeline-sa
    namespace: ci-cd
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io

# =============================================================================
# POD SECURITY STANDARDS (PSS) & POD SECURITY ADMISSION (PSA)
# =============================================================================

# --- Pod Security Standards: Enforce at Namespace level ---
apiVersion: v1
kind: Namespace
metadata:
  name: production-apps
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: latest
    pod-security.kubernetes.io/warn: baseline
    pod-security.kubernetes.io/warn-version: latest
---
# Namespace with privileged (for system components)
apiVersion: v1
kind: Namespace
metadata:
  name: system-tools
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
---
# Namespace with baseline (moderate security)
apiVersion: v1
kind: Namespace
metadata:
  name: legacy-apps
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/warn: restricted
---
# Pod Security Admission configuration via ValidatingAdmissionPolicy (K8s 1.28+)
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: enforce-restricted-pss
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: "object.spec.securityContext.runAsNonRoot == true"
      message: "Running as root is not allowed (restricted PSS)"
    - expression: "!has(object.spec.containers) || object.spec.containers.all(c, !has(c.securityContext) || !has(c.securityContext.privileged) || c.securityContext.privileged != true)"
      message: "Privileged containers are not allowed (restricted PSS)"
    - expression: "!has(object.spec.containers) || object.spec.containers.all(c, !has(c.securityContext) || !has(c.securityContext.capabilities) || !has(c.securityContext.capabilities.add) || c.securityContext.capabilities.add.all(cap, !(cap in ['NET_ADMIN', 'SYS_ADMIN', 'SYS_PTRACE'])))"
      message: "Forbidden capabilities (restricted PSS)"

# =============================================================================
# RESTRICTED POD (Pod Security Standards — restricted profile)
# =============================================================================

apiVersion: v1
kind: Pod
metadata:
  name: restricted-app
  namespace: production-apps
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1001
    runAsGroup: 1001
    fsGroup: 1001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: myapp:1.0
      securityContext:
        allowPrivilegeEscalation: false
        privileged: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
        runAsNonRoot: true
        runAsUser: 1001
        seccompProfile:
          type: RuntimeDefault
      volumeMounts:
        - name: tmp
          mountPath: /tmp
      ports:
        - containerPort: 8080
  volumes:
    - name: tmp
      emptyDir: {}

# =============================================================================
# NETWORK POLICY
# =============================================================================

# --- Default deny all ingress traffic (namespace isolation) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: production-apps
spec:
  podSelector: {}
  policyTypes:
    - Ingress
---
# --- Default deny all egress traffic ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: production-apps
spec:
  podSelector: {}
  policyTypes:
    - Egress
---
# --- Allow ingress from same namespace (namespace isolation) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-same-namespace
  namespace: production-apps
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: production-apps
---
# --- Allow specific namespace and pod labels (fine-grained) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-monitoring
  namespace: production-apps
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app: prometheus
      ports:
        - protocol: TCP
          port: 8080
        - protocol: TCP
          port: 9090
---
# --- Allow ingress from specific IP range (external) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-external-healthcheck
  namespace: production-apps
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Ingress
  ingress:
    - from:
        - ipBlock:
            cidr: 203.0.113.0/24
            except:
              - 203.0.113.10/32  # Block a specific IP
      ports:
        - protocol: TCP
          port: 80
---
# --- Allow ingress to API from frontend only ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-api
  namespace: production-apps
spec:
  podSelector:
    matchLabels:
      tier: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              tier: frontend
      ports:
        - protocol: TCP
          port: 3000
---
# --- Egress: allow DNS and specific service only ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-egress-dns-and-api
  namespace: production-apps
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - ipBlock:
            cidr: 10.0.0.0/8
            except:
              - 10.96.0.0/12  # Block cluster IP range
      ports:
        - protocol: TCP
          port: 443
---
# --- Allow egress to database in different namespace ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-egress-to-database
  namespace: production-apps
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: databases
          podSelector:
            matchLabels:
              app: postgresql
      ports:
        - protocol: TCP
          port: 5432
---
# --- Pod-level NetworkPolicy (specific pod) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-service-policy
  namespace: production-apps
spec:
  podSelector:
    matchLabels:
      app: payment
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: orders
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: fraud-detection
      ports:
        - protocol: TCP
          port: 50051
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: databases
          podSelector:
            matchLabels:
              app: payment-db
      ports:
        - protocol: TCP
          port: 5432
---
# --- Isolated namespace (no traffic allowed in or out by default) ---
apiVersion: v1
kind: Namespace
metadata:
  name: isolated
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: isolate-namespace
  namespace: isolated
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
---
# --- Per-namespace allow-list (allow ingress only from approved namespaces) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-approved-ns-only
  namespace: production-apps
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchExpressions:
              - key: kubernetes.io/metadata.name
                operator: In
                values:
                  - ingress-nginx
                  - monitoring
                  - cert-manager
      ports:
        - protocol: TCP
          port: 80
        - protocol: TCP
          port: 443
EOF
```