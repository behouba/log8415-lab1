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
    try:
        AMI_ID = ssm.get_parameter(
            Name="/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
        )["Parameter"]["Value"]
    except Exception:
        AMI_ID = ssm.get_parameter(
            Name="/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
        )["Parameter"]["Value"]

def create_group(instance_type: str, count: int, cluster_tag: str):
    rr = itertools.cycle(SUBNETS)
    instances = []
    for _ in range(count):
        subnet = next(rr)
        r = ec2.create_instances(
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
        instances.extend(r)
    return instances

print("Creating 4× t2.micro (cluster2) and 4× t2.large (cluster1)…")
grp_micro = create_group("t2.micro", 4, "cluster2")
grp_large = create_group("t2.large", 4, "cluster1")
all_instances = grp_micro + grp_large

for i in all_instances:
    print(f"⏱ Waiting for {i.id}…")
    i.wait_until_running()
    i.load()

out = []
for i in all_instances:
    cluster = None
    print(f"✅ {i.id} {i.instance_type} {i.state['Name']} {i.public_ip_address} {i.private_ip_address}")
    for t in (i.tags or []):
        if t.get("Key") == "Cluster":
            cluster = t["Value"]
    out.append({
        "id": i.id,
        "type": i.instance_type,
        "state": i.state["Name"],
        "public_ip": i.public_ip_address,
        "private_ip": i.private_ip_address,
        "cluster": cluster,
    })

os.makedirs("artifacts", exist_ok=True)
with open("artifacts/instances.json", "w") as f:
    json.dump(out, f, indent=2)
print("✅ Wrote artifacts/instances.json with instance IDs and IPs.")
