"""Deploy the Naadi API + web app to the existing server (naadi-server, ap-south-1) with HTTPS.

1. Elastic IP for a stable address; security group opens 80/443 only.
2. Uploads code, model artefacts and the built web app (web/dist) to the private bucket.
3. On the server (via SSM): sync files, install Python deps and Caddy, systemd unit `naadi-api`
   (uvicorn on 127.0.0.1:8000, root path /api), Caddy on <ip>.sslip.io with a Let's Encrypt certificate:
       https://<ip>.sslip.io/        web app
       https://<ip>.sslip.io/api/    API (docs at /api/docs)
   and restarts the feed recorder so it publishes data/live/latest.pb for the live engine.
Usage: python infra/deploy_api.py [--code-only]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
REGION = "ap-south-1"
IID = "i-02e366d4128da827b"
CADDY = "https://github.com/caddyserver/caddy/releases/download/v2.10.2/caddy_2.10.2_linux_arm64.tar.gz"
MODEL_FILES = ["data/processed/model/network_prod/network.npz", "data/processed/model/network_prod/network_meta.json",
               "data/processed/model/grid_oct_all.parquet", "data/processed/model/tables/oct_all/geom.parquet",
               "data/processed/model/tables/oct_all/cell_h.parquet", "data/processed/model/intervals.json",
               "data/processed/model/route_ac.json", "validation/results/eta_oct.json", "validation/results/summary.json"]


def ssm_run(s, cmds, timeout=900):
    ssm = s.client("ssm")
    cid = ssm.send_command(InstanceIds=[IID], DocumentName="AWS-RunShellScript",
                           Parameters={"commands": cmds, "executionTimeout": [str(timeout)]})["Command"]["CommandId"]
    t0 = time.time()
    while True:
        time.sleep(5)
        r = ssm.get_command_invocation(CommandId=cid, InstanceId=IID)
        if r["Status"] not in ("Pending", "InProgress", "Delayed") or time.time() - t0 > timeout + 60:
            return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-only", action="store_true")
    a = ap.parse_args()
    s = boto3.Session(profile_name="naadi", region_name=REGION)
    acct = s.client("sts").get_caller_identity()["Account"]
    bucket = f"naadi-data-{acct}"
    ec2, s3 = s.client("ec2"), s.client("s3")
    inst = ec2.describe_instances(InstanceIds=[IID])["Reservations"][0]["Instances"][0]
    addrs = ec2.describe_addresses(Filters=[{"Name": "tag:Project", "Values": ["naadi"]}])["Addresses"]
    if not addrs:
        alloc = ec2.allocate_address(Domain="vpc", TagSpecifications=[{"ResourceType": "elastic-ip", "Tags": [{"Key": "Project", "Value": "naadi"}]}])
        ec2.associate_address(AllocationId=alloc["AllocationId"], InstanceId=IID)
        ip = alloc["PublicIp"]
    else:
        ip = addrs[0]["PublicIp"]
        if addrs[0].get("InstanceId") != IID:
            ec2.associate_address(AllocationId=addrs[0]["AllocationId"], InstanceId=IID)
    host = ip.replace(".", "-") + ".sslip.io"
    sg = inst["SecurityGroups"][0]["GroupId"]
    for port in (80, 443):
        try:
            ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[{"IpProtocol": "tcp", "FromPort": port, "ToPort": port,
                                                  "IpRanges": [{"CidrIp": "0.0.0.0/0"}], "Ipv6Ranges": [{"CidrIpv6": "::/0"}]}])
        except ec2.exceptions.ClientError as e:
            if "Duplicate" not in str(e):
                raise
    print("host", host)
    files = [p for p in (ROOT / "naadi").glob("*.py")] + [ROOT / "scripts" / "record_feed.py", ROOT / "infra" / "requirements-api.txt"]
    for f in files:
        s3.upload_file(str(f), bucket, f"code/{f.relative_to(ROOT).as_posix()}")
    for f in (ROOT / "web" / "dist").rglob("*"):
        if f.is_file():
            ct = {".html": "text/html", ".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml"}.get(f.suffix, "application/octet-stream")
            s3.upload_file(str(f), bucket, f"web/{f.relative_to(ROOT / 'web' / 'dist').as_posix()}", ExtraArgs={"ContentType": ct})
    if not a.code_only:
        for rel in MODEL_FILES:
            p = ROOT / rel
            if p.exists():
                s3.upload_file(str(p), bucket, f"artefacts/{rel}")
            else:
                print("missing (skipped):", rel)
    caddyfile = f"""{host} {{
    encode zstd gzip
    handle_path /api/* {{
        reverse_proxy 127.0.0.1:8000
    }}
    handle {{
        root * /opt/naadi/web
        try_files {{path}} /index.html
        file_server
    }}
    header /assets/* Cache-Control "public, max-age=31536000, immutable"
}}
"""
    unit = """[Unit]
Description=Naadi API
After=network-online.target

[Service]
User=naadi
WorkingDirectory=/opt/naadi
Environment=NAADI_ROOT=/opt/naadi
Environment=NUMBA_CACHE_DIR=/opt/naadi/.numba
ExecStart=/opt/naadi/.venv/bin/uvicorn naadi.api:app --host 127.0.0.1 --port 8000 --root-path /api --workers 1
Restart=always
RestartSec=5
MemoryMax=1200M

[Install]
WantedBy=multi-user.target
"""
    cmds = [
        "set -e",
        f"aws s3 sync s3://{bucket}/code/ /opt/naadi/ --region {REGION} --only-show-errors",
        f"aws s3 sync s3://{bucket}/web/ /opt/naadi/web/ --region {REGION} --only-show-errors --delete",
        f"aws s3 sync s3://{bucket}/artefacts/ /opt/naadi/ --region {REGION} --only-show-errors",
        "/opt/naadi/.venv/bin/pip install --quiet -r /opt/naadi/infra/requirements-api.txt",
        f"test -x /usr/local/bin/caddy || (curl -sL {CADDY} -o /tmp/caddy.tgz && tar -xzf /tmp/caddy.tgz -C /usr/local/bin caddy && chmod 755 /usr/local/bin/caddy)",
        "id caddy || useradd --system --home /var/lib/caddy --create-home --shell /sbin/nologin caddy",
        "mkdir -p /etc/caddy /opt/naadi/.numba /opt/naadi/data/live",
        "cat > /etc/caddy/Caddyfile <<'EOF'\n" + caddyfile + "EOF",
        "cat > /etc/systemd/system/caddy.service <<'EOF'\n[Unit]\nDescription=Caddy\nAfter=network-online.target\n\n[Service]\nUser=caddy\n"
        "ExecStart=/usr/local/bin/caddy run --config /etc/caddy/Caddyfile\nExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile\n"
        "AmbientCapabilities=CAP_NET_BIND_SERVICE\nRestart=always\n\n[Install]\nWantedBy=multi-user.target\nEOF",
        "cat > /etc/systemd/system/naadi-api.service <<'EOF'\n" + unit + "EOF",
        "chown -R naadi:naadi /opt/naadi",
        "systemctl daemon-reload",
        "systemctl restart naadi-feed",
        "systemctl enable --now naadi-api caddy",
        "systemctl restart naadi-api",
        "sleep 25",
        "systemctl reload caddy || systemctl restart caddy",
        "curl -s http://127.0.0.1:8000/health | head -c 400; echo",
        "ls -la /opt/naadi/data/live/ | tail -2",
        "free -m | head -2",
    ]
    r = ssm_run(s, cmds)
    print(r["Status"])
    print(r["StandardOutputContent"][-2500:])
    print(r["StandardErrorContent"][-1500:])
    print(f"web: https://{host}/   api: https://{host}/api/docs")


if __name__ == "__main__":
    main()
