#!/usr/bin/env python3
import json, os, sys, itertools
import boto3

REGION   = os.getenv("AWS_REGION", "us-east-1")
KEY_NAME = os.getenv("AWS_KEY_NAME")
SG_ID    = os.getenv("AWS_INSTANCE_SG_ID")
AMI_ID   = os.getenv("AWS_AMI_ID", "")
SUBNETS  = os.getenv("AWS_SUBNET_IDS", "").split(",") if os.getenv("AWS_SUBNET_IDS") else []

if not (KEY_NAME and SG_ID and SUBNETS and len(SUBNETS) >= 2):
    sys.exit("Missing one of: AWS_KEY_NAME, AWS_INSTANCE_SG_ID, AWS_SUBNET_IDS(2+)")

ec2 = boto3.resource("ec2", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)

if not AMI_ID:
    print("AMI_ID not found in environment, resolving from AWS SSM...")
    try:
        AMI_ID = ssm.get_parameter(
            Name="/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
        )["Parameter"]["Value"]
    except Exception:
        AMI_ID = ssm.get_parameter(
            Name="/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
        )["Parameter"]["Value"]
    print(f"Using Ubuntu 22.04 AMI: {AMI_ID}")

def create_group(instance_type: str, count: int, cluster_tag: str):
    subnet_cycle = itertools.cycle(SUBNETS)
    instances = []
    print(f"Creating {count} x {instance_type} instance(s) for {cluster_tag}...")
    for _ in range(count):
        subnet = next(subnet_cycle)
        instance_group = ec2.create_instances(
            ImageId=AMI_ID,
            InstanceType=instance_type,
            MinCount=1, MaxCount=1,
            KeyName=KEY_NAME,
            NetworkInterfaces=[{
                "DeviceIndex": 0,
                "SubnetId": subnet,
                "AssociatePublicIpAddress": True,
                "Groups": [SG_ID],
            }],
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": f"lab-{cluster_tag}-{instance_type}"},
                    {"Key": "Cluster", "Value": cluster_tag},
                ],
            }],
        )
        instances.extend(instance_group)
    return instances

print("Creating 4 x t2.large (cluster1) and 4 x t2.micro (cluster2)...")
grp_large = create_group("t2.large", 4, "cluster1")
grp_micro = create_group("t2.micro", 4, "cluster2")
all_instances = grp_large + grp_micro