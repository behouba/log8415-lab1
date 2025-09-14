# LOG8415E – Lab 1 (Ubuntu-only, end-to-end)

This repo automates:
- **5× `t2.micro`** (cluster2) + **4× `t2.large`** (cluster1) on **Ubuntu 22.04**
- FastAPI app deployment (per assignment)
- ALB with **/cluster1** and **/cluster2** path rules
- Outputs:
  - `artifacts/instances.json`
  - `artifacts/alb.json` (DNS)

## Prereqs
- AWS account/role with EC2 + ELBv2 permissions
- AWS CLI configured (`aws sts get-caller-identity` works)
- Python 3.7+ (3.8+ recommended)

## 0) Bootstrap once
```bash
chmod +x scripts/bootstrap_env.sh
scripts/bootstrap_env.sh
set -a; source .env; set +a


eee_W_5029605@runweb188000:~/log8415-lab1$ set -a; source .env; set +a
eee_W_5029605@runweb188000:~/log8415-lab1$ aws sts get-caller-identity
{
    "UserId": "AROAXYKJVIMRUG7LGU3D3:user4389775=B__houba_Manass___Kouame",
    "Account": "533267301155",
    "Arn": "arn:aws:sts::533267301155:assumed-role/voclabs/user4389775=B__houba_Manass___Kouame"
}
eee_W_5029605@runweb188000:~/log8415-lab1$ echo "Region: $AWS_REGION"
Region: us-east-1
eee_W_5029605@runweb188000:~/log8415-lab1$ 

# reload env
cd ~/log8415-lab1
set -a; source .env; set +a

# get your current public IP
MYIP=$(curl -s https://checkip.amazonaws.com)

# allow SSH 22 from your current IP
aws ec2 authorize-security-group-ingress \
  --group-id "$AWS_INSTANCE_SG_ID" \
  --protocol tcp --port 22 --cidr ${MYIP}/32 \
  --region "$AWS_REGION"

# (optional) see the rules, to confirm the new /32 was added
aws ec2 describe-security-groups --group-ids "$AWS_INSTANCE_SG_ID" \
  --region "$AWS_REGION" --query 'SecurityGroups[0].IpPermissions'









  # Python upgrate
  # Install pyenv in home
curl https://pyenv.run | bash

# Add to shell init (if using bash)
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"

# Install python 3.11 locally
pyenv install 3.11.9
pyenv local 3.11.9

