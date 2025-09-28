#!/usr/bin/env python3
import json, os, sys, itertools
import boto3

REGION   = os.getenv("AWS_REGION", "us-east-1")
KEY_NAME = os.getenv("AWS_KEY_NAME")
SG_ID    = os.getenv("AWS_INSTANCE_SG_ID")
AMI_ID   = os.getenv("AWS_AMI_ID", "")
SUBNETS  = os.getenv("AWS_SUBNET_IDS", "").split(",") if os.getenv("AWS_SUBNET_IDS") else []

if not (KEY_NAME and SG_ID and SUBNETS and len(SUBNETS) >= 2):
    sys.exit("Missing one of: AWS_KEY_NAME, AWS_INSTANCE_SG_ID, AWS_SUBNET_IDS(2+)")