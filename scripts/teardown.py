#!/usr/bin/env python3
import os, sys, json, time
import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
ec2 = boto3.client("ec2", region_name=REGION)

def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return None

def terminate_and_wait(ids):
    if not ids: return
    print(f"Terminating {len(ids)} instance(s): {' '.join(ids)}")
    try:
        ec2.terminate_instances(InstanceIds=ids)
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("InvalidInstanceID.NotFound","IncorrectInstanceState"):
            raise
    print("Waiting for termination…")
    ec2.get_waiter("instance_terminated").wait(InstanceIds=ids)
    print("Instances terminated.")

def revoke_ingress(dst_sg_id, src_sg_id, port=8000):
    if not (dst_sg_id and src_sg_id): return
    try:
        ec2.revoke_security_group_ingress(
            GroupId=dst_sg_id,
            IpPermissions=[{
                "IpProtocol":"tcp","FromPort":port,"ToPort":port,
                "UserIdGroupPairs":[{"GroupId":src_sg_id}],
            }],
        )
        print(f"Revoked ingress tcp/{port} on {dst_sg_id} from {src_sg_id}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "InvalidPermission.NotFound":
            print(f"Note: could not revoke rule ({e.response['Error']['Code']}). Continuing.")

def delete_sg(group_id):
    if not group_id: return
    for _ in range(10):
        try:
            ec2.delete_security_group(GroupId=group_id)
            print(f"Deleted SG {group_id}")
            return
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "DependencyViolation":
                time.sleep(2); continue
            if code == "InvalidGroup.NotFound":
                return
            print(f"Note: could not delete SG ({code})."); return

def sg_id_by_name(vpc_id, name):
    try:
        r = ec2.describe_security_groups(
            Filters=[{"Name":"vpc-id","Values":[vpc_id]},
                     {"Name":"group-name","Values":[name]}]
        )
        if r["SecurityGroups"]:
            return r["SecurityGroups"][0]["GroupId"]
    except ClientError:
        pass
    return None

def main():
    if "--confirm" not in sys.argv:
        print("Add --confirm to actually delete resources. Optional: --purge")
        return

    apps = load_json("artifacts/instances.json") or []
    lb   = load_json("artifacts/lb.json") or {}

    app_ids = [i.get("id") for i in apps if i.get("id")]
    lb_id   = lb.get("id")
    lb_sg   = lb.get("sg")

    ids = [i for i in (app_ids + ([lb_id] if lb_id else [])) if i]
    terminate_and_wait(ids)

    # Revoke instance SG rule that allowed LB → instances:8000
    inst_sg = os.getenv("AWS_INSTANCE_SG_ID")
    vpc_id  = os.getenv("AWS_VPC_ID")
    if not lb_sg and vpc_id:
        lb_sg = sg_id_by_name(vpc_id, "lab-lb")
    revoke_ingress(inst_sg, lb_sg, 8000)

    # Delete the LB SG
    delete_sg(lb_sg)

    if "--purge" in sys.argv:
        for p in ("artifacts/instances.json","artifacts/lb.json"):
            try: os.remove(p)
            except Exception: pass
        try: os.rmdir("artifacts")
        except Exception: pass
        print("Purged local artifacts.")

    print("✅ Teardown complete.")

if __name__ == "__main__":
    main()
