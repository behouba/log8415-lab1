#!/usr/bin/env python3
import json, os, sys, time
import boto3

REGION = os.getenv("AWS_REGION","us-east-1")
ALB_SG = os.getenv("AWS_ALB_SG_ID")
VPC_ID = os.getenv("AWS_VPC_ID")
SUBNETS = os.getenv("AWS_SUBNET_IDS","").split(",")

if not (ALB_SG and VPC_ID and SUBNETS and len(SUBNETS)>=2):
    sys.exit("Missing one of: AWS_ALB_SG_ID, AWS_VPC_ID, AWS_SUBNET_IDS(2+)")

with open("artifacts/instances.json") as f:
    INST = json.load(f)

cluster1 = [i["id"] for i in INST if i["cluster"]=="cluster1"]
cluster2 = [i["id"] for i in INST if i["cluster"]=="cluster2"]

elbv2 = boto3.client("elbv2", region_name=REGION)

tg1 = elbv2.create_target_group(
    Name="lab-tg-cluster1", Protocol="HTTP", Port=8000, VpcId=VPC_ID,
    HealthCheckProtocol="HTTP", HealthCheckPath="/cluster1", TargetType="instance"
)["TargetGroups"][0]
tg2 = elbv2.create_target_group(
    Name="lab-tg-cluster2", Protocol="HTTP", Port=8000, VpcId=VPC_ID,
    HealthCheckProtocol="HTTP", HealthCheckPath="/cluster2", TargetType="instance"
)["TargetGroups"][0]

def reg(arn, ids):
    if ids:
        elbv2.register_targets(TargetGroupArn=arn, Targets=[{"Id": i} for i in ids])

reg(tg1["TargetGroupArn"], cluster1)
reg(tg2["TargetGroupArn"], cluster2)

alb = elbv2.create_load_balancer(
    Name="lab-alb", Subnets=SUBNETS, SecurityGroups=[ALB_SG],
    Scheme="internet-facing", Type="application", IpAddressType="ipv4"
)["LoadBalancers"][0]

listener = elbv2.create_listener(
    LoadBalancerArn=alb["LoadBalancerArn"], Protocol="HTTP", Port=80,
    DefaultActions=[{"Type":"forward","TargetGroupArn": tg1["TargetGroupArn"]}]
)["Listeners"][0]

elbv2.create_rule(
    ListenerArn=listener["ListenerArn"], Priority=10,
    Conditions=[{"Field":"path-pattern","Values":["/cluster1*"]}],
    Actions=[{"Type":"forward","TargetGroupArn": tg1["TargetGroupArn"]}],
)
elbv2.create_rule(
    ListenerArn=listener["ListenerArn"], Priority=20,
    Conditions=[{"Field":"path-pattern","Values":["/cluster2*"]}],
    Actions=[{"Type":"forward","TargetGroupArn": tg2["TargetGroupArn"]}],
)

print("⏳ Waiting for ALB to be active…")
while True:
    lb = elbv2.describe_load_balancers(LoadBalancerArns=[alb["LoadBalancerArn"]])["LoadBalancers"][0]
    if lb["State"]["Code"] == "active":
        break
    time.sleep(5)

dns = lb["DNSName"]
os.makedirs("artifacts", exist_ok=True)
with open("artifacts/alb.json","w") as f:
    json.dump({"dns": dns}, f, indent=2)
print(f"✅ ALB ready: http://{dns}/cluster1  and  http://{dns}/cluster2")
