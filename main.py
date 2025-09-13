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

# --- Creation d'une fonctions de recherche de groupe de securite ---

def get_security_group_id(sg_name):
    """Recherche l'ID d'un groupe de sécurité par son nom."""
    try:
        response = ec2_client.describe_security_groups(GroupNames=[sg_name])
        return response['SecurityGroups'][0]['GroupId']
    except botocore.exceptions.ClientError as e:
        print(f"Erreur : Le groupe de sécurité '{sg_name}' n'a pas été trouvé. {e}")
        return None
    
# --- Creation d'une fonction de creation de cluster ---

def create_cluster(instance_type, count, cluster_name):
    """
    Crée un cluster d'instances EC2, en nommant chaque instance de manière unique
    et en y appliquant un script de User Data.
    """
    print(f"\nTentative de création de {count} instances {instance_type} pour {cluster_name}")
    
    sg_id = get_security_group_id(SECURITY_GROUP_NAME)
    if not sg_id:
        return

    try:
        instances = ec2_resource.create_instances(
            ImageId=AMI_ID,
            InstanceType=instance_type,
            KeyName=KEY_NAME,
            SecurityGroupIds=[sg_id],
            MinCount=count,
            MaxCount=count,
            UserData=user_data_script # Ajout du UserData ici
        )
        
        print(f"Création démarrée. Instances en cours de lancement :")
        instance_ids = [instance.id for instance in instances]
        
        # Attendre que les instances soient en état 'running'
        print("En attente du statut 'running' pour toutes les instances...")
        ec2_resource.meta.client.get_waiter('instance_running').wait(InstanceIds=instance_ids)
        
        # Attribution des noms uniques après le lancement
        for i, instance in enumerate(instances):
            unique_name = f"{cluster_name}-{i + 1}"
            instance.create_tags(
                Tags=[{"Key": "Name", "Value": unique_name}]
            )
            print(f"- ID d'instance : {instance.id}, Nom : {unique_name}")
            
    except botocore.exceptions.ClientError as e:
        print(f"Échec de la création du cluster '{cluster_name}'. Erreur : {e}")


# --- Fonction principale ---
if __name__ == "__main__":
    create_cluster("t2.micro", 4, "Cluster-Micro")
    create_cluster("t2.large", 4, "Cluster-Large")