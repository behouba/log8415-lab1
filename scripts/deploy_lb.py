#!/usr/bin/env python3
import json, os, sys, subprocess, base64, pathlib

REGION = os.getenv("AWS_REGION", "us-east-1")
KEY_PATH = os.getenv("AWS_KEY_PATH")
if not KEY_PATH:
    sys.exit("Missing AWS_KEY_PATH")

SSH_BASE = [
    "ssh",
    "-o","StrictHostKeyChecking=no",
    "-o","BatchMode=yes",
    "-o","ServerAliveInterval=15",
    "-o","ServerAliveCountMax=3",
    "-o","ConnectTimeout=20",
    "-o","ConnectionAttempts=10",
]

def ssh(host, cmd):
    remote = f"bash -lc '{cmd}'"
    return subprocess.run(
        SSH_BASE + ["-i", KEY_PATH, f"ubuntu@{host}", remote],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

def scp_path(host, local, remote_home="~"):
    return subprocess.run(
        ["scp","-o","StrictHostKeyChecking=no","-i",KEY_PATH,"-r",local,f"ubuntu@{host}:{remote_home}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

# Load targets from artifacts/instances.json (use **private** IPs)
with open("artifacts/instances.json") as f:
    instances = json.load(f)
targets = {
    "cluster1": [f"http://{i['private_ip']}:8000/cluster1" for i in instances if i.get("cluster")=="cluster1"],
    "cluster2": [f"http://{i['private_ip']}:8000/cluster2" for i in instances if i.get("cluster")=="cluster2"],
}

with open("artifacts/lb.json") as f:
    lb = json.load(f)
HOST = lb["public_ip"]

print(f"🚀 Deploying LB to {HOST}")

apt_fix = "sudo rm -f /etc/apt/apt.conf.d/50command-not-found || true"
fix_lists = "sudo rm -rf /var/lib/apt/lists/* && sudo mkdir -p /var/lib/apt/lists/partial && sudo apt-get clean"

for c in [
    f"{apt_fix}; sudo apt-get update -y || ({fix_lists} && sudo apt-get update -y) || true",
    "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-pip curl",
    "mkdir -p ~/lb /etc/lb && rm -rf ~/lb/*",
]:
    print(f"[{HOST}] $ {c}")
    r = ssh(HOST, c)
    if r.returncode != 0:
        print(r.stdout); sys.exit(f"[{HOST}] Failed: {c}")

# Copy code
print(f"[{HOST}] Copying lb/ …")
r = scp_path(HOST, "lb")
if r.returncode != 0:
    print(r.stdout); sys.exit(f"[{HOST}] SCP failed (lb)")

# Write targets.json
print(f"[{HOST}] Writing /etc/lb/targets.json")
targets_b64 = base64.b64encode(json.dumps(targets).encode("utf-8")).decode("ascii")
r = ssh(HOST, f"echo '{targets_b64}' | base64 -d | sudo tee /etc/lb/targets.json >/dev/null")
if r.returncode != 0:
    print(r.stdout); sys.exit(f"[{HOST}] Failed writing targets.json")

# Python deps
for c in [
    "python3 -m pip install --upgrade pip",
    "python3 -m pip install fastapi uvicorn httpx",
]:
    print(f"[{HOST}] $ {c}")
    r = ssh(HOST, c)
    if r.returncode != 0:
        print(r.stdout); sys.exit(f"[{HOST}] Failed: {c}")

# systemd unit (port 80, capability to bind low port)
SERVICE_PATH = "/etc/systemd/system/lb.service"
SERVICE_TPL = f"""[Unit]
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
cmd = (
    f"echo '{unit_b64}' | base64 -d | sudo tee {SERVICE_PATH} >/dev/null && "
    "sudo systemctl daemon-reload && "
    "sudo systemctl enable --now lb && "
    "sudo systemctl restart lb"
)
print(f"[{HOST}] install systemd unit")
r = ssh(HOST, cmd)
if r.returncode != 0:
    print(r.stdout); sys.exit(f"[{HOST}] Failed to install/start lb.service")

# Readiness
ready = (
    "for i in $(seq 1 30); do "
    "code=$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1/status); "
    "[ \"$code\" = 200 ] && echo READY && exit 0; sleep 1; done; "
    "echo NOT_READY; systemctl --no-pager --full status lb || true; journalctl -u lb -n 120 --no-pager || true; exit 1"
)
print(f"[{HOST}] waiting for readiness …")
r = ssh(HOST, ready)
print(r.stdout, end="")
if r.returncode != 0:
    sys.exit("[LB] Not ready")

print("✅ LB deployed.")
print(f"🌐 Test:  http://{HOST}/cluster1   and   http://{HOST}/cluster2")
