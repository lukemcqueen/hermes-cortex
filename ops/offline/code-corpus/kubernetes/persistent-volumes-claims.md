---
language: kubernetes
tags: [persistent-volume, persistent-volume-claim, storage-class, access-modes]
title: Persistent Volumes & Claims
description: PersistentVolume, PersistentVolumeClaim, StorageClass, accessModes.
source: pattern
---

```kubernetes
---
# StorageClass for dynamic provisioning
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
  encrypted: "true"
  fstype: ext4
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer

---
# PersistentVolumeClaim (requests dynamic PV via StorageClass)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
  namespace: production
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: fast-ssd
  resources:
    requests:
      storage: 100Gi
  selector:
    matchLabels:
      tier: database

---
# Static PersistentVolume (pre-provisioned)
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nfs-share
  labels:
    tier: shared
spec:
  capacity:
    storage: 5Ti
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-standard
  mountOptions:
    - hard
    - nfsvers=4.1
  nfs:
    path: /exported/data
    server: 192.168.1.100

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: production
spec:
  serviceName: postgres-headless
  replicas: 3
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          envFrom:
            - secretRef:
                name: db-credentials
          ports:
            - containerPort: 5432
              name: pg
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
              subPath: pgdata
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: fast-ssd
        resources:
          requests:
            storage: 100Gi

```
