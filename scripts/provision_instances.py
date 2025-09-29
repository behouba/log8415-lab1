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

print("\nWaiting for all instances to enter the 'running' state...")
for i in all_instances:
    print(f"  ⏱  Waiting for {i.id} ({i.instance_type})...")
    i.wait_until_running()
    i.load() # Refresh instance attributes like public_ip_address

print("\n✅ All instances are running. Details:")
output_data = []
for i in all_instances:
    cluster_tag = next((tag['Value'] for tag in (i.tags or []) if tag.get("Key") == "Cluster"), "unknown")
    print(f"  - {i.id} | {i.instance_type} | {cluster_tag} | {i.public_ip_address}")
    output_data.append({
        "id": i.id,
        "type": i.instance_type,
        "state": i.state["Name"],
        "public_ip": i.public_ip_address,
        "private_ip": i.private_ip_address,
        "cluster": cluster_tag,
    })

os.makedirs("artifacts", exist_ok=True)
with open("artifacts/instances.json", "w") as f:
    json.dump(output_data, f, indent=2)
print("\n✅ Wrote instance details to artifacts/instances.json.")
