#!/usr/bin/env python3
import os, sys, time
import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
ec2 = boto3.client("ec2", region_name=REGION)

def find_instances():
    ids = set()
    def grab(filters):
        try:
            r = ec2.describe-instances(Filters=filters)
            for res in r.get("Reservations", []):
                for i in res.get("Instances", []):
                    ids.add(i["InstanceId"])
        except ClientError:
            pass

    states = "pending,running,stopping,stopped"
    grab([
        {"Name":"tag:Name","Values":["lab-*"]},
        {"Name":"instance-state-name","Values":states.split(",")}
    ])
    grab([
        {"Name":"tag:Cluster","Values":["cluster1","cluster2"]},
        {"Name":"instance-state-name","Values":states.split(",")}
    ])
    grab([
        {"Name":"tag:Role","Values":["lb"]},
        {"Name":"instance-state-name","Values":states.split(",")}
    ])
    return sorted(ids)

def terminate_and_wait(ids):
    if not ids:
        print("No instances to terminate.")
        return
    print(f"Terminating {len(ids)} instance(s): {' '.join(ids)}")
    try:
        ec2.terminate_instances(InstanceIds=ids)
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("InvalidInstanceID.NotFound","IncorrectInstanceState"):
            raise
    print("Waiting for termination…")
    ec2.get_waiter("instance_terminated").wait(InstanceIds=ids)
    print("Instances terminated.")

def sg_id_by_name(vpc_id, name):
    try:
        r = ec2.describe-security-groups(
            Filters=([{"Name":"vpc-id","Values":[vpc_id]}] if vpc_id else []) +
                    [{"Name":"group-name","Values":[name]}]
        )
        sgs = r.get("SecurityGroups", [])
        return sgs[0]["GroupId"] if sgs else None
    except ClientError:
        return None

def revoke_ingress(inst_sg_id, lb_sg_id, port=8000):
    if not (inst_sg_id and lb_sg_id): return
    try:
        ec2.revoke_security_group_ingress(
            GroupId=inst_sg_id,
            IpPermissions=[{
                "IpProtocol":"tcp",
                "FromPort":port, "ToPort":port,
                "UserIdGroupPairs":[{"GroupId":lb_sg_id}],
            }],
        )
        print(f"Revoked ingress tcp/{port} on {inst_sg_id} from {lb_sg_id}")
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

def main():
    if "--confirm" not in sys.argv:
        print("Add --confirm to actually delete resources. Optional: --purge")
        return

    ids = find_instances()
    terminate_and_wait(ids)

    inst_sg = os.getenv("AWS_INSTANCE_SG_ID")
    vpc_id  = os.getenv("AWS_VPC_ID")
    lb_sg   = sg_id_by_name(vpc_id, "lab-lb")
    revoke_ingress(inst_sg, lb_sg, 8000)
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
