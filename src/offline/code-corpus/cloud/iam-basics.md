---
language: python
tags: [aws, iam, security, permissions]
title: AWS IAM with boto3
description: Manage IAM roles, policies (managed vs inline), trust relationships, least privilege, service roles, and policy simulation using boto3
source: pattern
---

# AWS IAM with boto3

## Setup and Client Initialization

```python
import boto3
import json
from botocore.exceptions import ClientError
import time

# Initialize IAM client
iam = boto3.client('iam')
```

## Roles and Trust Relationships

```python
def create_service_role(role_name: str, service: str, description: str = None) -> dict:
    """
    Create an IAM role for an AWS service with a trust policy.
    
    Common service principals:
    - ec2.amazonaws.com      - EC2 instances
    - lambda.amazonaws.com   - Lambda functions
    - ecs-tasks.amazonaws.com - ECS tasks
    - s3.amazonaws.com       - S3
    - apigateway.amazonaws.com - API Gateway
    """
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": service
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description=description or f"Role for {service}"
        )
        role = response['Role']
        print(f"Role '{role_name}' created (ARN: {role['Arn']})")
        return role
    except ClientError as e:
        if e.response['Error']['Code'] == 'EntityAlreadyExists':
            print(f"Role '{role_name}' already exists")
            return get_role(role_name)
        raise


def create_cross_account_role(role_name: str, account_id: str,
                               external_id: str = None) -> dict:
    """
    Create a role that trusts another AWS account (cross-account access).
    Optionally requires an External ID for additional security.
    """
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{account_id}:root"
                },
                "Action": "sts:AssumeRole",
                "Condition": {}
            }
        ]
    }
    
    # Add External ID condition if provided
    if external_id:
        trust_policy["Statement"][0]["Condition"] = {
            "StringEquals": {
                "sts:ExternalId": external_id
            }
        }
    
    response = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description=f"Cross-account role for AWS account {account_id}"
    )
    return response['Role']


def create_federated_role(role_name: str, idp_arn: str) -> dict:
    """Create a role for federated identity (SAML/OIDC)."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Federated": idp_arn
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        f"{idp_arn.split('/')[-1]}:aud": "sts.amazonaws.com"
                    }
                }
            }
        ]
    }
    
    response = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description=f"Federated role for {idp_arn}"
    )
    return response['Role']


def get_role(role_name: str) -> dict:
    """Get an IAM role by name."""
    response = iam.get_role(RoleName=role_name)
    return response['Role']


def update_assume_role_policy(role_name: str, trust_policy: dict) -> bool:
    """Update the trust policy on an existing role."""
    try:
        iam.update_assume_role_policy(
            RoleName=role_name,
            PolicyDocument=json.dumps(trust_policy)
        )
        print(f"Trust policy updated for role '{role_name}'")
        return True
    except ClientError as e:
        print(f"Failed to update trust policy: {e}")
        return False


# Usage
ec2_role = create_service_role('EC2AppRole', 'ec2.amazonaws.com',
                                'Role for EC2 instances running the application')
lambda_role = create_service_role('LambdaExecutionRole', 'lambda.amazonaws.com',
                                   'Base Lambda execution role')
cross_account_role = create_cross_account_role('CrossAccountReader', '123456789012',
                                                external_id='my-secret-external-id')
```

## Managed Policies (AWS Managed and Customer Managed)

```python
def attach_managed_policies(role_name: str, policy_arns: list) -> bool:
    """Attach managed policies to a role."""
    success = True
    for policy_arn in policy_arns:
        try:
            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            policy_name = policy_arn.split('/')[-1]
            print(f"  Attached: {policy_name}")
        except ClientError as e:
            print(f"  Failed to attach {policy_arn}: {e}")
            success = False
    return success


def detach_managed_policies(role_name: str, policy_arns: list) -> bool:
    """Detach managed policies from a role."""
    success = True
    for policy_arn in policy_arns:
        try:
            iam.detach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            print(f"  Detached: {policy_arn.split('/')[-1]}")
        except ClientError as e:
            print(f"  Failed to detach: {e}")
            success = False
    return success


def list_attached_policies(role_name: str) -> list:
    """List all managed policies attached to a role."""
    policies = []
    paginator = iam.get_paginator('list_attached_role_policies')
    for page in paginator.paginate(RoleName=role_name):
        for policy in page['AttachedPolicies']:
            policies.append({
                'name': policy['PolicyName'],
                'arn': policy['PolicyArn']
            })
    return policies


def create_customer_managed_policy(policy_name: str, policy_document: dict,
                                    description: str = None) -> str:
    """Create a customer managed policy."""
    try:
        response = iam.create_policy(
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document),
            Description=description or f'Customer managed policy: {policy_name}'
        )
        policy_arn = response['Policy']['Arn']
        print(f"Policy '{policy_name}' created (ARN: {policy_arn})")
        return policy_arn
    except ClientError as e:
        if e.response['Error']['Code'] == 'EntityAlreadyExists':
            print(f"Policy '{policy_name}' already exists")
            return get_policy_arn(policy_name)
        raise


def get_policy_arn(policy_name: str) -> str:
    """Get the ARN for a customer managed policy by name."""
    paginator = iam.get_paginator('list_policies')
    for page in paginator.paginate(Scope='Local'):
        for policy in page['Policies']:
            if policy['PolicyName'] == policy_name:
                return policy['Arn']
    return None


# AWS managed policy ARNs - common ones
AWS_MANAGED_POLICIES = {
    'AdministratorAccess': 'arn:aws:iam::aws:policy/AdministratorAccess',
    'ReadOnlyAccess': 'arn:aws:iam::aws:policy/ReadOnlyAccess',
    'AmazonS3FullAccess': 'arn:aws:iam::aws:policy/AmazonS3FullAccess',
    'AmazonS3ReadOnlyAccess': 'arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess',
    'AmazonDynamoDBFullAccess': 'arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess',
    'AmazonDynamoDBReadOnlyAccess': 'arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess',
    'CloudWatchLogsFullAccess': 'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess',
    'AWSLambdaBasicExecutionRole': 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
    'AWSLambdaVPCAccessExecutionRole': 'arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole',
    'AmazonEC2FullAccess': 'arn:aws:iam::aws:policy/AmazonEC2FullAccess',
    'AmazonEC2ReadOnlyAccess': 'arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess',
}


# Usage: Attach policies following least privilege
attach_managed_policies('EC2AppRole', [
    AWS_MANAGED_POLICIES['CloudWatchLogsFullAccess'],
    AWS_MANAGED_POLICIES['AmazonS3ReadOnlyAccess'],
    AWS_MANAGED_POLICIES['AmazonDynamoDBReadOnlyAccess'],
])

print("Attached policies:", list_attached_policies('EC2AppRole'))
```

## Inline Policies (Least Privilege Examples)

```python
def put_inline_policy(role_name: str, policy_name: str, policy_document: dict) -> bool:
    """Create or update an inline policy on a role."""
    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document)
        )
        print(f"Inline policy '{policy_name}' applied to role '{role_name}'")
        return True
    except ClientError as e:
        print(f"Failed to put inline policy: {e}")
        return False


def delete_inline_policy(role_name: str, policy_name: str) -> bool:
    """Delete an inline policy from a role."""
    try:
        iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
        print(f"Inline policy '{policy_name}' deleted from '{role_name}'")
        return True
    except ClientError as e:
        print(f"Failed to delete inline policy: {e}")
        return False


def list_inline_policies(role_name: str) -> list:
    """List all inline policy names on a role."""
    policies = []
    paginator = iam.get_paginator('list_role_policies')
    for page in paginator.paginate(RoleName=role_name):
        policies.extend(page['PolicyNames'])
    return policies


# ─── Least Privilege Policy Examples ──────────────────────────────────────────

# EC2: Allow reading from a specific S3 bucket only
s3_read_only_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:GetObjectVersion",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::my-application-bucket",
                "arn:aws:s3:::my-application-bucket/*"
            ]
        }
    ]
}

# Lambda: Access DynamoDB table + CloudWatch logs
lambda_dynamodb_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Query",
                "dynamodb:Scan"
            ],
            "Resource": "arn:aws:dynamodb:us-east-1:123456789012:table/MyTable"
        }
    ]
}

# EC2: Describe instances and manage tags only
ec2_read_and_tags_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeTags",
                "ec2:CreateTags",
                "ec2:DeleteTags"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:StartInstances",
                "ec2:StopInstances"
            ],
            "Resource": "arn:aws:ec2:us-east-1:123456789012:instance/*",
            "Condition": {
                "StringEquals": {
                    "aws:ResourceTag/Environment": "development"
                }
            }
        }
    ]
}

# SQS: Send and receive messages from a specific queue
sqs_consumer_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes",
                "sqs:ChangeMessageVisibility"
            ],
            "Resource": "arn:aws:sqs:us-east-1:123456789012:my-processing-queue"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sqs:SendMessage"
            ],
            "Resource": "arn:aws:sqs:us-east-1:123456789012:my-output-queue"
        }
    ]
}

# Usage
put_inline_policy('EC2AppRole', 'S3ReadOnly', s3_read_only_policy)
put_inline_policy('LambdaExecutionRole', 'DynamoDBAccess', lambda_dynamodb_policy)
put_inline_policy('EC2AppRole', 'EC2TagManagement', ec2_read_and_tags_policy)

print("Inline policies:", list_inline_policies('EC2AppRole'))
```

## Service Roles for Specific AWS Services

```python
# ─── Common Service Roles ─────────────────────────────────────────────────────

def create_lambda_basic_role(role_name: str = 'lambda-basic-execution') -> dict:
    """Create a Lambda execution role with basic logging permissions."""
    role = create_service_role(
        role_name, 'lambda.amazonaws.com',
        'Basic Lambda execution role with CloudWatch logs access'
    )
    attach_managed_policies(role_name, [
        AWS_MANAGED_POLICIES['AWSLambdaBasicExecutionRole']
    ])
    return role


def create_ec2_s3_role(role_name: str = 'ec2-s3-access') -> dict:
    """Create an EC2 role with S3 read access (for use with instance profiles)."""
    role = create_service_role(
        role_name, 'ec2.amazonaws.com',
        'EC2 role with S3 read access'
    )
    attach_managed_policies(role_name, [
        AWS_MANAGED_POLICIES['AmazonS3ReadOnlyAccess']
    ])
    
    # Create and attach instance profile
    try:
        iam.create_instance_profile(InstanceProfileName=role_name)
        iam.add_role_to_instance_profile(
            InstanceProfileName=role_name,
            RoleName=role_name
        )
        print(f"Instance profile '{role_name}' created and linked")
    except ClientError as e:
        if e.response['Error']['Code'] != 'EntityAlreadyExists':
            raise
    
    return role


def create_ecs_task_role(role_name: str = 'ecs-task-role') -> dict:
    """Create an ECS task execution role."""
    return create_service_role(
        role_name, 'ecs-tasks.amazonaws.com',
        'ECS task execution role'
    )


def create_api_gateway_cloudwatch_role(role_name: str = 'api-gateway-cw') -> dict:
    """Create an API Gateway role for CloudWatch logging."""
    role = create_service_role(
        role_name, 'apigateway.amazonaws.com',
        'API Gateway CloudWatch logging role'
    )
    cloudwatch_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:PutLogEvents",
                    "logs:GetLogEvents",
                    "logs:FilterLogEvents"
                ],
                "Resource": "*"
            }
        ]
    }
    put_inline_policy(role_name, 'CloudWatchLogs', cloudwatch_policy)
    return role


# Usage
lambda_role = create_lambda_basic_role()
ec2_role = create_ec2_s3_role()
api_role = create_api_gateway_cloudwatch_role()
```

## Policy Simulator

```python
def simulate_policy(policy_source_arn: str, actions: list,
                    resource_arns: list = None) -> list:
    """
    Simulate whether a list of actions are allowed or denied by the given policy.
    Uses the IAM Policy Simulator API.
    """
    params = {
        'PolicySourceArn': policy_source_arn,
        'ActionNames': actions,
    }
    if resource_arns:
        params['ResourceArns'] = resource_arns
    
    try:
        response = iam.simulate_principal_policy(**params)
        results = []
        for result in response['EvaluationResults']:
            results.append({
                'action': result['EvalActionName'],
                'decision': result['EvalDecision'],  # allowed | denied | explicitDeny
                'matched_statements': result.get('MatchedStatements', []),
                'missing_actions': result.get('MissingContextValues', [])
            })
        return results
    except ClientError as e:
        print(f"Policy simulation failed: {e}")
        return []


def validate_lambda_permissions(role_name: str) -> list:
    """Verify that a Lambda execution role has the expected permissions."""
    role = get_role(role_name)
    
    actions = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "s3:GetObject",  # Not expected to be allowed
    ]
    
    results = simulate_policy(role['Arn'], actions)
    
    print(f"Policy simulation for role '{role_name}':")
    for r in results:
        status = "✅ ALLOWED" if r['decision'] == 'allowed' else \
                 "❌ DENIED" if r['decision'] == 'explicitDeny' else \
                 "⚠️  IMPLICIT DENY"
        print(f"  {status} - {r['action']}")
    
    return results


def compare_policies(policy_arn_1: str, policy_arn_2: str, actions: list) -> None:
    """Compare two policies by simulating the same actions against both."""
    results_1 = simulate_policy(policy_arn_1, actions)
    results_2 = simulate_policy(policy_arn_2, actions)
    
    print(f"{'Action':<40} {'Policy 1':<15} {'Policy 2':<15}")
    print("-" * 70)
    for r1, r2 in zip(results_1, results_2):
        print(f"{r1['action']:<40} {r1['decision']:<15} {r2['decision']:<15}")


# Usage
validate_lambda_permissions('LambdaExecutionRole')

# Simulate specific access
results = simulate_policy(
    get_role('EC2AppRole')['Arn'],
    ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    ["arn:aws:s3:::my-application-bucket/*"]
)
```

## Least Privilege Audit Helper

```python
def audit_role_permissions(role_name: str) -> dict:
    """
    Audit a role and identify potentially over-permissive policies.
    Returns a report of all attached policies and inline policies.
    """
    report = {
        'role_name': role_name,
        'arn': '',
        'trust_policy': None,
        'managed_policies': [],
        'inline_policies': []
    }
    
    try:
        role = get_role(role_name)
        report['arn'] = role['Arn']
        report['trust_policy'] = json.loads(role['AssumeRolePolicyDocument'])
    except ClientError as e:
        report['error'] = str(e)
        return report
    
    # Managed policies
    for policy in list_attached_policies(role_name):
        report['managed_policies'].append(policy['name'])
    
    # Inline policies
    for policy_name in list_inline_policies(role_name):
        response = iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
        report['inline_policies'].append({
            'name': policy_name,
            'document': json.loads(response['PolicyDocument'])
        })
    
    return report


def check_for_wildcard_permissions(policy_document: dict) -> list:
    """Check a policy document for overly permissive statements."""
    findings = []
    for i, statement in enumerate(policy_document.get('Statement', [])):
        actions = statement.get('Action', [])
        if isinstance(actions, str):
            actions = [actions]
        
        resources = statement.get('Resource', [])
        if isinstance(resources, str):
            resources = [resources]
        
        # Check for wildcard action
        for action in actions:
            if action == '*' or ':*' in action:
                findings.append({
                    'statement_index': i,
                    'issue': 'Wildcard action',
                    'action': action,
                    'resource': resources,
                    'effect': statement['Effect']
                })
        
        # Check for wildcard resource
        for resource in resources:
            if resource == '*':
                findings.append({
                    'statement_index': i,
                    'issue': 'Wildcard resource',
                    'action': actions,
                    'resource': resource,
                    'effect': statement['Effect']
                })
    
    return findings


# Usage
report = audit_role_permissions('EC2AppRole')
print(f"Role: {report['role_name']} ({report['arn']})")
print(f"Trust policy: {json.dumps(report['trust_policy'], indent=2)}")
print(f"Managed policies: {', '.join(report['managed_policies'])}")

for inline in report['inline_policies']:
    print(f"\nInline policy: {inline['name']}")
    findings = check_for_wildcard_permissions(inline['document'])
    if findings:
        print("  ⚠️  Potential issues found:")
        for finding in findings:
            print(f"    - [{finding['issue']}] {finding['action']} on {finding['resource']}")
    else:
        print("  ✅ No wildcard permissions found")
```

## Tag-Based Access Control

```python
def create_tag_based_policy(role_name: str, 
                             allowed_environment: str = 'development',
                             allowed_project: str = 'my-app') -> bool:
    """
    Apply a tag-based access control policy.
    Users can only manage resources with matching tags.
    """
    tag_based_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "ec2:*",
                "Resource": "*",
                "Condition": {
                    "StringEquals": {
                        "aws:ResourceTag/Environment": allowed_environment,
                        "aws:ResourceTag/Project": allowed_project
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DescribeInstances",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeTags"
                ],
                "Resource": "*"
            }
        ]
    }
    
    return put_inline_policy(role_name, 'TagBasedEC2Access', tag_based_policy)


# Usage
create_tag_based_policy('DeveloperRole', 'development', 'my-app')
```

## Permissions Boundary Example

```python
def create_permissions_boundary(boundary_name: str = 'MaxPermissionsBoundary') -> str:
    """
    Create a permissions boundary policy that sets the maximum allowed permissions.
    Roles/users with this boundary cannot grant permissions beyond it.
    """
    boundary_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:Describe*",
                    "ec2:CreateTags",
                    "ec2:DeleteTags",
                    "s3:List*",
                    "s3:Get*",
                    "logs:Describe*",
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Deny",
                "Action": [
                    "iam:*",
                    "organizations:*",
                    "account:*"
                ],
                "Resource": "*"
            }
        ]
    }
    
    return create_customer_managed_policy(
        boundary_name, boundary_policy,
        'Max permissions boundary for developer roles'
    )


def create_role_with_boundary(role_name: str, boundary_arn: str) -> dict:
    """Create a role with a permissions boundary."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    response = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        PermissionsBoundary=boundary_arn,
        Description=f'Role with permissions boundary'
    )
    return response['Role']


# Usage
boundary_arn = create_permissions_boundary()
role = create_role_with_boundary('LimitedEC2Role', boundary_arn)
```