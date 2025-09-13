#!/usr/bin/env python3
import json, os, sys, time
import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
ALB_SG = os.getenv("AWS_ALB_SG_ID")
SUBNETS = os.getenv("AWS_SUBNET_IDS", "").split(",") if os.getenv("AWS_SUBNET_IDS") else []

if not (ALB_SG and SUBNETS and len(SUBNETS) >= 2):
    sys.exit("Missing one of: AWS_ALB_SG_ID, AWS_SUBNET_IDS(2+)")

ec2   = boto3.client("ec2", region_name=REGION)
elbv2 = boto3.client("elbv2", region_name=REGION)

with open("artifacts/instances.json") as f:
    instances = json.load(f)
cluster1_ids = [i["id"] for i in instances if i.get("cluster") == "cluster1"]
cluster2_ids = [i["id"] for i in instances if i.get("cluster") == "cluster2"]

def find_alb_by_name(name: str):
    resp = elbv2.describe_load_balancers()
    for lb in resp.get("LoadBalancers", []):
        if lb["LoadBalancerName"] == name:
            return lb
    return None

def ensure_tg(name: str, hc_path: str):
    try:
        r = elbv2.describe_target_groups(Names=[name])
        tg = r["TargetGroups"][0]
        return tg
    except ClientError as e:
        if e.response["Error"]["Code"] != "TargetGroupNotFound":
            raise
    tg = elbv2.create_target_group(
        Name=name, Protocol="HTTP", Port=8000, VpcId=instances and
        ec2.describe_instances(InstanceIds=[instances[0]["id"]])["Reservations"][0]["Instances"][0]["VpcId"] or None,
        HealthCheckProtocol="HTTP", HealthCheckPath=hc_path, TargetType="instance",
    )["TargetGroups"][0]
    return tg

def ensure_listener(lb_arn: str, default_tg_arn: str):
    ls = elbv2.describe_listeners(LoadBalancerArn=lb_arn).get("Listeners", [])
    for l in ls:
        if l["Port"] == 80 and l["Protocol"] == "HTTP":
            return l
    l = elbv2.create_listener(
        LoadBalancerArn=lb_arn, Protocol="HTTP", Port=80,
        DefaultActions=[{"Type":"forward","TargetGroupArn": default_tg_arn}]
    )["Listeners"][0]
    return l

def ensure_rule(listener_arn: str, path: str, tg_arn: str, priority: int):
    # If a rule with this path exists, update action to our TG
    rules = elbv2.describe_rules(ListenerArn=listener_arn)["Rules"]
    for r in rules:
        conds = r.get("Conditions", [])
        for c in conds:
            if c.get("Field") == "path-pattern" and path in c.get("Values", []):
                acts = r.get("Actions", [])
                if not acts or acts[0].get("TargetGroupArn") != tg_arn:
                    elbv2.modify_rule(
                        RuleArn=r["RuleArn"],
                        Actions=[{"Type":"forward","TargetGroupArn": tg_arn}]
                    )
                return r
    return elbv2.create_rule(
        ListenerArn=listener_arn, Priority=priority,
        Conditions=[{"Field":"path-pattern","Values":[path]}],
        Actions=[{"Type":"forward","TargetGroupArn": tg_arn}],
    )

tg1 = ensure_tg("lab-tg-cluster1", "/cluster1")
tg2 = ensure_tg("lab-tg-cluster2", "/cluster2")

if cluster1_ids:
    elbv2.register_targets(TargetGroupArn=tg1["TargetGroupArn"], Targets=[{"Id": i} for i in cluster1_ids])
if cluster2_ids:
    elbv2.register_targets(TargetGroupArn=tg2["TargetGroupArn"], Targets=[{"Id": i} for i in cluster2_ids])

lb = find_alb_by_name("lab-alb")
if not lb:
    lb = elbv2.create_load_balancer(
        Name="lab-alb", Subnets=SUBNETS, SecurityGroups=[ALB_SG],
        Scheme="internet-facing", Type="application", IpAddressType="ipv4"
    )["LoadBalancers"][0]

while True:
    cur = elbv2.describe_load_balancers(LoadBalancerArns=[lb["LoadBalancerArn"]])["LoadBalancers"][0]
    if cur["State"]["Code"] == "active":
        lb = cur
        break
    time.sleep(3)

listener = ensure_listener(lb["LoadBalancerArn"], tg1["TargetGroupArn"])
ensure_rule(listener["ListenerArn"], "/cluster1*", tg1["TargetGroupArn"], priority=10)
ensure_rule(listener["ListenerArn"], "/cluster2*", tg2["TargetGroupArn"], priority=20)

os.makedirs("artifacts", exist_ok=True)
with open("artifacts/alb.json","w") as f:
    json.dump({"dns": lb["DNSName"], "tg_cluster1": tg1["TargetGroupArn"], "tg_cluster2": tg2["TargetGroupArn"]}, f, indent=2)
print(f"✅ ALB ready: http://{lb['DNSName']}/cluster1  and  http://{lb['DNSName']}/cluster2")
