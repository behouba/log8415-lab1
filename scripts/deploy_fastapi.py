#!/usr/bin/env python3
# Ubuntu-only deploy: copy ./app to each instance, install deps, start uvicorn FROM ~/app,
# and wait until /cluster{1|2} returns 200 to avoid ALB 502s.

import json, os, sys, subprocess, pathlib

KEY_PATH = os.getenv("AWS_KEY_PATH")
if not KEY_PATH:
    sys.exit("Missing AWS_KEY_PATH")

APP_SRC = pathlib.Path("app").resolve()

def ssh(host: str, cmd: str):
    """Run a command on the host via SSH (Ubuntu user), using bash -lc for safe quoting."""
    remote = f"bash -lc '{cmd}'"
    return subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-i", KEY_PATH, f"ubuntu@{host}", remote],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

def scp_dir(host: str, local_path: str, remote_home: str = "~"):
    return subprocess.run(
        ["scp", "-o", "StrictHostKeyChecking=no", "-i", KEY_PATH, "-r", local_path, f"ubuntu@{host}:{remote_home}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

with open("artifacts/instances.json") as f:
    instances = json.load(f)

def deploy_one(host: str, cluster: str):
    print(f"🚀 {host} ({cluster})")

    # 0) Ensure basics (Ubuntu): python3, pip, curl (for readiness check)
    cmds = [
        "sudo apt-get update -y",
        "sudo apt-get install -y python3 python3-pip curl",
        "mkdir -p ~/app && rm -rf ~/app/*",
    ]
    for c in cmds:
        r = ssh(host, c)
        if r.returncode != 0:
            print(r.stdout); sys.exit(f"[{host}] Failed: {c}")

    # 1) Copy app/
    r = scp_dir(host, str(APP_SRC))
    if r.returncode != 0:
        print(r.stdout); sys.exit(f"[{host}] SCP failed")

    # 2) Python deps
    for c in [
        "python3 -m pip install --upgrade pip",
        "python3 -m pip install fastapi uvicorn",
    ]:
        r = ssh(host, c)
        if r.returncode != 0:
            print(r.stdout); sys.exit(f"[{host}] Failed: {c}")

    # 3) Start uvicorn FROM ~/app so `main:app` imports correctly
    r = ssh(host, "pkill -f 'uvicorn .*main:app' || true")
    _ = r  # ignore result

    start_cmd = (
        f"cd ~/app && "
        f"nohup env CLUSTER_NAME={cluster} "
        f"python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 "
        f">/tmp/uvicorn.log 2>&1 &"
    )
    r = ssh(host, start_cmd)
    if r.returncode != 0:
        print(r.stdout); sys.exit(f"[{host}] Failed to start uvicorn")

    # 4) Readiness: wait until /clusterX returns 200
    ready_cmd = (
        f"for i in $(seq 1 30); do "
        f"  code=$(curl -s -o /dev/null -w %{{http_code}} http://127.0.0.1:8000/{cluster}); "
        f"  [ \"$code\" = 200 ] && echo READY && exit 0; "
        f"  sleep 1; "
        f"done; echo NOT_READY; tail -n 120 /tmp/uvicorn.log; exit 1"
    )
    r = ssh(host, ready_cmd)
    print(r.stdout, end="")
    if r.returncode != 0:
        sys.exit(f"[{host}] App did not become ready")

for inst in instances:
    ip = inst.get("public_ip")
    cluster = inst.get("cluster", "")
    if ip and cluster:
        deploy_one(ip, cluster)

print("✅ Deployment complete (Ubuntu). Apps are listening on :8000 and healthy.")
