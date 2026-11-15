"""One-time AWS bootstrap, run with the root key (profile `naadi`), then never again.

Creates:
  * IAM user `naadi-deploy` limited to Mumbai (ap-south-1): small Graviton EC2 only,
    S3 buckets named naadi-*, SSM parameters under /naadi/, Session Manager, budgets and cost read.
  * IAM role + instance profile `naadi-server-role` for the server: write to the data bucket,
    read /naadi/ parameters, and Session Manager access (no SSH, no open ports).
  * Private S3 bucket `naadi-data-<account>` (public access blocked, encrypted).
  * AWS Budget `naadi-hosting-cap`: US$20 for 2026 on hosting services only, before credits,
    with email alerts at 50/75/90% actual and 100% forecast.
Then it creates an access key for `naadi-deploy`, writes it to ~/.aws/credentials as profile
`naadi`, and removes the root key from that file.

Usage: .venv\\Scripts\\python.exe infra\\bootstrap_iam.py <alert-email>
"""
from __future__ import annotations

import configparser
import json
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "ap-south-1"
USER = "naadi-deploy"
ROLE = "naadi-server-role"
BUDGET = "naadi-hosting-cap"
HOSTING_SERVICES = [
    "Amazon Elastic Compute Cloud - Compute", "EC2 - Other", "Amazon Simple Storage Service",
    "Amazon Virtual Private Cloud", "AmazonCloudWatch", "AWS Systems Manager",
]


def deploy_policy(acct: str) -> dict:
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "EC2InMumbai", "Effect": "Allow", "Action": "ec2:*", "Resource": "*",
         "Condition": {"StringEquals": {"aws:RequestedRegion": REGION}}},
        {"Sid": "OnlySmallGraviton", "Effect": "Deny", "Action": "ec2:RunInstances",
         "Resource": "arn:aws:ec2:*:*:instance/*",
         "Condition": {"StringNotEquals": {"ec2:InstanceType": ["t4g.nano", "t4g.micro", "t4g.small", "t4g.medium"]}}},
        {"Sid": "SmallDisksOnly", "Effect": "Deny", "Action": ["ec2:RunInstances", "ec2:CreateVolume", "ec2:ModifyVolume"],
         "Resource": "arn:aws:ec2:*:*:volume/*", "Condition": {"NumericGreaterThan": {"ec2:VolumeSize": "40"}}},
        {"Sid": "NoCostlyNetworkingOrCommitments", "Effect": "Deny", "Action": [
            "ec2:CreateNatGateway", "ec2:CreateVpnConnection", "ec2:CreateVpnGateway", "ec2:CreateTransitGateway",
            "ec2:CreateClientVpnEndpoint", "ec2:CreateVpcEndpoint", "ec2:PurchaseReservedInstancesOffering",
            "ec2:AllocateHosts", "ec2:PurchaseHostReservation", "ec2:CreateCapacityReservation",
            "ec2:RequestSpotFleet", "ec2:CreateFleet", "ec2:ModifyInstanceCreditSpecification"], "Resource": "*"},
        {"Sid": "S3ProjectBuckets", "Effect": "Allow", "Action": "s3:*",
         "Resource": ["arn:aws:s3:::naadi-*", "arn:aws:s3:::naadi-*/*"]},
        {"Sid": "S3ListAll", "Effect": "Allow", "Action": ["s3:ListAllMyBuckets", "s3:GetBucketLocation"], "Resource": "*"},
        {"Sid": "ProjectParameters", "Effect": "Allow",
         "Action": ["ssm:PutParameter", "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath",
                    "ssm:DeleteParameter", "ssm:AddTagsToResource"],
         "Resource": f"arn:aws:ssm:{REGION}:{acct}:parameter/naadi/*"},
        {"Sid": "PublicAmiParameters", "Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:GetParameters"],
         "Resource": f"arn:aws:ssm:{REGION}::parameter/aws/service/*"},
        {"Sid": "SessionManagerAndCommands", "Effect": "Allow",
         "Action": ["ssm:DescribeParameters", "ssm:SendCommand", "ssm:GetCommandInvocation", "ssm:ListCommands",
                    "ssm:ListCommandInvocations", "ssm:DescribeInstanceInformation", "ssm:StartSession",
                    "ssm:TerminateSession", "ssm:ResumeSession"], "Resource": "*",
         "Condition": {"StringEquals": {"aws:RequestedRegion": REGION}}},
        {"Sid": "PassServerRoleOnly", "Effect": "Allow", "Action": "iam:PassRole",
         "Resource": f"arn:aws:iam::{acct}:role/{ROLE}"},
        {"Sid": "ReadOwnIam", "Effect": "Allow",
         "Action": ["iam:GetRole", "iam:GetInstanceProfile", "iam:ListInstanceProfiles"], "Resource": "*"},
        {"Sid": "CostAndMonitoring", "Effect": "Allow",
         "Action": ["budgets:ViewBudget", "budgets:DescribeBudgets", "ce:GetCostAndUsage", "ce:GetCostForecast",
                    "cloudwatch:*", "logs:*"], "Resource": "*"},
    ]}


def server_policy(bucket: str, acct: str) -> dict:
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "DataBucket", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket",
                                                             "s3:GetBucketLocation", "s3:AbortMultipartUpload"],
         "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"]},
        {"Sid": "ReadSecrets", "Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:GetParameters",
                                                             "ssm:GetParametersByPath"],
         "Resource": f"arn:aws:ssm:{REGION}:{acct}:parameter/naadi/*"},
        {"Sid": "Metrics", "Effect": "Allow", "Action": "cloudwatch:PutMetricData", "Resource": "*"},
    ]}


def ensure(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("EntityAlreadyExists", "BucketAlreadyOwnedByYou", "DuplicateRecordException",
                                           "LimitExceeded"):
            print(f"  (exists) {fn.__name__}")
            return None
        raise


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: bootstrap_iam.py <alert-email>")
    email = sys.argv[1]
    s = boto3.Session(profile_name="naadi", region_name=REGION)
    acct_arn = s.client("sts").get_caller_identity()
    acct = acct_arn["Account"]
    if not acct_arn["Arn"].endswith(":root"):
        sys.exit("profile naadi is no longer the root key; bootstrap already done")
    iam, s3 = s.client("iam"), s.client("s3")
    bucket = f"naadi-data-{acct}"

    print("1. data bucket")
    ensure(s3.create_bucket, Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}]})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": "Project", "Value": "naadi"}]})

    print("2. server role and instance profile")
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"},
                                                      "Action": "sts:AssumeRole"}]}
    ensure(iam.create_role, RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust),
           Description="Naadi server: data bucket, /naadi parameters, Session Manager",
           Tags=[{"Key": "Project", "Value": "naadi"}])
    iam.attach_role_policy(RoleName=ROLE, PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore")
    iam.put_role_policy(RoleName=ROLE, PolicyName="naadi-server", PolicyDocument=json.dumps(server_policy(bucket, acct)))
    ensure(iam.create_instance_profile, InstanceProfileName=ROLE)
    try:
        iam.add_role_to_instance_profile(InstanceProfileName=ROLE, RoleName=ROLE)
    except ClientError as e:
        if e.response["Error"]["Code"] != "LimitExceeded":
            raise

    print("3. deploy user")
    ensure(iam.create_user, UserName=USER, Tags=[{"Key": "Project", "Value": "naadi"}])
    # Inline user policies are capped at 2 KB, so use a customer-managed policy (6 KB cap).
    pol_arn = f"arn:aws:iam::{acct}:policy/naadi-deploy"
    try:
        iam.create_policy(PolicyName="naadi-deploy", PolicyDocument=json.dumps(deploy_policy(acct), separators=(",", ":")),
                          Description="Naadi deploy user: Mumbai only, small Graviton EC2, naadi-* S3, /naadi params",
                          Tags=[{"Key": "Project", "Value": "naadi"}])
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        print("  (exists) policy")
    iam.attach_user_policy(UserName=USER, PolicyArn=pol_arn)

    print("4. budget")
    budgets = s.client("budgets")
    ensure(budgets.create_budget, AccountId=acct, Budget={
        "BudgetName": BUDGET, "BudgetLimit": {"Amount": "20", "Unit": "USD"}, "TimeUnit": "ANNUALLY",
        "BudgetType": "COST", "CostFilters": {"Service": HOSTING_SERVICES},
        "CostTypes": {"IncludeCredit": False, "IncludeRefund": False, "IncludeTax": True, "IncludeSubscription": True,
                      "IncludeRecurring": True, "IncludeOtherSubscription": True, "IncludeSupport": True,
                      "IncludeDiscount": True, "IncludeUpfront": True, "UseBlended": False, "UseAmortized": False}},
        NotificationsWithSubscribers=[
            {"Notification": {"NotificationType": t, "ComparisonOperator": "GREATER_THAN", "Threshold": p,
                              "ThresholdType": "PERCENTAGE"},
             "Subscribers": [{"SubscriptionType": "EMAIL", "Address": email}]}
            for t, p in (("ACTUAL", 50), ("ACTUAL", 75), ("ACTUAL", 90), ("FORECASTED", 100))])

    print("5. access key for deploy user, swap credentials file")
    existing = iam.list_access_keys(UserName=USER)["AccessKeyMetadata"]
    if existing:
        sys.exit(f"{USER} already has an access key; not creating another")
    key = iam.create_access_key(UserName=USER)["AccessKey"]
    cred_path = Path.home() / ".aws" / "credentials"
    cp = configparser.ConfigParser()
    cp.read(cred_path)
    cp["naadi"] = {"aws_access_key_id": key["AccessKeyId"], "aws_secret_access_key": key["SecretAccessKey"]}
    with cred_path.open("w") as f:
        cp.write(f)
    time.sleep(12)  # IAM propagation
    me = boto3.Session(profile_name="naadi", region_name=REGION).client("sts").get_caller_identity()["Arn"]
    print(f"   profile naadi now: {me.split(':')[-1]}")
    print(f"   bucket: {bucket}")


if __name__ == "__main__":
    main()
