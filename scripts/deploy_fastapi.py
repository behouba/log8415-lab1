#!/usr/bin/env python3
import json, os, sys, subprocess, pathlib, base64

KEY_PATH = os.getenv("AWS_KEY_PATH")
if not KEY_PATH:
    sys.exit("Missing AWS_KEY_PATH")

APP_SRC = pathlib.Path("app").resolve()
SSH_USER = "ubuntu"

SSH_BASE = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",
    "-o", "BatchMode=yes",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=3",
    "-o", "ConnectTimeout=20",
    "-o", "ConnectionAttempts=10",
]

def ssh(host, cmd):
    remote = f"bash -lc '{cmd}'"
    return subprocess.run(
        SSH_BASE + ["-i", KEY_PATH, f"{SSH_USER}@{host}", remote],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

def scp_dir(host, local_path, remote_home="~"):
    return subprocess.run(
        ["scp", "-o", "StrictHostKeyChecking=no", "-i", KEY_PATH, "-r",
         local_path, f"{SSH_USER}@{host}:{remote_home}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

with open("artifacts/instances.json") as f:
    instances = json.load(f)

SERVICE_PATH = "/etc/systemd/system/fastapi.service"

SERVICE_TPL = r"""[Unit]
Description=FastAPI (Uvicorn) service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/app
Environment=CLUSTER_NAME={cluster}
ExecStartPre=/bin/bash -lc 'fuser -k 8000/tcp || true'
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=2
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
"""


def deploy_one(host: str, cluster: str):
    print(f"\nDeploying to {host} ({cluster}) as {SSH_USER}")

    apt_prep = "sudo rm -f /etc/apt/apt.conf.d/50command-not-found || true"
    fix_lists = "sudo rm -rf /var/lib/apt/lists/* && sudo mkdir -p /var/lib/apt/lists/partial && sudo apt-get clean"
    apt_update = (
        f"{apt_prep}; "
        "sudo apt-get update -y "
        "|| (" + fix_lists + " && sudo apt-get update -y) "
        "|| true"
    )

    setup_cmds = [
        apt_update,
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-pip curl "
        "|| (" + fix_lists + " && sudo apt-get update -y && "
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-pip curl)",
        "mkdir -p ~/app && rm -rf ~/app/*",
    ]
    for c in setup_cmds:
        print(f"[{host}] $ {c}")
        r = ssh(host, c)
        if r.returncode != 0:
            print(r.stdout); sys.exit(f"[{host}] Failed: {c}")

    print(f"[{host}] Copying app/ …")
    r = scp_dir(host, str(APP_SRC))
    if r.returncode != 0:
        print(r.stdout); sys.exit(f"[{host}] SCP failed")

    for c in [
        "python3 -m pip install --upgrade pip",
        "python3 -m pip install fastapi 'uvicorn[standard]'",
    ]:
        print(f"[{host}] $ {c}")
        r = ssh(host, c)
        if r.returncode != 0:
            print(r.stdout); sys.exit(f"[{host}] Failed: {c}")

    unit_text = SERVICE_TPL.format(cluster=cluster)
    unit_b64  = base64.b64encode(unit_text.encode("utf-8")).decode("ascii")

    write_unit = (
        f"echo '{unit_b64}' | base64 -d | sudo tee {SERVICE_PATH} >/dev/null && "
        "sudo systemctl daemon-reload && "
        "sudo systemctl enable --now fastapi && "
        "sudo systemctl restart fastapi || true"
    )
    print(f"[{host}] $ install systemd unit")
    r = ssh(host, write_unit)
    if r.returncode != 0:
        print(r.stdout); sys.exit(f"[{host}] Failed to install/start systemd unit")

    ready_cmd = (
        f"for i in $(seq 1 60); do "
        f"  code=$(curl -s -o /dev/null -w %{{http_code}} http://127.0.0.1:8000/{cluster}); "
        f"  [ \"$code\" = 200 ] && echo READY && exit 0; "
        f"  sleep 1; "
        f"done; echo NOT_READY;"
        f"sudo systemctl --no-pager --full status fastapi || true; "
        f"journalctl -u fastapi -n 120 --no-pager || true; exit 1"
    )
    print(f"[{host}] Waiting for app to become ready …")
    r = ssh(host, ready_cmd)
    print(r.stdout, end="")
    if r.returncode != 0:
        sys.exit(f"[{host}] App did not become ready")

for inst in instances:
    ip = inst.get("public_ip")
    cluster = inst.get("cluster", "")
    if ip and cluster:
        deploy_one(ip, cluster)

print("✅ Deployment complete!")
