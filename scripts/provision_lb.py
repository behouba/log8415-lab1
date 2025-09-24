#!/usr/bin/env python3
import json, os, sys, time, urllib.request
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
            sg_id = r["SecurityGroups"][0]["GroupId"]
            print(f"Found existing security group '{name}' with ID: {sg_id}")
            return sg_id
    except ClientError:
        pass
    print(f"Creating new security group '{name}'...")
    r = ec2.create_security_group(
        GroupName=name, Description=desc, VpcId=VPC_ID
    )
    return r["GroupId"]

def authorize_ingress(group_id, **kwargs):
    try:
        ec2.authorize_security_group_ingress(GroupId=group_id, IpPermissions=[kwargs])
    except ClientError as e:
        if e.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise

print("Ensuring LB security group 'lab-lb' exists and is configured...")
LB_SG = ensure_sg("lab-lb", "Custom LB SG")

# Rule 1: Allow HTTP traffic from anyone to the LB
print(f"  - Authorizing inbound HTTP (port 80) from 0.0.0.0/0 on SG {LB_SG}")
authorize_ingress(LB_SG, IpProtocol="tcp", FromPort=80, ToPort=80, IpRanges=[{"CidrIp": "0.0.0.0/0"}])

# Rule 2: Allow SSH traffic from YOUR IP to the LB for deployment
try:
    my_ip = urllib.request.urlopen('https://checkip.amazonaws.com', timeout=5).read().decode('utf8').strip()
    print(f"  - Authorizing inbound SSH (port 22) from your IP ({my_ip}) on SG {LB_SG}")
    authorize_ingress(LB_SG, IpProtocol="tcp", FromPort=22, ToPort=22, IpRanges=[{"CidrIp": f"{my_ip}/32"}])
except Exception as e:
    print(f"⚠️  Could not determine public IP to allow SSH. You may need to add a rule for port 22 manually. Error: {e}")

# Rule 3: Allow app instances to receive traffic from the LB
print(f"  - Authorizing inbound traffic on port 8000 from LB SG ({LB_SG}) on App SG ({INST_SG})")
authorize_ingress(INST_SG, IpProtocol="tcp", FromPort=8000, ToPort=8000, UserIdGroupPairs=[{"GroupId": LB_SG}])

print("\nLaunching LB instance (t2.large, Ubuntu 22.04)...")
inst_list = ec2r.create_instances(
    ImageId=AMI, InstanceType="t2.large", MinCount=1, MaxCount=1,
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
)
inst = inst_list[0]

print(f"Waiting for LB instance {inst.id} to start...")
inst.wait_until_running()
inst.load()

data = {
  "id": inst.id,
  "public_ip": inst.public_ip_address,
  "private_ip": inst.private_ip_address,
  "sg": LB_SG
}
os.makedirs("artifacts", exist_ok=True)
with open("artifacts/lb.json","w") as f:
    json.dump(data, f, indent=2)

print(f"✅ LB instance ready: {data['public_ip']} (ID: {data['id']})")