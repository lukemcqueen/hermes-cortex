#!/usr/bin/env python3
"""Verify MinIO S3 API on port 9002."""
import urllib.request, hashlib, hmac, datetime

access = '598088ddb580be913ccceaa0bb296509'
secret = '960b2c...1503'
bucket = 'langfuse'

amz_date = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
date_stamp = amz_date[:8]

def sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()

def s3_request(method, path, body=None):
    if body:
        payload_hash = hashlib.sha256(body).hexdigest()
    else:
        payload_hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    
    canonical_uri = '/' + bucket + '/' + path.lstrip('/')
    canonical_headers = (f'host:localhost:9002\nx-amz-content-sha256:{payload_hash}\n'
                        f'x-amz-date:{amz_date}\n')
    signed_headers = 'host;x-amz-content-sha256;x-amz-date'
    canonical_req = f'{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}'
    
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f'{date_stamp}/us-east-1/s3/aws4_request'
    string_to_sign = f'{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_req.encode()).hexdigest()}'
    
    date_key = sign(('AWS4' + secret).encode(), date_stamp)
    region_key = sign(date_key, 'us-east-1')
    service_key = sign(region_key, 's3')
    signing_key = sign(service_key, 'aws4_request')
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    
    auth = f'{algorithm} Credential={access}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
    req = urllib.request.Request(f'http://localhost:9002{canonical_uri}', data=body, method=method)
    req.add_header('Authorization', auth)
    req.add_header('x-amz-date', amz_date)
    req.add_header('x-amz-content-sha256', payload_hash)
    if body:
        req.add_header('Content-Type', 'application/json')
    
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return -1, str(e)

# Test HEAD on bucket
print("HEAD /langfuse/:", s3_request('HEAD', '/')[0])
print("Write test-write.json:", s3_request('PUT', 'test-write.json', b'{"test": true}')[0])
print("Read test-write.json:", s3_request('GET', 'test-write.json')[0])
print("Delete test-write.json:", s3_request('DELETE', 'test-write.json')[0])