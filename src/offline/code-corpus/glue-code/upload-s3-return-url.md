---
title: File Upload → S3 → Return URL
description: FastAPI file upload endpoint that uploads to S3 with boto3, returns a presigned URL, and a React frontend upload component with progress bar.
language: python
tags: [glue-code, upload, s3, file, storage]
---

# File Upload → S3 → Return URL

## Overview

A complete file upload flow: the client uploads a file to a FastAPI backend, which streams it to Amazon S3 and returns a presigned URL. The React frontend shows a progress bar during upload.

---

## Backend: FastAPI + boto3 + S3

### Configuration

```python
# config.py
import os

class Settings:
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "my-app-uploads")
    S3_PRESIGNED_EXPIRY: int = 3600  # seconds (1 hour)
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100 MB
    ALLOWED_CONTENT_TYPES: list[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/plain",
        "application/zip",
    ]

settings = Settings()
```

### S3 Service

```python
# services/s3.py
import boto3
import uuid
from botocore.exceptions import ClientError
from config import settings
from typing import BinaryIO

class S3Service:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket = settings.S3_BUCKET

    def _generate_key(self, filename: str, prefix: str = "uploads") -> str:
        """Generate a unique S3 object key."""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        unique_name = f"{uuid.uuid4().hex}"
        return f"{prefix}/{unique_name}.{ext}" if ext else f"{prefix}/{unique_name}"

    def upload_file(
        self,
        file_obj: BinaryIO,
        filename: str,
        content_type: str,
        prefix: str = "uploads",
    ) -> dict:
        """
        Upload file to S3 and return object info.
        Returns dict with key, url, and presigned_url.
        """
        key = self._generate_key(filename, prefix)

        try:
            # Upload the file
            self.client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=self.bucket,
                Key=key,
                ExtraArgs={
                    "ContentType": content_type,
                    # Optional: set cache control
                    "CacheControl": "public, max-age=31536000",
                },
            )

            # Generate presigned URL for secure access
            presigned_url = self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                },
                ExpiresIn=settings.S3_PRESIGNED_EXPIRY,
            )

            return {
                "key": key,
                "bucket": self.bucket,
                "content_type": content_type,
                "size": file_obj.tell() if hasattr(file_obj, 'tell') else None,
                "presigned_url": presigned_url,
                "object_url": f"https://{self.bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{key}",
            }

        except ClientError as exc:
            print(f"[S3 ERROR] Upload failed: {exc}")
            raise RuntimeError(f"S3 upload failed: {exc}")

    def delete_file(self, key: str) -> bool:
        """Delete an object from S3."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            print(f"[S3 ERROR] Delete failed: {exc}")
            return False

    def generate_upload_url(self, filename: str, content_type: str) -> dict:
        """
        Generate a presigned POST URL for direct browser-to-S3 upload.
        (Alternative: client uploads directly to S3 without going through backend.)
        """
        key = self._generate_key(filename)

        try:
            conditions = [
                {"bucket": self.bucket},
                {"key": key},
                {"Content-Type": content_type},
                ["content-length-range", 1, settings.MAX_FILE_SIZE],
            ]

            url = self.client.generate_presigned_post(
                Bucket=self.bucket,
                Key=key,
                Conditions=conditions,
                ExpiresIn=3600,
            )

            return {
                "url": url["url"],
                "fields": url["fields"],
                "key": key,
            }
        except ClientError as exc:
            raise RuntimeError(f"Failed to generate presigned URL: {exc}")


# Singleton
s3_service = S3Service()
```

### FastAPI Upload Endpoint

```python
# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from services.s3 import s3_service, settings
import magic  # python-magic-bin / libmagic for MIME detection

app = FastAPI(title="File Upload API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class UploadResponse(BaseModel):
    key: str
    presigned_url: str
    content_type: str
    size: int

class UploadUrlResponse(BaseModel):
    upload_url: str
    upload_fields: dict
    key: str

@app.post("/api/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file. Returns the S3 key and a presigned URL.
    The file is streamed through the backend to S3.
    """

    # --- Validation ---

    # Check file size (read first chunk to detect, then seek back)
    file.file.seek(0, 2)  # seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # seek back to start

    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max: {settings.MAX_FILE_SIZE // (1024*1024)}MB",
        )

    # Detect content type from file content (more reliable than client header)
    file_bytes = await file.read(2048)
    detected_type = magic.from_buffer(file_bytes, mime=True)
    await file.seek(0)  # reset for upload

    # Use detected type, fall back to client-provided content_type
    content_type = detected_type or file.content_type or "application/octet-stream"

    if content_type not in settings.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}",
        )

    # --- Upload to S3 ---
    try:
        result = s3_service.upload_file(
            file_obj=file.file,
            filename=file.filename or "unnamed",
            content_type=content_type,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # --- Store metadata in database (optional) ---
    # await store_file_metadata(result["key"], file.filename, content_type, file_size)

    return UploadResponse(
        key=result["key"],
        presigned_url=result["presigned_url"],
        content_type=content_type,
        size=file_size,
    )


@app.post("/api/upload/direct-url", response_model=UploadUrlResponse)
async def get_direct_upload_url(
    filename: str,
    content_type: str = "application/octet-stream",
):
    """
    Alternative: Generate a presigned POST URL so the client can
    upload directly to S3 without proxying through the backend.
    (Better for large files — saves backend bandwidth.)
    """
    result = s3_service.generate_upload_url(filename, content_type)
    return UploadUrlResponse(
        upload_url=result["url"],
        upload_fields=result["fields"],
        key=result["key"],
    )


@app.delete("/api/upload/{key:path}")
async def delete_upload(key: str):
    """Delete an uploaded file from S3."""
    success = s3_service.delete_file(key)
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    return {"deleted": True}
```

### Startup: Ensure Bucket Exists

```python
# Add to startup event
@app.on_event("startup")
async def startup():
    # Ensure S3 bucket exists
    try:
        s3_service.client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError:
        # Bucket doesn't exist — create it
        if settings.AWS_REGION == "us-east-1":
            s3_service.client.create_bucket(Bucket=settings.S3_BUCKET)
        else:
            s3_service.client.create_bucket(
                Bucket=settings.S3_BUCKET,
                CreateBucketConfiguration={"LocationConstraint": settings.AWS_REGION},
            )
        print(f"[S3] Created bucket: {settings.S3_BUCKET}")
```

---

## Frontend: React Upload Component with Progress Bar

```tsx
// src/components/FileUpload.tsx
import React, { useState, useRef } from 'react';

interface UploadResult {
  key: string;
  presigned_url: string;
  content_type: string;
  size: number;
}

export function FileUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setResult(null);
    setError(null);
    setProgress(0);
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);
    setProgress(0);

    try {
      const formData = new FormData();
      formData.append('file', file);

      // Use XMLHttpRequest for progress tracking
      const result = await uploadWithProgress(
        'http://localhost:8000/api/upload',
        formData,
        (pct) => setProgress(pct),
      );

      setResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const copyUrl = () => {
    if (result?.presigned_url) {
      navigator.clipboard.writeText(result.presigned_url);
    }
  };

  const reset = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="upload-container">
      <h1>File Upload</h1>

      {/* File Selector */}
      <div className="file-selector">
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileChange}
          disabled={uploading}
          accept="image/*,.pdf,.txt,.zip"
        />
        {file && (
          <p className="file-info">
            {file.name} ({formatSize(file.size)})
          </p>
        )}
      </div>

      {/* Upload Button */}
      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="upload-button"
      >
        {uploading ? 'Uploading...' : 'Upload to S3'}
      </button>

      {/* Progress Bar */}
      {uploading && (
        <div className="progress-container">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="progress-text">{progress}%</span>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="upload-error" role="alert">
          <p>⚠️ {error}</p>
          <button onClick={reset}>Try another file</button>
        </div>
      )}

      {/* Success State */}
      {result && !uploading && (
        <div className="upload-success">
          <h2>✅ Upload Complete!</h2>
          <div className="result-details">
            <p><strong>File key:</strong> <code>{result.key}</code></p>
            <p><strong>Type:</strong> {result.content_type}</p>
            <p><strong>Size:</strong> {formatSize(result.size)}</p>
            <div className="url-display">
              <p><strong>Presigned URL:</strong></p>
              <div className="url-box">
                <code>{result.presigned_url}</code>
              </div>
              <button onClick={copyUrl} className="copy-button">
                📋 Copy URL
              </button>
            </div>
          </div>

          {/* Preview (for images) */}
          {result.content_type.startsWith('image/') && (
            <div className="preview">
              <img
                src={result.presigned_url}
                alt="Uploaded file preview"
                loading="lazy"
              />
            </div>
          )}

          <button onClick={reset} className="upload-more">
            Upload another file
          </button>
        </div>
      )}
    </div>
  );
}

// --- Helpers ---

function uploadWithProgress(
  url: string,
  formData: FormData,
  onProgress: (pct: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        const pct = Math.round((event.loaded / event.total) * 100);
        onProgress(pct);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `HTTP ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed (HTTP ${xhr.status})`));
        }
      }
    });

    xhr.addEventListener('error', () => {
      reject(new Error('Network error during upload'));
    });

    xhr.addEventListener('abort', () => {
      reject(new Error('Upload cancelled'));
    });

    xhr.open('POST', url);
    xhr.send(formData);
  });
}
```

### Styling

```css
/* src/styles/upload.css */
.upload-container {
  max-width: 600px;
  margin: 40px auto;
  padding: 24px;
  font-family: system-ui, -apple-system, sans-serif;
}

.file-selector {
  margin: 16px 0;
  padding: 20px;
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  text-align: center;
}

.file-info {
  margin-top: 8px;
  color: #6b7280;
  font-size: 0.875rem;
}

.upload-button {
  width: 100%;
  padding: 12px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.2s;
}

.upload-button:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}

.upload-button:hover:not(:disabled) {
  background: #1d4ed8;
}

.progress-container {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #2563eb);
  transition: width 0.3s ease;
  border-radius: 4px;
}

.progress-text {
  font-size: 0.875rem;
  color: #6b7280;
  min-width: 40px;
  text-align: right;
}

.upload-error {
  margin-top: 16px;
  padding: 16px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #dc2626;
}

.upload-success {
  margin-top: 16px;
  padding: 20px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
}

.url-box {
  background: #1f2937;
  color: #e5e7eb;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.8rem;
  word-break: break-all;
  margin: 8px 0;
}

.copy-button {
  padding: 6px 12px;
  background: #374151;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.preview img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 6px;
  margin-top: 12px;
}

.upload-more {
  margin-top: 12px;
  padding: 8px 16px;
  background: transparent;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  cursor: pointer;
}
```

---

## Alternative: Direct Browser-to-S3 Upload

For very large files, bypass the backend entirely:

```tsx
async function uploadDirectToS3(file: File) {
  // 1. Get presigned POST from backend
  const resp = await fetch(
    `/api/upload/direct-url?filename=${encodeURIComponent(file.name)}&content_type=${file.type}`,
  );
  const { upload_url, upload_fields } = await resp.json();

  // 2. Upload directly to S3
  const formData = new FormData();
  Object.entries(upload_fields).forEach(([key, value]) => {
    formData.append(key, value as string);
  });
  formData.append('file', file);

  const s3Resp = await fetch(upload_url, {
    method: 'POST',
    body: formData,
  });

  if (!s3Resp.ok) throw new Error('Direct S3 upload failed');

  // 3. Use the key to construct the URL
  return `https://${upload_fields.bucket}.s3.amazonaws.com/${upload_fields.key}`;
}
```

---

## Key Takeaways

- **Backend proxy upload** (via FastAPI) gives you validation, logging, and metadata tracking.
- **Direct-to-S3 upload** saves backend bandwidth for large files.
- **XMLHttpRequest** is used instead of `fetch` for progress tracking (fetch doesn't support upload progress events).
- **Magic bytes detection** (`python-magic`) is more reliable than trusting the `Content-Type` header.
- **Presigned URLs** provide time-limited secure access without making objects public.
- Always validate file size and type **before** uploading to S3.
