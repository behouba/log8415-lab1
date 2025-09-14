#!/usr/bin/env python3
import json, os, sys, time

import urllib
import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
VPC_ID = os.getenv("AWS_VPC_ID")
SUBNETS = os.getenv("AWS_SUBNET_IDS", "").split(",") if os.getenv("AWS_SUBNET_IDS") else []
KEY = os.getenv("AWS_KEY_NAME")
AMI = os.getenv("AWS_AMI_ID")
INST_SG = os.getenv("AWS_INSTANCE_SG_ID")

if not (VPC_ID and SUBNETS and KEY and AMI and INST_SG):
    sys.exit("Missing one of: AWS_VPC_ID, AWS_SUBNET_IDS, AWS_KEY_NAME, AWS_AMI_ID, AWS_INSTANCE_SG_ID")

ec2 = boto3.client("ec2", region_name=REGION)
ec2r = boto3.resource("ec2", region_name=REGION)

def ensure_sg(name, desc):
    try:
        r = ec2.describe_security_groups(
            Filters=[{"Name":"vpc-id","Values":[VPC_ID]}, {"Name":"group-name","Values":[name]}]
        )
        if r["SecurityGroups"]:
            return r["SecurityGroups"][0]["GroupId"]
    except ClientError:
        pass
    r = ec2.create_security_group(
        GroupName=name, Description=desc, VpcId=VPC_ID
    )
    return r["GroupId"]

def allow_ingress_cidr(sg, port, cidr="0.0.0.0/0", proto="tcp"):
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg, IpPermissions=[{
                "IpProtocol": proto,
                "FromPort": port, "ToPort": port,
                "IpRanges": [{"CidrIp": cidr}]
            }]
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise

def allow_ingress_sg(dst_sg, port, src_sg, proto="tcp"):
    try:
        ec2.authorize_security_group_ingress(
            GroupId=dst_sg, IpPermissions=[{
                "IpProtocol": proto,
                "FromPort": port, "ToPort": port,
                "UserIdGroupPairs": [{"GroupId": src_sg}]
            }]
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise

print("Ensuring LB security group…")
LB_SG = ensure_sg("lab-lb", "Custom LB SG")
allow_ingress_cidr(LB_SG, 80, "0.0.0.0/0")   # LB listens on 80

try:
    my_ip = urllib.request.urlopen('https://checkip.amazonaws.com').read().decode('utf8').strip()
    print(f"Allowing SSH (port 22) from IP: {my_ip}")
    allow_ingress_cidr(LB_SG, 22, f"{my_ip}/32")
except Exception as e:
    print(f"⚠️  Could not determine your public IP to allow SSH. You may need to add a rule for port 22 manually to the 'lab-lb' security group. Error: {e}")

# Instances must allow 8000 from the LB SG:
allow_ingress_sg(INST_SG, 8000, LB_SG)

print("Launching LB instance (t2.micro, Ubuntu 22.04)…")
inst = ec2r.create_instances(
    ImageId=AMI, InstanceType="t2.micro", MinCount=1, MaxCount=1,
    KeyName=KEY,
    NetworkInterfaces=[{
        "DeviceIndex": 0,
        "SubnetId": SUBNETS[0],
        "AssociatePublicIpAddress": True,
        "Groups": [LB_SG],
    }],
    TagSpecifications=[{
        "ResourceType":"instance",
        "Tags":[{"Key":"Name","Value":"lab-lb-instance"}, {"Key":"Role","Value":"lb"}]
    }]
)[0]

inst.wait_until_running(); inst.load()
data = {
  "id": inst.id,
  "public_ip": inst.public_ip_address,
  "private_ip": inst.private_ip_address,
  "sg": LB_SG
}
os.makedirs("artifacts", exist_ok=True)
with open("artifacts/lb.json","w") as f:
    json.dump(data, f, indent=2)

print(f"✅ LB instance ready: {data['public_ip']} (sg {LB_SG})")
