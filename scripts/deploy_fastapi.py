#!/usr/bin/env python3
import json, os, subprocess, pathlib, sys

KEY_PATH = os.getenv("AWS_KEY_PATH")
if not KEY_PATH:
    sys.exit("Missing AWS_KEY_PATH")

with open("artifacts/instances.json") as f:
    INST = json.load(f)

APP_SRC = pathlib.Path("app").resolve()

def ssh(user, host, cmd):
    base = ["ssh","-o","StrictHostKeyChecking=no","-i",KEY_PATH,f"{user}@{host}",cmd]
    return subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

def scp(user, host, src, dst):
    base = ["scp","-o","StrictHostKeyChecking=no","-i",KEY_PATH,"-r",src,f"{user}@{host}:{dst}"]
    return subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

def detect_user(host):
    for user in ["ec2-user","ubuntu"]:
        r = ssh(user, host, "whoami")
        if r.returncode == 0:
            return user
    raise RuntimeError(f"Could not SSH to {host} with ec2-user or ubuntu")

def deploy_one(host, cluster):
    user = detect_user(host)
    print(f"{host} ({cluster}) as {user}")

    cmds = [
        "sudo yum -y update || true",
        "sudo apt-get update -y || true",
        "sudo apt-get upgrade -y || true",
        "sudo yum -y install python3 python3-pip || true",
        "sudo apt-get install -y python3 python3-pip || true",
        "mkdir -p ~/app && rm -rf ~/app/*",
    ]
    for c in cmds:
        ssh(user, host, c)

    r = scp(user, host, str(APP_SRC), "~")
    if r.returncode != 0:
        print(r.stdout); sys.exit(f"SCP failed to {host}")

    ssh(user, host, "python3 -m pip install --upgrade pip")
    ssh(user, host, "python3 -m pip install fastapi uvicorn")

    ssh(user, host, "pkill -f 'uvicorn main:app' || true")
    ssh(user, host,
        f"nohup env CLUSTER_NAME={cluster} python3 -m uvicorn main:app "
        "--host 0.0.0.0 --port 8000 >/tmp/uvicorn.log 2>&1 &")

for inst in INST:
    ip = inst.get("public_ip")
    if ip:
        deploy_one(ip, inst.get("cluster",""))
print("Deployment complete on all instances.")
