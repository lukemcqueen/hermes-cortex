---
language: python
tags: [aws, lambda, serverless, cloud]
title: AWS Lambda with Python
description: Complete guide to AWS Lambda functions in Python including handler functions, event/context, environment variables, layers, CloudWatch logging, and API Gateway trigger integration
source: pattern
---

# AWS Lambda with Python

## Basic Handler Function

```python
import json


def lambda_handler(event, context):
    """
    Main Lambda handler function.
    
    Args:
        event (dict): Event data from the trigger source.
        context (LambdaContext): Runtime context with methods/meta.
    
    Returns:
        dict: Response object (shape depends on trigger type).
    """
    # Log the incoming event for debugging
    print(f"Received event: {json.dumps(event, indent=2)}")
    
    # Extract useful context details
    print(f"Function name: {context.function_name}")
    print(f"Function version: {context.function_version}")
    print(f"Remaining time (ms): {context.get_remaining_time_in_millis()}")
    print(f"Log group: {context.log_group_name}")
    print(f"Log stream: {context.log_stream_name}")
    print(f"AWS Request ID: {context.aws_request_id}")
    print(f"Memory limit (MB): {context.memory_limit_in_mb}")
    
    # Process based on event source
    body = event.get('body', event)
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'X-Custom-Header': 'value'
        },
        'body': json.dumps({
            'message': 'Hello from Lambda!',
            'request_id': context.aws_request_id
        })
    }
```

## Event Source Patterns

```python
import json

# ─── API Gateway (REST / HTTP API) ────────────────────────────────────────────

def api_gateway_handler(event, context):
    """Handle API Gateway REST or HTTP API events."""
    http_method = event['httpMethod']
    path = event['path']
    headers = event.get('headers', {})
    query_params = event.get('queryStringParameters', {}) or {}
    path_params = event.get('pathParameters', {}) or {}
    body = json.loads(event.get('body', '{}')) if event.get('body') else {}
    
    print(f"{http_method} {path}")
    print(f"Headers: {headers}")
    print(f"Query params: {query_params}")
    print(f"Path params: {path_params}")
    print(f"Body: {body}")
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE'
        },
        'body': json.dumps({
            'method': http_method,
            'path': path,
            'data': body
        })
    }


# ─── S3 Event Notifications ───────────────────────────────────────────────────

def s3_event_handler(event, context):
    """Handle S3 bucket notification events."""
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']
        event_name = record['eventName']
        
        print(f"Event: {event_name}")
        print(f"Bucket: {bucket}")
        print(f"Object: {object_key}")
        print(f"Size: {record['s3']['object']['size']} bytes")
        
        # Handle specific event types
        if event_name.startswith('ObjectCreated'):
            print(f"New object uploaded: {object_key}")
            # Process the new file...
        elif event_name.startswith('ObjectRemoved'):
            print(f"Object deleted: {object_key}")
        elif event_name.startswith('ObjectRestore'):
            print(f"Object restored from Glacier: {object_key}")
    
    return {'statusCode': 200}


# ─── SQS (Simple Queue Service) ───────────────────────────────────────────────

def sqs_handler(event, context):
    """Handle SQS queue messages (batch)."""
    for record in event['Records']:
        message_id = record['messageId']
        receipt_handle = record['receiptHandle']
        body = record['body']
        attributes = record.get('attributes', {})
        
        print(f"Message ID: {message_id}")
        print(f"Body: {body}")
        print(f"Approximate receive count: {attributes.get('ApproximateReceiveCount')}")
        
        # Process message
        try:
            data = json.loads(body)
            process_message(data)
        except Exception as e:
            print(f"Failed to process message {message_id}: {e}")
            # If returning partial batch failure, raise to retry
            raise
    
    return {'batchItemFailures': []}


# ─── DynamoDB Streams ─────────────────────────────────────────────────────────

def dynamodb_stream_handler(event, context):
    """Handle DynamoDB stream records."""
    for record in event['Records']:
        event_id = record['eventID']
        event_name = record['eventName']  # INSERT, MODIFY, REMOVE
        dynamodb = record['dynamodb']
        
        # Keys and attributes
        keys = dynamodb.get('Keys', {})
        new_image = dynamodb.get('NewImage', {})
        old_image = dynamodb.get('OldImage', {})
        sequence_number = dynamodb.get('SequenceNumber')
        
        print(f"Event: {event_name} ({event_id})")
        print(f"Keys: {keys}")
        
        if event_name == 'INSERT':
            print(f"New record: {new_image}")
        elif event_name == 'MODIFY':
            print(f"Old: {old_image}")
            print(f"New: {new_image}")
        elif event_name == 'REMOVE':
            print(f"Removed: {keys}")
    
    return {'statusCode': 200}


# Helper for processing
def process_message(data: dict):
    """Example message processor."""
    print(f"Processing: {data}")


# ─── CloudWatch Events / EventBridge ──────────────────────────────────────────

def eventbridge_handler(event, context):
    """Handle EventBridge scheduled events."""
    source = event.get('source', 'unknown')
    detail_type = event.get('detail-type', '')
    resources = event.get('resources', [])
    time = event.get('time', '')
    
    print(f"Scheduled event triggered at {time}")
    print(f"Source: {source}, Type: {detail_type}")
    
    # Run periodic tasks
    cleanup_expired_data()
    generate_daily_report()
    
    return {'statusCode': 200}


def cleanup_expired_data():
    """Placeholder for periodic maintenance."""
    print("Performing cleanup...")


def generate_daily_report():
    """Placeholder for reporting."""
    print("Generating report...")
```

## Environment Variables and Configuration

```python
import os
import json

# ─── Accessing Environment Variables ──────────────────────────────────────────

APP_NAME = os.environ.get('APP_NAME', 'MyFunction')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
DATABASE_URL = os.environ['DATABASE_URL']  # Required, will raise KeyError if missing
FEATURE_FLAGS = json.loads(os.environ.get('FEATURE_FLAGS', '{}'))

# ─── Configuration Class ──────────────────────────────────────────────────────

class Config:
    """Type-safe configuration loaded from environment variables."""
    
    def __init__(self):
        self.app_name = os.environ.get('APP_NAME', 'MyLambda')
        self.log_level = os.environ.get('LOG_LEVEL', 'INFO')
        self.database_url = os.environ.get('DATABASE_URL', '')
        self.api_key = os.environ.get('API_KEY', '')
        self.s3_bucket = os.environ.get('S3_BUCKET', '')
        self.max_retries = int(os.environ.get('MAX_RETRIES', '3'))
        self.timeout_seconds = int(os.environ.get('TIMEOUT_SECONDS', '30'))
        self.enable_cache = os.environ.get('ENABLE_CACHE', 'true').lower() == 'true'
        self.allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*').split(',')

    def validate(self) -> list:
        """Check required config is present, return list of missing keys."""
        required = ['database_url', 'api_key']
        return [key for key in required if not getattr(self, key, '')]


config = Config()


def lambda_handler(event, context):
    """Handler using centralized config."""
    missing = config.validate()
    if missing:
        print(f"Missing required config: {', '.join(missing)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Configuration error'})
        }
    
    # Use config values
    print(f"App: {config.app_name}, Log level: {config.log_level}")
    print(f"Cache enabled: {config.enable_cache}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({'status': 'ok', 'app': config.app_name})
    }
```

## Lambda Layers

```python
# ─── Custom Layer Structure ───────────────────────────────────────────────────
#
# Layers are ZIP archives with a specific folder structure. A Python layer must
# follow the `python/` prefix convention:
#
# my-layer.zip
# ├── python/
# │   ├── lib/
# │   │   └── python3.11/
# │   │       └── site-packages/
# │   │           ├── requests/
# │   │           ├── requests-2.31.0.dist-info/
# │   │           └── ...
# │   └── my_custom_module.py
#
# ─── Publishing a Layer from Code ─────────────────────────────────────────────

def publish_layer(layer_name: str, zip_file_path: str, 
                  runtimes: list = None) -> str:
    """
    Publish a new Lambda layer version.
    
    Usage:
        arn = publish_layer('my-utils', '/tmp/layer.zip',
                            runtimes=['python3.10', 'python3.11'])
    """
    import boto3
    
    lambda_client = boto3.client('lambda')
    
    with open(zip_file_path, 'rb') as f:
        response = lambda_client.publish_layer_version(
            LayerName=layer_name,
            Content={'ZipFile': f.read()},
            CompatibleRuntimes=runtimes or ['python3.11'],
            CompatibleArchitectures=['x86_64', 'arm64'],
            Description='Utility functions and dependencies'
        )
    
    layer_arn = response['LayerVersionArn']
    print(f"Published layer: {layer_arn}")
    return layer_arn


# ─── Using a Layer in Code ────────────────────────────────────────────────────

# Assuming a layer contains `my_custom_module`:
try:
    from my_custom_module import helper_function
    helper_function()
except ImportError:
    print("Custom module not available (layer not attached)")


# ─── Common Python Dependencies for Layers ────────────────────────────────────

# requirements.txt for a common layer:
"""
requests==2.31.0
pydantic==2.5.0
python-dateutil==2.8.2
aws-xray-sdk==2.12.1
boto3>=1.28.0
"""

# Build script for creating layer ZIP:
"""
mkdir -p layer/python/lib/python3.11/site-packages
pip install -r requirements.txt -t layer/python/lib/python3.11/site-packages/
cd layer && zip -r ../layer.zip python/
"""
```

## CloudWatch Logging

```python
import logging
import json

# ─── Configure Structured Logging ─────────────────────────────────────────────

class StructuredFormatter(logging.Formatter):
    """Format logs as structured JSON for CloudWatch Logs Insights."""
    
    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        if hasattr(record, 'extra_data'):
            log_entry['extra'] = record.extra_data
        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Remove default Lambda handler (prints raw text) and add structured handler
for handler in logger.handlers:
    logger.removeHandler(handler)

handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.addHandler(handler)


# ─── Usage in Lambda ──────────────────────────────────────────────────────────

def lambda_handler(event, context):
    logger.info("Function invoked", extra={
        'extra_data': {
            'function_name': context.function_name,
            'request_id': context.aws_request_id
        }
    })
    
    try:
        result = process_data(event)
        logger.info("Processing successful", extra={
            'extra_data': {'record_count': len(result)}
        })
        return {'statusCode': 200, 'body': json.dumps(result)}
    except Exception as e:
        logger.error("Processing failed", extra={
            'extra_data': {'error': str(e)}
        }, exc_info=True)
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def process_data(event):
    """Example processing function with logging."""
    data = event.get('data', [])
    logger.debug("Processing data batch", extra={
        'extra_data': {'batch_size': len(data)}
    })
    
    results = []
    for i, item in enumerate(data):
        logger.info(f"Processing item {i}")
        results.append(item.upper() if isinstance(item, str) else item)
    
    return results


# ─── CloudWatch Logs Insights Queries ─────────────────────────────────────────

# Useful queries to run in CloudWatch Logs Insights:
#
# 1. Find all ERROR logs in the last hour:
#   fields @timestamp, @message
#   | filter @message like '"ERROR"'
#   | sort @timestamp desc
#   | limit 50
#
# 2. Group by function and count invocations:
#   fields function_name = json_extract_scalar(@message, '$.extra.function_name')
#   | stats count() by function_name
#
# 3. Find slow executions (> 1 second):
#   fields @timestamp, @message, @duration
#   | filter @duration > 1000
#   | sort @duration desc
```

## Error Handling and Retries

```python
import json
import traceback
from datetime import datetime


class LambdaError(Exception):
    """Base exception for Lambda-specific errors."""
    def __init__(self, message: str, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


class ValidationError(LambdaError):
    """Raised when input validation fails."""
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class NotFoundError(LambdaError):
    """Raised when a resource is not found."""
    def __init__(self, message: str):
        super().__init__(message, status_code=404)


def error_handler(event, context):
    """Handler with centralized error handling."""
    try:
        # Validate input
        if not event.get('body'):
            raise ValidationError("Request body is required")
        
        body = json.loads(event['body'])
        if 'id' not in body:
            raise ValidationError("Field 'id' is required")
        
        # Process
        result = process_request(body)
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result)
        }
        
    except ValidationError as e:
        print(f"Validation error: {e}")
        return format_error(e.status_code, str(e))
        
    except NotFoundError as e:
        print(f"Not found: {e}")
        return format_error(e.status_code, str(e))
        
    except json.JSONDecodeError:
        return format_error(400, "Invalid JSON in request body")
        
    except Exception as e:
        print(f"Unexpected error: {traceback.format_exc()}")
        return format_error(500, "Internal server error")


def format_error(status_code: int, message: str) -> dict:
    """Create a standardized error response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'X-Amzn-ErrorType': 'Error'
        },
        'body': json.dumps({
            'error': {
                'code': status_code,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
        })
    }


def process_request(body: dict) -> dict:
    """Example business logic."""
    item_id = body['id']
    print(f"Processing request for item: {item_id}")
    return {'id': item_id, 'status': 'processed'}
```

## API Gateway Integration

```python
import json
import uuid
from datetime import datetime

# ─── REST API Response Helpers ────────────────────────────────────────────────

def success_response(data, status_code=200):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True
        },
        'body': json.dumps(data)
    }


def error_response(message, status_code=400):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({'error': message})
    }


# ─── CRUD Handler ─────────────────────────────────────────────────────────────

# Simulated database
ITEMS = {}


def crud_handler(event, context):
    """
    RESTful CRUD handler for API Gateway.
    Routes based on HTTP method and path parameters.
    """
    http_method = event['httpMethod']
    path_params = event.get('pathParameters', {}) or {}
    query_params = event.get('queryStringParameters', {}) or {}
    
    try:
        body = json.loads(event.get('body', '{}')) if event.get('body') else {}
    except json.JSONDecodeError:
        return error_response('Invalid JSON body', 400)
    
    item_id = path_params.get('id')
    
    if http_method == 'GET' and item_id:
        return get_item(item_id)
    elif http_method == 'GET':
        return list_items(query_params)
    elif http_method == 'POST':
        return create_item(body)
    elif http_method == 'PUT' and item_id:
        return update_item(item_id, body)
    elif http_method == 'DELETE' and item_id:
        return delete_item(item_id)
    else:
        return error_response('Method not allowed', 405)


def get_item(item_id: str) -> dict:
    item = ITEMS.get(item_id)
    if not item:
        return error_response(f'Item {item_id} not found', 404)
    return success_response(item)


def list_items(params: dict) -> dict:
    limit = min(int(params.get('limit', 50)), 200)
    items = list(ITEMS.values())[:limit]
    return success_response({'items': items, 'count': len(items)})


def create_item(body: dict) -> dict:
    if not body.get('name'):
        return error_response('Field "name" is required', 400)
    
    item_id = str(uuid.uuid4())
    item = {
        'id': item_id,
        'name': body['name'],
        'description': body.get('description', ''),
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }
    ITEMS[item_id] = item
    return success_response(item, status_code=201)


def update_item(item_id: str, body: dict) -> dict:
    if item_id not in ITEMS:
        return error_response(f'Item {item_id} not found', 404)
    
    ITEMS[item_id].update({
        'name': body.get('name', ITEMS[item_id]['name']),
        'description': body.get('description', ITEMS[item_id]['description']),
        'updated_at': datetime.utcnow().isoformat()
    })
    return success_response(ITEMS[item_id])


def delete_item(item_id: str) -> dict:
    if item_id not in ITEMS:
        return error_response(f'Item {item_id} not found', 404)
    
    del ITEMS[item_id]
    return success_response({'message': f'Item {item_id} deleted'})


# ─── API Gateway Authorizer ───────────────────────────────────────────────────

def lambda_authorizer(event, context):
    """
    Custom Lambda authorizer for API Gateway.
    Validates a token and returns an IAM policy document.
    """
    token = event['authorizationToken']
    method_arn = event['methodArn']
    
    # Validate token (this is a simple example — use proper auth in production)
    if token == 'Bearer valid-token':
        effect = 'Allow'
        principal_id = 'user123'
    else:
        effect = 'Deny'
        principal_id = 'unknown'
    
    # Generate IAM policy
    policy = generate_policy(principal_id, effect, method_arn)
    policy['context'] = {
        'userId': principal_id,
        'userRole': 'admin' if effect == 'Allow' else 'guest'
    }
    return policy


def generate_policy(principal_id: str, effect: str, resource: str) -> dict:
    """Generate an IAM policy document for API Gateway."""
    return {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        }
    }
```

## Best Practices and Packaging

```python
# ─── Directory Structure for Lambda Projects ──────────────────────────────────
#
# my-lambda/
# ├── src/
# │   ├── __init__.py
# │   ├── handler.py          # Lambda handler entry point
# │   ├── config.py           # Configuration management
# │   ├── database.py         # Database access layer
# │   ├── services/           # Business logic
# │   │   ├── __init__.py
# │   │   └── process.py
# │   └── utils/              # Utility functions
# │       ├── __init__.py
# │       ├── logging.py
# │       └── validation.py
# ├── tests/
# │   ├── test_handler.py
# │   ├── test_config.py
# │   └── conftest.py
# ├── template.yaml           # AWS SAM template (optional)
# ├── requirements.txt
# └── Dockerfile              # Container image support (optional)
#

# ─── Packaging with SAM (Serverless Application Model) ────────────────────────
#
# template.yaml:
"""
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: My Lambda application

Globals:
  Function:
    Timeout: 30
    MemorySize: 256
    Runtime: python3.11
    Environment:
      Variables:
        LOG_LEVEL: INFO
        DATABASE_URL: !Ref DatabaseUrl

Resources:
  MyFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: handler.lambda_handler
      Layers:
        - !Ref MyLayer
      Events:
        ApiEvent:
          Type: Api
          Properties:
            Path: /{proxy+}
            Method: ANY
      Policies:
        - S3CrudPolicy:
            BucketName: !Ref MyBucket
        - DynamoDBCrudPolicy:
            TableName: !Ref MyTable
"""

# ─── Deploy with SAM CLI ──────────────────────────────────────────────────────
#
# Build:    sam build
# Package:  sam package --s3-bucket my-deploy-bucket --output-template packaged.yaml
# Deploy:   sam deploy --template-file packaged.yaml --stack-name my-stack --capabilities CAPABILITY_IAM
#
# ─── Container Image Support ───────────────────────────────────────────────────
#
# Dockerfile:
"""
FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt .
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY src/ ${LAMBDA_TASK_ROOT}

CMD ["handler.lambda_handler"]
"""
```