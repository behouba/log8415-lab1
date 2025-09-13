#!/usr/bin/env python3
import json, os, sys, time
import boto3

REGION = os.getenv("AWS_REGION","us-east-1")
elbv2 = boto3.client("elbv2", region_name=REGION)
ec2   = boto3.client("ec2",   region_name=REGION)

def delete_alb_stack():
    # by names we used
    for name in ["lab-alb"]:
        lbs = elbv2.describe_load_balancers(Names=[name])["LoadBalancers"] if name else []
        for lb in lbs:
            print(f"Deleting listener(s) for {lb['LoadBalancerName']}")
            ls = elbv2.describe_listeners(LoadBalancerArn=lb["LoadBalancerArn"])["Listeners"]
            for l in ls:
                # delete rules then listener
                if "ListenerArn" in l:
                    rules = elbv2.describe_rules(ListenerArn=l["ListenerArn"])["Rules"]
                    for r in rules:
                        if r.get("Priority") not in (None, "default"):
                            elbv2.delete_rule(RuleArn=r["RuleArn"])
                    elbv2.delete_listener(ListenerArn=l["ListenerArn"])
            print(f"Deleting ALB {lb['LoadBalancerName']}")
            elbv2.delete_load_balancer(LoadBalancerArn=lb["LoadBalancerArn"])
            # wait until deleted
            while True:
                try:
                    elbv2.describe_load_balancers(LoadBalancerArns=[lb["LoadBalancerArn"]])
                    time.sleep(3)
                except Exception:
                    break

    # target groups
    for tgname in ["lab-tg-cluster1","lab-tg-cluster2"]:
        try:
            tg = elbv2.describe_target_groups(Names=[tgname])["TargetGroups"][0]
            print(f"Deregister & delete TG {tgname}")
            th = elbv2.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])["TargetHealthDescriptions"]
            if th:
                elbv2.deregister_targets(TargetGroupArn=tg["TargetGroupArn"],
                                         Targets=[{"Id": t["Target"]["Id"]} for t in th])
            elbv2.delete_target_group(TargetGroupArn=tg["TargetGroupArn"])
        except Exception:
            pass

def terminate_instances():
    with open("artifacts/instances.json") as f:
        inst = json.load(f)
    ids = [i["id"] for i in inst]
    if not ids:
        return
    print(f"Terminating {len(ids)} instances…")
    ec2.terminate_instances(InstanceIds=ids)
    waiter = ec2.get_waiter("instance_terminated")
    waiter.wait(InstanceIds=ids)
    print("Instances terminated.")

if __name__ == "__main__":
    if "--confirm" not in sys.argv:
        print("Add --confirm to actually delete resources.")
        sys.exit(0)
    delete_alb_stack()
    terminate_instances()
    print("✅ Teardown complete.")
