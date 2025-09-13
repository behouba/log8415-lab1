# import des bibliothèques nécessaires
import boto3
import botocore.exceptions

# --- Paramètres communs avec les variables d'environnement ---
AMI_ID = "ami-00ca32bbc84273381"
KEY_NAME = "vockey"
SECURITY_GROUP_NAME = "default"
REGION_NAME = "us-east-1"

# ajout d'un script pour mise a jour et installation de python dans chaque instance
user_data_script = '''#!/bin/bash
yum update -y
yum install -y python3 python3-pip
'''

# --- Initialisation des clients Boto3 ---
try:
    ec2_client = boto3.client("ec2", region_name=REGION_NAME)
    ec2_resource = boto3.resource("ec2", region_name=REGION_NAME)
    print("Clients Boto3 initialisés avec succès.")
except botocore.exceptions.NoCredentialsError:
    print("Erreur: Les identifiants AWS ne sont pas configurés.")
    exit(1)



