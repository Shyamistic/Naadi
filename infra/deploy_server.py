"""Launch (or report) the Naadi server in Mumbai with the naadi-deploy profile.

Steps: store API keys in SSM Parameter Store, upload code and the static bus GTFS to the
private bucket, create a security group with no inbound rules, and launch one t4g.small
(standard CPU credits, 20 GB encrypted gp3, IMDSv2, Session Manager access only).

Usage:
  .venv\\Scripts\\python.exe infra\\deploy_server.py launch
  .venv\\Scripts\\python.exe infra\\deploy_server.py status
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
REGION = "ap-south-1"
NAME = "naadi-server"
TYPE = "t4g.small"
TAGS = [{"Key": "Project", "Value": "naadi"}, {"Key": "Name", "Value": NAME}]
CODE = ["scripts/record_feed.py", "scripts/log_eta_baseline.py", "infra/requirements-server.txt"]
GTFS = ROOT / "delhi_buses_static_gtfs_v1-2"


def session():
    return boto3.Session(profile_name="naadi", region_name=REGION)


def running(ec2):
    r = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [NAME]},
                                        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])
    return [i for res in r["Reservations"] for i in res["Instances"]]


def launch() -> None:
    s = session()
    acct = s.client("sts").get_caller_identity()["Account"]
    bucket = f"naadi-data-{acct}"
    ec2, s3, ssm = s.client("ec2"), s.client("s3"), s.client("ssm")
    if running(ec2):
        sys.exit("server already exists; use 'status'")

    env = dotenv_values(ROOT / ".env")
    for k in ("OTD_API_KEY", "ETA_API_KEY"):
        ssm.put_parameter(Name=f"/naadi/{k}", Value=env[k], Type="SecureString", Overwrite=True)
    print("secrets stored in SSM")

    for rel in CODE:
        s3.upload_file(str(ROOT / rel), bucket, f"code/{rel}")
    for f in sorted(GTFS.glob("*.txt")):
        s3.upload_file(str(f), bucket, f"static/delhi_buses_static_gtfs_v1-2/{f.name}")
    print("code and static GTFS uploaded")

    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    sgs = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["naadi-server-sg"]}])["SecurityGroups"]
    if sgs:
        sg = sgs[0]["GroupId"]
    else:
        sg = ec2.create_security_group(GroupName="naadi-server-sg", VpcId=vpc,
                                       Description="Naadi server: no inbound, outbound only",
                                       TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}])["GroupId"]
    ami = ssm.get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64")["Parameter"]["Value"]
    user_data = (ROOT / "infra" / "user_data.sh").read_text().replace("\r\n", "\n").replace("__BUCKET__", bucket)
    inst = ec2.run_instances(
        ImageId=ami, InstanceType=TYPE, MinCount=1, MaxCount=1, UserData=user_data,
        IamInstanceProfile={"Name": "naadi-server-role"}, SecurityGroupIds=[sg],
        CreditSpecification={"CpuCredits": "standard"},
        MetadataOptions={"HttpTokens": "required", "HttpEndpoint": "enabled"},
        BlockDeviceMappings=[{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 20, "VolumeType": "gp3",
                                                                   "Encrypted": True, "DeleteOnTermination": True}}],
        TagSpecifications=[{"ResourceType": "instance", "Tags": TAGS}, {"ResourceType": "volume", "Tags": TAGS}],
    )["Instances"][0]
    print(f"launched {inst['InstanceId']} ({TYPE}, {ami})")


def status() -> None:
    s = session()
    ec2 = s.client("ec2")
    for i in running(ec2):
        print(i["InstanceId"], i["InstanceType"], i["State"]["Name"], i.get("LaunchTime"))
    acct = s.client("sts").get_caller_identity()["Account"]
    objs = s.client("s3").list_objects_v2(Bucket=f"naadi-data-{acct}", Prefix="raw/")
    keys = objs.get("Contents", [])
    print(f"objects under raw/: {len(keys)}" + (f", latest {max(k['LastModified'] for k in keys)}" if keys else ""))


if __name__ == "__main__":
    {"launch": launch, "status": status}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
