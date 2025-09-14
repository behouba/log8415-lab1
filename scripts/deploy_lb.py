#!/usr/bin/env python3
import json, os, sys, subprocess, base64, time

KEY_PATH = os.getenv("AWS_KEY_PATH")
if not KEY_PATH:
    sys.exit("Missing AWS_KEY_PATH")

SSH_OPTS = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
    "-o", "ServerAliveInterval=15", "-o", "ConnectTimeout=30"
]

def ssh(host, cmd):
    return subprocess.run(
        SSH_OPTS + ["-i", KEY_PATH, f"ubuntu@{host}", f"bash -lc '{cmd}'"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True
    )

def scp_path(host, local_path):
    subprocess.run(
        ["scp", "-o", "StrictHostKeyChecking=no", "-i", KEY_PATH, "-r", local_path, f"ubuntu@{host}:~"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True
    )

with open("artifacts/instances.json") as f:
    instances = json.load(f)
with open("artifacts/lb.json") as f:
    lb = json.load(f)

print("Waiting 60 seconds for the new instance to initialize its SSH service...")
time.sleep(60)
HOST = lb["public_ip"]
targets = {
    "cluster1": [f"http://{i['private_ip']}:8000/cluster1" for i in instances if i.get("cluster")=="cluster1"],
    "cluster2": [f"http://{i['private_ip']}:8000/cluster2" for i in instances if i.get("cluster")=="cluster2"],
}

print(f"Deploying LB to {HOST}...")

try:
    print(f"[{HOST}] Waiting for cloud-init to finish (max 2 mins)...")
    ssh(HOST, "sudo cloud-init status --wait")

    print(f"[{HOST}] Installing Python dependencies...")
    ssh(HOST, "sudo apt-get update -y && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-pip")
    ssh(HOST, "python3 -m pip install --upgrade pip fastapi uvicorn httpx")

    print(f"[{HOST}] Copying lb/ source code...")
    scp_path(HOST, "lb")

    print(f"[{HOST}] Writing /etc/lb/targets.json configuration...")
    targets_b64 = base64.b64encode(json.dumps(targets).encode("utf-8")).decode("ascii")
    ssh(HOST, f"sudo mkdir -p /etc/lb && sudo touch /etc/lb/targets.json && echo '{targets_b64}' | base64 -d | sudo tee /etc/lb/targets.json >/dev/null")

  

    print(f"[{HOST}] Creating and starting systemd service for the LB...")
    SERVICE_TPL = """[Unit]
Description=Custom Latency-based LB
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/lb
Environment=LB_CONFIG=/etc/lb/targets.json
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
ExecStart=/usr/bin/python3 -m uvicorn lb:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
    unit_b64 = base64.b64encode(SERVICE_TPL.encode("utf-8")).decode("ascii")
    ssh(
        HOST,
        f"echo '{unit_b64}' | base64 -d | sudo tee /etc/systemd/system/lb.service >/dev/null && "
        "sudo systemctl daemon-reload && "
        "sudo systemctl enable --now lb"
    )

    print(f"[{HOST}] Waiting for LB service to become ready...")
    ssh(
        HOST,
        "for i in $(seq 1 30); do "
        "curl -s -o /dev/null http://127.0.0.1/status && echo 'READY' && exit 0; "
        "sleep 1; "
        "done; echo 'NOT READY'; exit 1"
    )

    print("✅ LB deployed.")

except subprocess.CalledProcessError as e:
    print(f"\n❌ FAILED during LB deployment on host {HOST}.")
    print(f"  - Command exited with code: {e.returncode}")
    print(f"  - Output:\n{e.stdout}")
    sys.exit(1)
