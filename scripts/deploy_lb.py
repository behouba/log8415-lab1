#!/usr/bin/env python3
import json, os, sys, subprocess, base64

KEY_PATH = os.getenv("AWS_KEY_PATH")
if not KEY_PATH:
    sys.exit("Missing AWS_KEY_PATH")

SSH_OPTS = [
    "ssh",
    "-o","StrictHostKeyChecking=no",
    "-o","BatchMode=yes",
    "-o","ServerAliveInterval=15",
    "-o","ServerAliveCountMax=3",
    "-o","ConnectTimeout=20",
    "-o","ConnectionAttempts=10",
]

def ssh(host, cmd):
    """Run a remote command via non-interactive bash."""
    return subprocess.run(
        SSH_OPTS + ["-i", KEY_PATH, f"ubuntu@{host}", f"bash -lc '{cmd}'"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

def scp_path(host, local, remote_home="~"):
    return subprocess.run(
        ["scp","-o","StrictHostKeyChecking=no","-i",KEY_PATH,"-r",local,f"ubuntu@{host}:{remote_home}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

# -------- targets & host --------
with open("artifacts/instances.json") as f:
    instances = json.load(f)

targets = {
    "cluster1": [f"http://{i['private_ip']}:8000/cluster1" for i in instances if i.get("cluster")=="cluster1"],
    "cluster2": [f"http://{i['private_ip']}:8000/cluster2" for i in instances if i.get("cluster")=="cluster2"],
}

with open("artifacts/lb.json") as f:
    lb = json.load(f)
HOST = lb["public_ip"]

print(f"Deploying LB to {HOST} …")

# -------- NO APT, NO CLOUD-INIT WAITS --------
# 1) Make sure Python is there; bootstrap pip without apt; install deps.
bootstrap = (
    "set -eu;"
    "python3 -V || (echo 'python3 missing' >&2; exit 1); "
    # ensurepip is bundled with CPython; harmless if already installed
    "python3 -m ensurepip --upgrade || true; "
    "python3 -m pip install --upgrade pip || true; "
    "python3 -m pip install -q fastapi uvicorn httpx || (python3 -m pip install fastapi uvicorn httpx)"
)
print(f"[{HOST}] $ bootstrap python/pip/deps (no apt)")
r = ssh(HOST, bootstrap)
if r.returncode != 0:
    print(r.stdout); sys.exit(f"[{HOST}] Failed to bootstrap Python/pip")

# 2) Place code & config
print(f"[{HOST}] Copying lb/ …")
r = scp_path(HOST, "lb")
if r.returncode != 0:
    print(r.stdout); sys.exit(f"[{HOST}] SCP failed (lb)")

print(f"[{HOST}] Writing /etc/lb/targets.json")
targets_b64 = base64.b64encode(json.dumps(targets).encode("utf-8")).decode("ascii")
r = ssh(HOST, f"sudo mkdir -p /etc/lb && echo '{targets_b64}' | base64 -d | sudo tee /etc/lb/targets.json >/dev/null")
if r.returncode != 0:
    print(r.stdout); sys.exit(f"[{HOST}] Failed writing targets.json")

# 3) systemd unit (give CAP_NET_BIND_SERVICE so non-root can bind :80)
SERVICE_PATH = "/etc/systemd/system/lb.service"
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
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
"""
unit_b64 = base64.b64encode(SERVICE_TPL.encode("utf-8")).decode("ascii")
cmd = (
    f"echo '{unit_b64}' | base64 -d | sudo tee {SERVICE_PATH} >/dev/null && "
    "sudo systemctl daemon-reload && "
    "sudo systemctl enable --now lb && "
    "sudo systemctl restart lb || true"
)
print(f"[{HOST}] install systemd unit")
r = ssh(HOST, cmd)
if r.returncode != 0:
    print(r.stdout); sys.exit(f"[{HOST}] Failed to install/start lb.service")

# 4) Readiness check with Python (no curl)
ready = (
    "set -e; "
    "for i in $(seq 1 45); do "
    "  python3 - <<'PY'\n"
    "import sys, urllib.request\n"
    "try:\n"
    "    with urllib.request.urlopen('http://127.0.0.1/status', timeout=2) as r:\n"
    "        sys.exit(0 if r.getcode()==200 else 1)\n"
    "except Exception:\n"
    "    sys.exit(1)\n"
    "PY\n"
    "  && echo READY && exit 0 || true; "
    "  sleep 1; "
    "done; "
    "echo NOT_READY; "
    "systemctl --no-pager --full status lb || true; "
    "journalctl -u lb -n 120 --no-pager || true; "
    "exit 1"
)
print(f"[{HOST}] waiting for readiness …")
r = ssh(HOST, ready)
print(r.stdout, end="")
if r.returncode != 0:
    sys.exit("[LB] Not ready")

print("✅ LB deployed.")
print(f"🌐 Test:  http://{HOST}/cluster1   and   http://{HOST}/cluster2")
