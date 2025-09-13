# import des bibliothèques nécessaires
import boto3
import botocore.exceptions

# --- Paramètres communs avec les variables d'environnement ---
AMI_ID = "ami-00ca32bbc84273381"
KEY_NAME = "vockey"
SECURITY_GROUP_NAME = "default"
REGION_NAME = "us-east-1"


