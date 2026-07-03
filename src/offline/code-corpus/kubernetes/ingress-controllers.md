---
language: yaml
tags: [kubernetes, ingress, nginx, tls, cert-manager]
title: K8s Ingress Controllers
description: NGINX Ingress controller setup, annotations for rewrite/SSL/CORS, cert-manager for automatic TLS, IngressClass, multiple controllers, canary deployments, gRPC ingress.
source: pattern
---

```yaml
# =============================================================================
# NGINX INGRESS CONTROLLER
# =============================================================================

# --- NGINX Ingress Controller (via helm: ingress-nginx/ingress-nginx) ---
# values.yaml for helm install
controller:
  replicaCount: 3
  service:
    type: LoadBalancer
    annotations:
      service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
      service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
      service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
    externalTrafficPolicy: Local
  config:
    # Global config settings
    use-forwarded-headers: "true"
    proxy-body-size: "50m"
    proxy-buffer-size: "128k"
    ssl-protocols: "TLSv1.2 TLSv1.3"
    ssl-ciphers: "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"
    keep-alive: "60"
    upstream-keepalive-connections: "64"
    upstream-keepalive-timeout: "60"
    hsts: "true"
    hsts-preload: "true"
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 2
      memory: 2Gi
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 80
    targetMemoryUtilizationPercentage: 80
  podAnnotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "10254"
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: ScheduleAnyway
defaultBackend:
  enabled: true

# --- IngressClass (separates multiple controllers) ---
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx-external
  annotations:
    ingressclass.kubernetes.io/is-default-class: "true"
spec:
  controller: k8s.io/ingress-nginx
  parameters:
    apiGroup: k8s.example.com
    kind: IngressParameters
    name: external-lb-config
---
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx-internal
spec:
  controller: k8s.io/ingress-nginx
  parameters:
    apiGroup: k8s.example.com
    kind: IngressParameters
    name: internal-lb-config

# =============================================================================
# BASIC INGRESS WITH TLS & ANNOTATIONS
# =============================================================================

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: main-app-ingress
  namespace: production
  annotations:
    # SSL/HTTPS config
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    nginx.ingress.kubernetes.io/ssl-passthrough: "false"
    
    # Rewrite rules
    nginx.ingress.kubernetes.io/rewrite-target: "/$2"
    nginx.ingress.kubernetes.io/use-regex: "true"
    
    # CORS headers
    nginx.ingress.kubernetes.io/enable-cors: "true"
    nginx.ingress.kubernetes.io/cors-allow-origin: "https://app.example.com,https://admin.example.com"
    nginx.ingress.kubernetes.io/cors-allow-methods: "GET, PUT, POST, DELETE, PATCH, OPTIONS"
    nginx.ingress.kubernetes.io/cors-allow-headers: "DNT,X-CustomHeader,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Authorization"
    nginx.ingress.kubernetes.io/cors-allow-credentials: "true"
    nginx.ingress.kubernetes.io/cors-max-age: "86400"
    
    # Rate limiting
    nginx.ingress.kubernetes.io/limit-rps: "100"
    nginx.ingress.kubernetes.io/limit-burst-size: "200"
    nginx.ingress.kubernetes.io/limit-connections: "50"
    
    # Auth
    nginx.ingress.kubernetes.io/whitelist-source-range: "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    
    # Proxy config
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "10"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-buffering: "on"
    nginx.ingress.kubernetes.io/proxy-buffers-number: "4"
    nginx.ingress.kubernetes.io/proxy-buffer-size: "128k"
    
    # ConfigMap reference (controller-level)
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "X-XSS-Protection: 1; mode=block";
      more_set_headers "Referrer-Policy: strict-origin-when-cross-origin";
    
    # Upstream keepalive
    nginx.ingress.kubernetes.io/upstream-keepalive-connections: "32"
    nginx.ingress.kubernetes.io/upstream-keepalive-timeout: "60"
    
spec:
  ingressClassName: nginx-external
  tls:
    - hosts:
        - app.example.com
        - api.example.com
      secretName: main-app-tls
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /api(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: api-service
                port:
                  number: 8080
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-service
                port:
                  number: 80
    - host: admin.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: admin-service
                port:
                  number: 8080

# =============================================================================
# CERT-MANAGER — AUTOMATIC TLS
# =============================================================================

# --- ClusterIssuer (Let's Encrypt Production) ---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
      - selector:
          dnsZones:
            - "example.com"
        dns01:
          route53:
            region: us-east-1
            hostedZoneID: Z1234567890ABCDEF
      - selector:
          dnsZones:
            - "internal.example.com"
        dns01:
          cloudflare:
            email: ops@example.com
            apiTokenSecretRef:
              name: cloudflare-api-token
              key: api-token
---
# --- ClusterIssuer (Let's Encrypt Staging for testing) ---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: ops@example.com
    privateKeySecretRef:
      name: letsencrypt-staging-account-key
    solvers:
      - http01:
          ingress:
            class: nginx-external
---
# --- Self-signed ClusterIssuer (for internal services) ---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
---
# --- Certificate resource (manual) ---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: wildcard-example-com
  namespace: cert-manager
spec:
  secretName: wildcard-example-com-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  commonName: "*.example.com"
  dnsNames:
    - "*.example.com"
    - "example.com"
  secretTemplate:
    annotations:
      reflector.v1.k8s.emberstack.com/reflection-allowed: "true"
      reflector.v1.k8s.emberstack.com/reflection-auto-enabled: "true"
      reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces: "production,staging,development"
  privateKey:
    algorithm: ECDSA
    size: 256
    encoding: PKCS8
  usages:
    - server auth
    - client auth
  duration: 2160h  # 90 days
  renewBefore: 720h  # 30 days before expiry
---
# Ingress referencing cert-manager annotations (auto-provision)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: auto-tls-ingress
  namespace: production
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    cert-manager.io/acme-challenge-type: "http01"
    acme.cert-manager.io/http01-edit-in-place: "true"
    cert-manager.io/common-name: "app.example.com"
    cert-manager.io/private-key-algorithm: "ECDSA"
    cert-manager.io/private-key-size: "256"
    cert-manager.io/renew-before: "720h"
    cert-manager.io/duration: "2160h"
spec:
  ingressClassName: nginx-external
  tls:
    - hosts:
        - app.example.com
      secretName: app-example-com-tls  # auto-created by cert-manager
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-service
                port:
                  number: 80

# =============================================================================
# MULTIPLE INGRESS CONTROLLERS
# =============================================================================

# --- IngressClass for internal controller ---
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx-internal
spec:
  controller: k8s.io/ingress-nginx
  parameters:
    apiGroup: k8s.example.com
    kind: IngressParameters
    name: internal-lb-config
---
# Internal Ingress (referenced by ingressClassName)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: internal-api-ingress
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/whitelist-source-range: "10.0.0.0/8"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx-internal
  tls:
    - hosts:
        - internal-api.internal.example.com
      secretName: internal-api-tls
  rules:
    - host: internal-api.internal.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: internal-api-service
                port:
                  number: 8080
---
# Per-IngressClass parameters
apiVersion: k8s.example.com/v1
kind: IngressParameters
metadata:
  name: internal-lb-config
  namespace: production
spec:
  loadBalancerIP: "10.0.0.100"
  loadBalancerSourceRanges:
    - "10.0.0.0/8"

# =============================================================================
# CANARY DEPLOYMENTS WITH INGRESS
# =============================================================================

# --- Canary Ingress (sends subset of traffic to new version) ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web-app-canary
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-by-header: "X-Canary"          # Route based on header
    nginx.ingress.kubernetes.io/canary-by-header-value: "canary"      # Specific header value
    nginx.ingress.kubernetes.io/canary-by-header-pattern: ".*canary.*"
    nginx.ingress.kubernetes.io/canary-by-cookie: "canary_cookie"     # Route based on cookie
    nginx.ingress.kubernetes.io/canary-weight: "10"                   # 10% of traffic
    nginx.ingress.kubernetes.io/canary-weight-total: "100"            # Total weight denominator
spec:
  ingressClassName: nginx-external
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-app-canary-service    # Points to new version
                port:
                  number: 80
---
# Canary based on header value (for internal testing)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-canary-header
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-by-header: "X-Env"
    nginx.ingress.kubernetes.io/canary-by-header-value: "staging"
spec:
  ingressClassName: nginx-external
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-canary-service
                port:
                  number: 8080

# =============================================================================
# gRPC INGRESS
# =============================================================================

# --- gRPC Ingress (requires HTTP/2) ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: grpc-ingress
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/backend-protocol: "GRPC"
    nginx.ingress.kubernetes.io/ssl-passthrough: "false"
    nginx.ingress.kubernetes.io/server-snippet: |
      location / {
        grpc_pass grpc://grpc-backend;
      }
    nginx.ingress.kubernetes.io/upstream-keepalive-connections: "128"
    nginx.ingress.kubernetes.io/upstream-keepalive-timeout: "600"
    nginx.ingress.kubernetes.io/upstream-keepalive-requests: "10000"
spec:
  ingressClassName: nginx-external
  tls:
    - hosts:
        - grpc.example.com
      secretName: grpc-tls
  rules:
    - host: grpc.example.com
      http:
        paths:
          - path: /myapp.MyService
            pathType: Prefix
            backend:
              service:
                name: grpc-service
                port:
                  number: 50051
          - path: /myapp.HealthService
            pathType: Prefix
            backend:
              service:
                name: grpc-health-service
                port:
                  number: 50052
---
# gRPC Service (must use h2c or HTTP/2)
apiVersion: v1
kind: Service
metadata:
  name: grpc-service
  namespace: production
  annotations:
    service.alpha.kubernetes.io/backend-protocol: "GRPC"
spec:
  type: ClusterIP
  ports:
    - port: 50051
      targetPort: 50051
      name: grpc
      protocol: TCP
      appProtocol: h2c  # HTTP/2 Cleartext (required for gRPC)
  selector:
    app: grpc-server

# =============================================================================
# ADVANCED INGRESS FEATURES
# =============================================================================

# --- Ingress with sticky sessions (session affinity) ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: session-affinity-ingress
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/affinity: "cookie"
    nginx.ingress.kubernetes.io/affinity-mode: "balanced"
    nginx.ingress.kubernetes.io/session-cookie-name: "INGRESS_SESSION"
    nginx.ingress.kubernetes.io/session-cookie-expires: "86400"
    nginx.ingress.kubernetes.io/session-cookie-max-age: "86400"
    nginx.ingress.kubernetes.io/upstream-hash-by: "$request_uri"
spec:
  ingressClassName: nginx-external
  rules:
    - host: session.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: session-service
                port:
                  number: 80
---
# --- Ingress with custom error pages ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: custom-error-ingress
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/custom-http-errors: "404,503"
    nginx.ingress.kubernetes.io/default-backend: "custom-error-service"
    nginx.ingress.kubernetes.io/custom-error-service: |
      [
        {"code": 404, "service": "error-page-404", "port": 80},
        {"code": 503, "service": "error-page-503", "port": 80}
      ]
spec:
  ingressClassName: nginx-external
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-service
                port:
                  number: 80
---
# --- Ingress with OAuth2 proxy ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: oauth2-ingress
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/auth-url: "https://oauth2-proxy.oauth2.svc.cluster.local/oauth2/auth"
    nginx.ingress.kubernetes.io/auth-signin: "https://oauth2-proxy.example.com/oauth2/start?rd=$scheme://$host$request_uri"
    nginx.ingress.kubernetes.io/auth-response-headers: "X-Auth-Request-User, X-Auth-Request-Email"
spec:
  ingressClassName: nginx-external
  tls:
    - hosts:
        - dashboard.example.com
      secretName: dashboard-tls
  rules:
    - host: dashboard.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: dashboard-service
                port:
                  number: 8080

# =============================================================================
# MULTI-CLUSTER INGRESS (via Global Load Balancer)
# =============================================================================

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: multi-cluster-ingress
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/global-rate-limit: "1000"
    nginx.ingress.kubernetes.io/global-rate-limit-window: "1m"
    nginx.ingress.kubernetes.io/global-rate-limit-key: "${http_x_forwarded_for}"
    nginx.ingress.kubernetes.io/limit-whitelist: "10.0.0.0/8"
    nginx.ingress.kubernetes.io/enable-access-log: "true"
    nginx.ingress.kubernetes.io/log-format-escape-json: "true"
    nginx.ingress.kubernetes.io/log-format-upstream: '{"time": "$time_iso8601", "remote_addr": "$remote_addr", "host": "$host", "method": "$request_method", "uri": "$uri", "status": $status, "latency": "$upstream_response_time", "user_agent": "$http_user_agent", "x_forwarded_for": "$http_x_forwarded_for"}'
spec:
  ingressClassName: nginx-external
  tls:
    - hosts:
        - global.example.com
      secretName: global-tls
  rules:
    - host: global.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: global-service
                port:
                  number: 80
EOF
```