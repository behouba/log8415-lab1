#!/usr/bin/env python3
import os, sys, time
import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
ec2 = boto3.client("ec2", region_name=REGION)

def find_instances():
    instance_ids = set()
    filters = [
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        {"Name": "tag:Name", "Values": ["lab-*"]}
    ]
    try:
        print("Finding instances with tag Name=lab-*...")
        response = ec2.describe_instances(Filters=filters)
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instance_ids.add(instance["InstanceId"])
    except ClientError as e:
        print(f"Error describing instances: {e}")
    return sorted(list(instance_ids))

def terminate_and_wait(ids):
    if not ids:
        print("No instances found to terminate.")
        return
    print(f"Terminating {len(ids)} instance(s): {' '.join(ids)}")
    try:
        ec2.terminate_instances(InstanceIds=ids)
        print("Waiting for termination to complete...")
        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=ids, WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
        print("✅ Instances terminated.")
    except ClientError as e:
        if "InvalidInstanceID.NotFound" not in str(e):
             print(f"An error occurred during termination: {e}")

def sg_id_by_name(vpc_id, name):
    try:
        response = ec2.describe_security_groups(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}, {"Name": "group-name", "Values": [name]}]
        )
        sgs = response.get("SecurityGroups", [])
        return sgs[0]["GroupId"] if sgs else None
    except ClientError:
        return None

def cleanup_security_groups():
    inst_sg_id = os.getenv("AWS_INSTANCE_SG_ID")
    vpc_id = os.getenv("AWS_VPC_ID")
    lb_sg_name = "lab-lb"
    lb_sg_id = sg_id_by_name(vpc_id, lb_sg_name)

    if inst_sg_id and lb_sg_id:
        try:
            print(f"Revoking ingress rule from {inst_sg_id} for LB source {lb_sg_id}...")
            ec2.revoke_security_group_ingress(
                GroupId=inst_sg_id,
                IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 8000, 'ToPort': 8000, 'UserIdGroupPairs': [{'GroupId': lb_sg_id}]}]
            )
        except ClientError as e:
            if "InvalidPermission.NotFound" not in str(e):
                print(f"Note: Could not revoke rule, may not exist. ({e})")

    if lb_sg_id:
        try:
            # Wait a bit for network interfaces to detach after instance termination
            print(f"Waiting a moment before deleting '{lb_sg_name}' security group...")
            time.sleep(15)
            ec2.delete_security_group(GroupId=lb_sg_id)
            print(f"✅ Deleted security group '{lb_sg_name}' ({lb_sg_id}).")
        except ClientError as e:
            print(f"Note: Could not delete SG '{lb_sg_name}'. It may have dependencies or is already gone. ({e})")

def main():
    if "--confirm" not in sys.argv:
        print("This is a destructive operation. Add the --confirm flag to proceed.")
        return

    ids = find_instances()
    terminate_and_wait(ids)
    cleanup_security_groups()

    if "--purge" in sys.argv:
        for p in ("artifacts/instances.json", "artifacts/lb.json", ".env"):
            if os.path.exists(p):
                os.remove(p)
                print(f"Removed local file: {p}")
        if os.path.exists("artifacts"):
            try:
                os.rmdir("artifacts")
                print("Removed local directory: artifacts")
            except OSError:
                pass

    print("\n✅ Teardown complete.")

if __name__ == "__main__":
    main()
