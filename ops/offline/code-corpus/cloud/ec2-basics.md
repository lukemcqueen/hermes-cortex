---
language: python
tags: [aws, ec2, compute, cloud]
title: AWS EC2 Basics with boto3
description: Launch and manage EC2 instances using boto3 including security groups, key pairs, SSH access, EBS volumes, tags, and instance lifecycle management
source: pattern
---

# AWS EC2 Basics with boto3

## Setup and Client Initialization

```python
import boto3
from botocore.exceptions import ClientError
import time
import os

# Initialize EC2 client and resource
ec2_client = boto3.client('ec2', region_name='us-east-1')
ec2_resource = boto3.resource('ec2', region_name='us-east-1')
```

## Key Pairs

```python
def create_key_pair(key_name: str, private_key_path: str = None) -> str:
    """
    Create a new EC2 key pair and save the private key.
    Returns the key pair ID.
    """
    try:
        key_pair = ec2_client.create_key_pair(KeyName=key_name)
        
        private_key = key_pair['KeyMaterial']
        key_path = private_key_path or os.path.expanduser(f'~/.ssh/{key_name}.pem')
        
        with open(key_path, 'w') as f:
            f.write(private_key)
        os.chmod(key_path, 0o400)  # Secure the private key
        
        print(f"Key pair '{key_name}' created and saved to {key_path}")
        return key_pair['KeyPairId']
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidKeyPair.Duplicate':
            print(f"Key pair '{key_name}' already exists")
            return None
        raise


def list_key_pairs() -> list:
    """List all key pairs."""
    response = ec2_client.describe_key_pairs()
    return [{
        'name': kp['KeyName'],
        'id': kp['KeyPairId'],
        'type': kp.get('KeyType', 'rsa'),
        'fingerprint': kp['KeyFingerprint']
    } for kp in response['KeyPairs']]


def delete_key_pair(key_name: str) -> bool:
    """Delete a key pair."""
    try:
        ec2_client.delete_key_pair(KeyName=key_name)
        print(f"Key pair '{key_name}' deleted")
        return True
    except ClientError as e:
        print(f"Failed to delete key pair: {e}")
        return False


# Usage
create_key_pair('my-app-key', '/Users/me/.ssh/my-app-key.pem')
print(list_key_pairs())
```

## Security Groups

```python
def create_web_security_group(group_name: str, description: str = None,
                              vpc_id: str = None) -> str:
    """
    Create a security group with common web server rules.
    Returns the Group ID.
    """
    try:
        response = ec2_client.create_security_group(
            GroupName=group_name,
            Description=description or f'Security group for {group_name}',
            VpcId=vpc_id or get_default_vpc_id()
        )
        group_id = response['GroupId']
        
        # Add inbound rules
        ec2_client.authorize_security_group_ingress(
            GroupId=group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTP'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 443,
                    'ToPort': 443,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS'}]
                }
            ]
        )
        
        print(f"Security group '{group_name}' ({group_id}) created")
        return group_id
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidGroup.Duplicate':
            print(f"Security group '{group_name}' already exists")
            return get_security_group_id(group_name)
        raise


def create_internal_sg(group_name: str, source_sg_id: str, vpc_id: str = None) -> str:
    """
    Create a security group that only allows traffic from another security group.
    Useful for internal service-to-service communication.
    """
    response = ec2_client.create_security_group(
        GroupName=group_name,
        Description=f'Internal traffic only from {source_sg_id}',
        VpcId=vpc_id or get_default_vpc_id()
    )
    group_id = response['GroupId']
    
    # Allow all TCP traffic from the source security group
    ec2_client.authorize_security_group_ingress(
        GroupId=group_id,
        IpPermissions=[{
            'IpProtocol': 'tcp',
            'FromPort': 0,
            'ToPort': 65535,
            'UserIdGroupPairs': [{
                'GroupId': source_sg_id,
                'Description': 'Internal traffic'
            }]
        }]
    )
    return group_id


def get_default_vpc_id() -> str:
    """Get the default VPC ID for the region."""
    response = ec2_client.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    return response['Vpcs'][0]['VpcId'] if response['Vpcs'] else None


def get_security_group_id(group_name: str) -> str:
    """Get security group ID by name."""
    response = ec2_client.describe_security_groups(
        Filters=[{'Name': 'group-name', 'Values': [group_name]}]
    )
    return response['SecurityGroups'][0]['GroupId'] if response['SecurityGroups'] else None


def describe_security_group(group_id: str) -> dict:
    """Describe a security group with its rules."""
    response = ec2_client.describe_security_groups(GroupIds=[group_id])
    sg = response['SecurityGroups'][0]
    return {
        'id': sg['GroupId'],
        'name': sg['GroupName'],
        'vpc_id': sg['VpcId'],
        'inbound_rules': sg.get('IpPermissions', []),
        'outbound_rules': sg.get('IpPermissionsEgress', [])
    }


# Usage
web_sg_id = create_web_security_group('web-server-sg')
internal_sg_id = create_internal_sg('app-to-db-sg', web_sg_id)
```

## Launch Instances

```python
def launch_instance(
    image_id: str = 'ami-0c02fb55956c7d316',  # Amazon Linux 2023 (us-east-1)
    instance_type: str = 't3.micro',
    key_name: str = None,
    security_group_ids: list = None,
    user_data: str = None,
    name: str = None,
    min_count: int = 1,
    max_count: int = 1
) -> list:
    """
    Launch one or more EC2 instances with common configuration.
    Returns list of instance IDs.
    """
    params = {
        'ImageId': image_id,
        'InstanceType': instance_type,
        'MinCount': min_count,
        'MaxCount': max_count,
    }
    
    if key_name:
        params['KeyName'] = key_name
    if security_group_ids:
        params['SecurityGroupIds'] = security_group_ids
    if user_data:
        params['UserData'] = user_data
    
    try:
        response = ec2_client.run_instances(**params)
        instances = response['Instances']
        instance_ids = [inst['InstanceId'] for inst in instances]
        
        print(f"Launched {len(instance_ids)} instance(s): {', '.join(instance_ids)}")
        
        # Add Name tag if provided
        if name:
            ec2_client.create_tags(
                Resources=instance_ids,
                Tags=[
                    {'Key': 'Name', 'Value': name},
                    {'Key': 'Environment', 'Value': 'development'}
                ]
            )
            print(f"Tagged instances with Name={name}")
        
        return instance_ids
    except ClientError as e:
        print(f"Failed to launch instances: {e}")
        return []


def launch_with_user_data(instance_name: str) -> list:
    """Launch an instance that installs and starts a web server at boot."""
    user_data_script = """#!/bin/bash
yum update -y
yum install -y httpd
systemctl start httpd
systemctl enable httpd
echo "<html><body><h1>Hello from EC2!</h1></body></html>" > /var/www/html/index.html
"""
    
    return launch_instance(
        key_name='my-app-key',
        security_group_ids=['sg-xxxxxxxx'],
        user_data=user_data_script,
        name=instance_name
    )


def launch_spot_instance(
    image_id: str,
    instance_type: str = 't3.micro',
    key_name: str = None,
    security_group_ids: list = None,
    max_price: str = '0.01',
    name: str = None
) -> str:
    """
    Launch a spot instance for cost savings.
    Returns the instance ID.
    """
    try:
        response = ec2_client.request_spot_instances(
            SpotPrice=max_price,
            InstanceCount=1,
            LaunchSpecification={
                'ImageId': image_id,
                'InstanceType': instance_type,
                'KeyName': key_name,
                'SecurityGroupIds': security_group_ids or []
            }
        )
        
        request_id = response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
        print(f"Spot request submitted: {request_id}")
        
        # Wait for the request to be fulfilled
        print("Waiting for spot instance to be provisioned...")
        waiter = ec2_client.get_waiter('spot_instance_request_fulfilled')
        waiter.wait(SpotInstanceRequestIds=[request_id])
        
        # Get the instance ID from the fulfilled request
        request = ec2_client.describe_spot_instance_requests(
            SpotInstanceRequestIds=[request_id]
        )
        instance_id = request['SpotInstanceRequests'][0]['InstanceId']
        
        if name:
            ec2_client.create_tags(
                Resources=[instance_id],
                Tags=[
                    {'Key': 'Name', 'Value': name},
                    {'Key': 'Spot', 'Value': 'true'}
                ]
            )
        
        print(f"Spot instance {instance_id} is running")
        return instance_id
    except ClientError as e:
        print(f"Failed to launch spot instance: {e}")
        return None
```

## Describe and Manage Instances

```python
def describe_instances(instance_ids: list = None, filters: list = None) -> list:
    """
    Describe EC2 instances with optional filtering.
    """
    params = {}
    if instance_ids:
        params['InstanceIds'] = instance_ids
    if filters:
        params['Filters'] = filters
    
    response = ec2_client.describe_instances(**params)
    
    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances.append(extract_instance_info(instance))
    
    return instances


def extract_instance_info(instance: dict) -> dict:
    """Extract relevant fields from an EC2 instance description."""
    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
    
    return {
        'id': instance['InstanceId'],
        'name': tags.get('Name', ''),
        'state': instance['State']['Name'],
        'type': instance['InstanceType'],
        'az': instance['Placement']['AvailabilityZone'],
        'private_ip': instance.get('PrivateIpAddress', ''),
        'public_ip': instance.get('PublicIpAddress', ''),
        'public_dns': instance.get('PublicDnsName', ''),
        'key_name': instance.get('KeyName', ''),
        'vpc_id': instance.get('VpcId', ''),
        'subnet_id': instance.get('SubnetId', ''),
        'security_groups': [
            {'id': sg['GroupId'], 'name': sg['GroupName']}
            for sg in instance.get('SecurityGroups', [])
        ],
        'launch_time': instance['LaunchTime'],
        'tags': tags
    }


# Filter examples
def get_running_instances() -> list:
    """Get all running instances."""
    return describe_instances(filters=[
        {'Name': 'instance-state-name', 'Values': ['running']}
    ])


def get_instances_by_name(name_pattern: str) -> list:
    """Find instances by Name tag pattern."""
    return describe_instances(filters=[
        {'Name': 'tag:Name', 'Values': [name_pattern]}
    ])


def get_instances_by_environment(env: str) -> list:
    """Find instances by Environment tag."""
    return describe_instances(filters=[
        {'Name': 'tag:Environment', 'Values': [env]}
    ])


# Usage
all_instances = describe_instances()
running = get_running_instances()
web_servers = get_instances_by_name('web-*')
production = get_instances_by_environment('production')

for inst in running:
    print(f"{inst['name']} ({inst['id']}) - {inst['public_ip']} - {inst['state']}")
```

## Stop, Start, and Terminate Instances

```python
def stop_instances(instance_ids: list, force: bool = False) -> bool:
    """Stop one or more instances."""
    try:
        if force:
            ec2_client.stop_instances(InstanceIds=instance_ids, Force=True)
        else:
            ec2_client.stop_instances(InstanceIds=instance_ids)
        
        print(f"Stopping instances: {', '.join(instance_ids)}")
        
        # Wait for instances to stop
        waiter = ec2_client.get_waiter('instance_stopped')
        waiter.wait(InstanceIds=instance_ids)
        print("Instances stopped")
        return True
    except ClientError as e:
        print(f"Failed to stop instances: {e}")
        return False


def start_instances(instance_ids: list) -> bool:
    """Start one or more stopped instances."""
    try:
        ec2_client.start_instances(InstanceIds=instance_ids)
        print(f"Starting instances: {', '.join(instance_ids)}")
        
        waiter = ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=instance_ids)
        print("Instances running")
        return True
    except ClientError as e:
        print(f"Failed to start instances: {e}")
        return False


def terminate_instances(instance_ids: list) -> bool:
    """Terminate one or more instances (permanent)."""
    try:
        ec2_client.terminate_instances(InstanceIds=instance_ids)
        print(f"Terminating instances: {', '.join(instance_ids)}")
        
        waiter = ec2_client.get_waiter('instance_terminated')
        waiter.wait(InstanceIds=instance_ids)
        print("Instances terminated")
        return True
    except ClientError as e:
        print(f"Failed to terminate instances: {e}")
        return False


def reboot_instances(instance_ids: list) -> bool:
    """Reboot one or more instances."""
    try:
        ec2_client.reboot_instances(InstanceIds=instance_ids)
        print(f"Rebooting instances: {', '.join(instance_ids)}")
        return True
    except ClientError as e:
        print(f"Failed to reboot instances: {e}")
        return False


# Usage
stop_instances(['i-xxxxxxxx', 'i-yyyyyyyy'])
time.sleep(5)
start_instances(['i-xxxxxxxx'])
# terminate_instances(['i-xxxxxxxx'])  # Be careful!
```

## EBS Volumes

```python
def create_volume(size_gb: int, availability_zone: str = None,
                  volume_type: str = 'gp3', snapshot_id: str = None,
                  encrypted: bool = False, name: str = None) -> str:
    """Create an EBS volume."""
    try:
        az = availability_zone or 'us-east-1a'
        params = {
            'Size': size_gb,
            'AvailabilityZone': az,
            'VolumeType': volume_type,
            'Encrypted': encrypted
        }
        if snapshot_id:
            params['SnapshotId'] = snapshot_id
        
        response = ec2_client.create_volume(**params)
        volume_id = response['VolumeId']
        
        if name:
            ec2_client.create_tags(
                Resources=[volume_id],
                Tags=[{'Key': 'Name', 'Value': name}]
            )
        
        print(f"Volume {volume_id} ({size_gb}GB, {volume_type}) created in {az}")
        
        # Wait for volume to be available
        waiter = ec2_client.get_waiter('volume_available')
        waiter.wait(VolumeIds=[volume_id])
        
        return volume_id
    except ClientError as e:
        print(f"Failed to create volume: {e}")
        return None


def attach_volume(volume_id: str, instance_id: str, device: str = '/dev/xvdf') -> bool:
    """Attach an EBS volume to an instance."""
    try:
        ec2_client.attach_volume(
            VolumeId=volume_id,
            InstanceId=instance_id,
            Device=device
        )
        print(f"Volume {volume_id} attached to {instance_id} as {device}")
        
        # Wait for volume to be attached
        waiter = ec2_client.get_waiter('volume_in_use')
        waiter.wait(VolumeIds=[volume_id])
        return True
    except ClientError as e:
        print(f"Failed to attach volume: {e}")
        return False


def detach_volume(volume_id: str, instance_id: str = None,
                  force: bool = False) -> bool:
    """Detach an EBS volume from an instance."""
    try:
        params = {'VolumeId': volume_id}
        if instance_id:
            params['InstanceId'] = instance_id
        if force:
            params['Force'] = True
        
        ec2_client.detach_volume(**params)
        print(f"Volume {volume_id} detached")
        
        waiter = ec2_client.get_waiter('volume_available')
        waiter.wait(VolumeIds=[volume_id])
        return True
    except ClientError as e:
        print(f"Failed to detach volume: {e}")
        return False


def create_snapshot(volume_id: str, description: str = None) -> str:
    """Create a snapshot of an EBS volume for backup."""
    try:
        response = ec2_client.create_snapshot(
            VolumeId=volume_id,
            Description=description or f'Snapshot of {volume_id}'
        )
        snapshot_id = response['SnapshotId']
        print(f"Snapshot {snapshot_id} created for volume {volume_id}")
        return snapshot_id
    except ClientError as e:
        print(f"Failed to create snapshot: {e}")
        return None


def list_volumes(instance_id: str = None) -> list:
    """List EBS volumes, optionally filtered by attached instance."""
    filters = []
    if instance_id:
        filters.append({'Name': 'attachment.instance-id', 'Values': [instance_id]})
    
    response = ec2_client.describe_volumes(Filters=filters if filters else [])
    
    volumes = []
    for vol in response['Volumes']:
        tags = {t['Key']: t['Value'] for t in vol.get('Tags', [])}
        volumes.append({
            'id': vol['VolumeId'],
            'size': vol['Size'],
            'type': vol['VolumeType'],
            'state': vol['State'],
            'az': vol['AvailabilityZone'],
            'iops': vol.get('Iops', ''),
            'encrypted': vol['Encrypted'],
            'name': tags.get('Name', ''),
            'attachments': [
                {
                    'instance_id': att['InstanceId'],
                    'device': att['Device'],
                    'attach_time': att['AttachTime']
                }
                for att in vol.get('Attachments', [])
            ]
        })
    return volumes


# Usage
vol_id = create_volume(20, 'us-east-1a', name='data-volume')
attach_volume(vol_id, 'i-xxxxxxxx', '/dev/xvdf')
print(list_volumes(instance_id='i-xxxxxxxx'))
```

## Managing Tags

```python
def tag_resources(resource_ids: list, tags: dict) -> bool:
    """Add or update tags on resources."""
    try:
        ec2_client.create_tags(
            Resources=resource_ids,
            Tags=[{'Key': k, 'Value': v} for k, v in tags.items()]
        )
        print(f"Tags applied to {len(resource_ids)} resources")
        return True
    except ClientError as e:
        print(f"Failed to tag resources: {e}")
        return False


def remove_tags(resource_ids: list, tag_keys: list) -> bool:
    """Remove specific tags from resources."""
    try:
        ec2_client.delete_tags(
            Resources=resource_ids,
            Tags=[{'Key': k} for k in tag_keys]
        )
        print(f"Tags {tag_keys} removed from {len(resource_ids)} resources")
        return True
    except ClientError as e:
        print(f"Failed to remove tags: {e}")
        return False


def find_resources_by_tag(tag_key: str, tag_value: str) -> list:
    """Find all EC2 resources with a specific tag."""
    filters = [{'Name': f'tag:{tag_key}', 'Values': [tag_value]}]
    
    # Search across resource types
    results = {}
    
    # Instances
    instances = ec2_client.describe_instances(Filters=filters)
    results['instances'] = [
        inst['InstanceId']
        for res in instances['Reservations']
        for inst in res['Instances']
    ]
    
    # Volumes
    volumes = ec2_client.describe_volumes(Filters=filters)
    results['volumes'] = [v['VolumeId'] for v in volumes['Volumes']]
    
    # Security groups
    sgs = ec2_client.describe_security_groups(Filters=filters)
    results['security_groups'] = [sg['GroupId'] for sg in sgs['SecurityGroups']]
    
    return results


# Standard tagging convention
STANDARD_TAGS = {
    'Environment': 'development',  # development, staging, production
    'Project': 'my-project',
    'Owner': 'team-name',
    'CostCenter': '12345',
    'ManagedBy': 'boto3-scripts'
}

# Usage
tag_resources(['i-xxxxxxxx', 'vol-xxxxxxxx'], STANDARD_TAGS)
resources = find_resources_by_tag('Environment', 'production')
print(f"Production instances: {resources.get('instances', [])}")
```

## SSH Access Helper

```python
import subprocess
import json

def get_instance_ssh_info(instance_id: str) -> dict:
    """Get SSH connection details for an instance."""
    instances = describe_instances(instance_ids=[instance_id])
    if not instances:
        print(f"Instance {instance_id} not found")
        return None
    
    inst = instances[0]
    
    if inst['state'] != 'running':
        print(f"Instance {instance_id} is {inst['state']}, not running")
        return None
    
    ip = inst.get('public_ip') or inst.get('private_ip')
    if not ip:
        print(f"No IP address found for instance {instance_id}")
        return None
    
    return {
        'ip': ip,
        'key_name': inst['key_name'],
        'instance_id': instance_id,
        'name': inst['name'],
        'dns': inst.get('public_dns', ''),
        'az': inst['az']
    }


def ssh_command(instance_id: str, key_path: str, user: str = 'ec2-user',
                command: str = None) -> str:
    """
    Run a command on an EC2 instance via SSH.
    Default user: ec2-user (Amazon Linux), ubuntu (Ubuntu), admin (others)
    """
    info = get_instance_ssh_info(instance_id)
    if not info:
        return None
    
    ssh_cmd = [
        'ssh', '-o', 'StrictHostKeyChecking=no',
        '-o', 'ConnectTimeout=10',
        '-i', key_path,
        f'{user}@{info["ip"]}'
    ]
    
    if command:
        ssh_cmd.append(command)
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        return result.stdout if result.returncode == 0 else result.stderr
    else:
        print(f"SSH command: {' '.join(ssh_cmd)}")
        return None


# Usage
ssh_command('i-xxxxxxxx', '/Users/me/.ssh/my-app-key.pem', command='uname -a')
ssh_command('i-xxxxxxxx', '/Users/me/.ssh/my-app-key.pem', command='df -h')
```

## AMI Management

```python
def create_image(instance_id: str, image_name: str, description: str = None,
                 no_reboot: bool = False) -> str:
    """Create an AMI from a running instance."""
    try:
        response = ec2_client.create_image(
            InstanceId=instance_id,
            Name=image_name,
            Description=description or f'AMI of {instance_id}',
            NoReboot=no_reboot
        )
        image_id = response['ImageId']
        print(f"AMI {image_id} created from instance {instance_id}")
        return image_id
    except ClientError as e:
        print(f"Failed to create AMI: {e}")
        return None


def list_amis(owners: list = None, filters: list = None) -> list:
    """List AMIs from specified owners with optional filters."""
    params = {}
    if owners:
        params['Owners'] = owners
    if filters:
        params['Filters'] = filters
    
    response = ec2_client.describe_images(**params)
    
    amis = []
    for image in response['Images']:
        amis.append({
            'id': image['ImageId'],
            'name': image['Name'],
            'description': image.get('Description', ''),
            'state': image['State'],
            'architecture': image['Architecture'],
            'platform': image.get('PlatformDetails', 'Linux'),
            'creation_date': image['CreationDate'],
            'root_device': image['RootDeviceType'],
            'virtualization': image['VirtualizationType']
        })
    return sorted(amis, key=lambda x: x['creation_date'], reverse=True)


# Usage
image_id = create_image('i-xxxxxxxx', 'my-app-v1-20240601', no_reboot=True)

# List your AMIs
my_amis = list_amis(owners=['self'])
for ami in my_amis:
    print(f"{ami['name']} ({ami['id']}) - {ami['state']} - {ami['creation_date']}")
```