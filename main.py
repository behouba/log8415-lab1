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

