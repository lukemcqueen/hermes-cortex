---
language: python
tags: [aws, s3, storage, boto3, python]
title: AWS S3 Operations with boto3
description: Complete guide to S3 operations using boto3 including upload/download, listing objects, presigned URLs, bucket policies, and multipart uploads
source: pattern
---

# AWS S3 Operations with boto3

## Setup and Client Initialization

```python
import boto3
from botocore.exceptions import ClientError
import os

# Initialize S3 client and resource
s3_client = boto3.client('s3', region_name='us-east-1')
s3_resource = boto3.resource('s3', region_name='us-east-1')

# Optional: configure from environment
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
    region_name=os.environ.get('AWS_REGION', 'us-east-1')
)
```

## Upload and Download Files

```python
def upload_file(file_path: str, bucket: str, object_key: str = None) -> bool:
    """Upload a file to S3 with automatic content type detection."""
    if object_key is None:
        object_key = os.path.basename(file_path)
    try:
        with open(file_path, 'rb') as f:
            s3_client.upload_fileobj(
                f, bucket, object_key,
                ExtraArgs={'ACL': 'private'}
            )
        print(f"Uploaded {file_path} -> s3://{bucket}/{object_key}")
        return True
    except ClientError as e:
        print(f"Upload failed: {e}")
        return False


def download_file(bucket: str, object_key: str, download_path: str) -> bool:
    """Download a file from S3."""
    try:
        s3_client.download_file(bucket, object_key, download_path)
        print(f"Downloaded s3://{bucket}/{object_key} -> {download_path}")
        return True
    except ClientError as e:
        print(f"Download failed: {e}")
        return False


def upload_directory(local_dir: str, bucket: str, prefix: str = "") -> list:
    """Upload an entire directory tree to S3."""
    uploaded = []
    for root, dirs, files in os.walk(local_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_dir)
            object_key = os.path.join(prefix, relative_path) if prefix else relative_path
            if upload_file(local_path, bucket, object_key):
                uploaded.append(object_key)
    return uploaded


# Usage
upload_file('report.pdf', 'my-bucket', 'data/report.pdf')
download_file('my-bucket', 'data/report.pdf', './downloaded_report.pdf')
upload_directory('./logs/', 'my-bucket', 'logs/')
```

## List Objects

```python
def list_objects(bucket: str, prefix: str = "", max_keys: int = 1000) -> list:
    """List objects in a bucket with optional prefix filtering."""
    objects = []
    paginator = s3_client.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, MaxKeys=max_keys):
        if 'Contents' in page:
            for obj in page['Contents']:
                objects.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag'],
                    'storage_class': obj.get('StorageClass', 'STANDARD')
                })
    return objects


def filter_by_extension(bucket: str, extension: str, prefix: str = "") -> list:
    """List objects filtered by file extension."""
    all_objects = list_objects(bucket, prefix)
    return [obj for obj in all_objects if obj['key'].endswith(extension)]


# Usage
objects = list_objects('my-bucket', prefix='data/')
print(f"Found {len(objects)} objects")
for obj in objects:
    print(f"{obj['key']} ({obj['size']} bytes, {obj['storage_class']})")

# Paginate through all objects
paginator = s3_client.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket='my-bucket', Prefix='images/', MaxKeys=100):
    if 'Contents' in page:
        for obj in page['Contents']:
            print(f"  {obj['Key']}")
```

## Presigned URLs

```python
from datetime import datetime, timedelta

def generate_presigned_url(bucket: str, object_key: str, expiration: int = 3600) -> str:
    """Generate a presigned URL for temporary access to a private object."""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': object_key},
            ExpiresIn=expiration
        )
        return url
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        return None


def generate_presigned_upload_url(bucket: str, object_key: str, expiration: int = 3600) -> str:
    """Generate a presigned URL for uploading an object."""
    try:
        url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': bucket, 'Key': object_key},
            ExpiresIn=expiration
        )
        return url
    except ClientError as e:
        print(f"Error generating presigned upload URL: {e}")
        return None


def generate_presigned_post(bucket: str, object_key: str, expiration: int = 3600) -> dict:
    """Generate presigned POST fields for browser-based uploads."""
    try:
        response = s3_client.generate_presigned_post(
            Bucket=bucket,
            Key=object_key,
            Conditions=[
                {"acl": "private"},
                ["content-length-range", 1, 10_485_760]  # 10 MB max
            ],
            ExpiresIn=expiration
        )
        return response  # {'url': ..., 'fields': {...}}
    except ClientError as e:
        print(f"Error generating presigned POST: {e}")
        return None


# Usage
download_url = generate_presigned_url('my-bucket', 'private/report.pdf', expiration=3600)
print(f"Temporary download URL (valid 1h): {download_url}")

upload_url = generate_presigned_upload_url('my-bucket', 'uploads/photo.jpg', expiration=900)
print(f"Temporary upload URL (valid 15min): {upload_url}")

post_data = generate_presigned_post('my-bucket', 'uploads/${filename}', expiration=1800)
print(f"POST URL: {post_data['url']}")
print(f"POST fields: {post_data['fields']}")
```

## Bucket Policies

```python
import json

def set_bucket_policy(bucket: str, policy: dict) -> bool:
    """Set a bucket policy (replaces existing policy)."""
    try:
        s3_client.put_bucket_policy(
            Bucket=bucket,
            Policy=json.dumps(policy)
        )
        print(f"Policy applied to bucket '{bucket}'")
        return True
    except ClientError as e:
        print(f"Failed to set policy: {e}")
        return False


def get_bucket_policy(bucket: str) -> dict:
    """Retrieve the current bucket policy."""
    try:
        response = s3_client.get_bucket_policy(Bucket=bucket)
        return json.loads(response['Policy'])
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucketPolicy':
            print(f"No policy on bucket '{bucket}'")
        else:
            print(f"Failed to get policy: {e}")
        return None


def delete_bucket_policy(bucket: str) -> bool:
    """Delete the bucket policy."""
    try:
        s3_client.delete_bucket_policy(Bucket=bucket)
        print(f"Policy deleted from bucket '{bucket}'")
        return True
    except ClientError as e:
        print(f"Failed to delete policy: {e}")
        return False


# Example: Allow cross-account access to a specific prefix
cross_account_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CrossAccountRead",
            "Effect": "Allow",
            "Principal": {"AWS": "arn:aws:iam::123456789012:root"},
            "Action": ["s3:GetObject", "s3:ListBucket"],
            "Resource": [
                "arn:aws:s3:::my-bucket",
                "arn:aws:s3:::my-bucket/shared/*"
            ]
        }
    ]
}
set_bucket_policy('my-bucket', cross_account_policy)

# Example: Enforce TLS for all requests
tls_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DenyInsecureConnections",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": [
                "arn:aws:s3:::my-bucket",
                "arn:aws:s3:::my-bucket/*"
            ],
            "Condition": {
                "Bool": {"aws:SecureTransport": "false"}
            }
        }
    ]
}
set_bucket_policy('my-bucket', tls_policy)
```

## Multipart Upload

```python
import threading

def multipart_upload(bucket: str, object_key: str, file_path: str,
                     part_size: int = 8 * 1024 * 1024) -> bool:
    """
    Upload a large file using S3 multipart upload.
    part_size: minimum 5 MB (5 * 1024 * 1024), default 8 MB.
    """
    file_size = os.path.getsize(file_path)
    parts_count = (file_size + part_size - 1) // part_size
    
    if parts_count < 2:
        # File is small enough for a single upload
        return upload_file(file_path, bucket, object_key)

    try:
        # Initiate multipart upload
        mpu = s3_client.create_multipart_upload(
            Bucket=bucket, Key=object_key,
            ContentType='application/octet-stream'
        )
        upload_id = mpu['UploadId']
        print(f"Started multipart upload {upload_id} ({parts_count} parts)")

        # Upload parts
        parts = []
        with open(file_path, 'rb') as f:
            for part_number in range(1, parts_count + 1):
                data = f.read(part_size)
                response = s3_client.upload_part(
                    Bucket=bucket, Key=object_key,
                    PartNumber=part_number, UploadId=upload_id,
                    Body=data
                )
                parts.append({
                    'PartNumber': part_number,
                    'ETag': response['ETag']
                })
                print(f"  Part {part_number}/{parts_count} uploaded")

        # Complete multipart upload
        s3_client.complete_multipart_upload(
            Bucket=bucket, Key=object_key,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )
        print(f"Multipart upload completed: s3://{bucket}/{object_key}")
        return True

    except Exception as e:
        print(f"Multipart upload failed: {e}")
        # Abort the upload to avoid storage charges
        try:
            s3_client.abort_multipart_upload(
                Bucket=bucket, Key=object_key, UploadId=upload_id
            )
            print(f"Aborted multipart upload {upload_id}")
        except Exception:
            pass
        return False


def multipart_upload_concurrent(bucket: str, object_key: str, file_path: str,
                                part_size: int = 8 * 1024 * 1024,
                                max_concurrency: int = 4) -> bool:
    """
    Upload a large file using concurrent multipart upload.
    Uses threads to upload parts in parallel for faster throughput.
    """
    file_size = os.path.getsize(file_path)
    parts_count = (file_size + part_size - 1) // part_size
    
    if parts_count < 2:
        return upload_file(file_path, bucket, object_key)

    results = {'parts': [], 'error': None}
    lock = threading.Lock()

    def upload_part(part_number: int, data: bytes):
        try:
            response = s3_client.upload_part(
                Bucket=bucket, Key=object_key,
                PartNumber=part_number, UploadId=upload_id,
                Body=data
            )
            with lock:
                results['parts'].append({
                    'PartNumber': part_number,
                    'ETag': response['ETag']
                })
            print(f"  Part {part_number} uploaded")
        except Exception as e:
            with lock:
                results['error'] = e

    try:
        mpu = s3_client.create_multipart_upload(
            Bucket=bucket, Key=object_key
        )
        upload_id = mpu['UploadId']
        print(f"Started concurrent multipart upload ({parts_count} parts, {max_concurrency} threads)")

        # Read all parts into memory (for large files, stream instead)
        parts_data = []
        with open(file_path, 'rb') as f:
            for _ in range(parts_count):
                parts_data.append(f.read(part_size))

        # Upload parts in parallel using ThreadPool
        threads = []
        for i, data in enumerate(parts_data, 1):
            t = threading.Thread(target=upload_part, args=(i, data))
            threads.append(t)
            t.start()
            
            # Limit concurrency
            if len(threads) >= max_concurrency:
                threads[0].join()
                threads.pop(0)

        # Wait for remaining threads
        for t in threads:
            t.join()

        if results['error']:
            raise results['error']

        # Sort parts by part number and complete
        results['parts'].sort(key=lambda p: p['PartNumber'])
        s3_client.complete_multipart_upload(
            Bucket=bucket, Key=object_key,
            UploadId=upload_id,
            MultipartUpload={'Parts': results['parts']}
        )
        print(f"Concurrent multipart upload completed: s3://{bucket}/{object_key}")
        return True

    except Exception as e:
        print(f"Concurrent multipart upload failed: {e}")
        try:
            s3_client.abort_multipart_upload(
                Bucket=bucket, Key=object_key, UploadId=upload_id
            )
        except Exception:
            pass
        return False


# Usage
multipart_upload('my-bucket', 'large-backup.tar.gz', '/tmp/large-backup.tar.gz')
multipart_upload_concurrent('my-bucket', 'large-backup.tar.gz', '/tmp/large-backup.tar.gz',
                            max_concurrency=8)
```

## Lifecycle Rules and Versioning

```python
def set_lifecycle_policy(bucket: str) -> bool:
    """Configure lifecycle rules to transition and expire objects."""
    lifecycle_rules = [
        {
            'ID': 'TransitionToIA',
            'Status': 'Enabled',
            'Prefix': 'logs/',
            'Transitions': [
                {'Days': 30, 'StorageClass': 'STANDARD_IA'},
                {'Days': 90, 'StorageClass': 'GLACIER'}
            ],
            'Expiration': {'Days': 365}
        },
        {
            'ID': 'ExpireOldVersions',
            'Status': 'Enabled',
            'Filter': {'Prefix': ''},
            'NoncurrentVersionExpiration': {'NoncurrentDays': 90}
        }
    ]
    try:
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket,
            LifecycleConfiguration={'Rules': lifecycle_rules}
        )
        print(f"Lifecycle rules applied to '{bucket}'")
        return True
    except ClientError as e:
        print(f"Failed to set lifecycle rules: {e}")
        return False


def enable_versioning(bucket: str) -> bool:
    """Enable versioning on a bucket."""
    try:
        s3_client.put_bucket_versioning(
            Bucket=bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        print(f"Versioning enabled on '{bucket}'")
        return True
    except ClientError as e:
        print(f"Failed to enable versioning: {e}")
        return False


def list_object_versions(bucket: str, prefix: str = "") -> list:
    """List all versions of objects in a bucket."""
    versions = []
    paginator = s3_client.get_paginator('list_object_versions')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for v in page.get('Versions', []):
            versions.append({
                'key': v['Key'],
                'version_id': v['VersionId'],
                'is_latest': v['IsLatest'],
                'last_modified': v['LastModified'],
                'size': v['Size']
            })
        for dm in page.get('DeleteMarkers', []):
            versions.append({
                'key': dm['Key'],
                'version_id': dm['VersionId'],
                'is_latest': dm['IsLatest'],
                'is_delete_marker': True
            })
    return versions


# Usage
enable_versioning('my-bucket')
set_lifecycle_policy('my-bucket')
```

## Error Handling Best Practices

```python
import time

def s3_operation_with_retry(operation, max_retries: int = 3):
    """Execute an S3 operation with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return operation()
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ('NoSuchBucket', 'NoSuchKey', 'AccessDenied'):
                raise  # Don't retry client errors
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"Retrying in {wait}s (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(wait)
            else:
                raise


def verify_bucket_access(bucket: str) -> dict:
    """Verify that we can access a bucket and report permissions."""
    checks = {}
    
    # Check if bucket exists and we can list it
    try:
        s3_client.head_bucket(Bucket=bucket)
        checks['bucket_exists'] = True
    except ClientError as e:
        checks['bucket_exists'] = False
        checks['error'] = str(e)
        return checks

    # Check list permission
    try:
        s3_client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        checks['can_list'] = True
    except ClientError:
        checks['can_list'] = False

    # Check write permission (try to upload a small test object)
    try:
        s3_client.put_object(Bucket=bucket, Key='.s3-access-test', Body=b'test')
        s3_client.delete_object(Bucket=bucket, Key='.s3-access-test')
        checks['can_write'] = True
    except ClientError:
        checks['can_write'] = False

    return checks


# Usage
access = verify_bucket_access('my-bucket')
print(f"Bucket access: exists={access.get('bucket_exists')}, "
      f"list={access.get('can_list')}, write={access.get('can_write')}")
```