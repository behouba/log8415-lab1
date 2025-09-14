#!/usr/bin/env bash
set -euo pipefail

err() { echo "ERROR: $*" >&2; exit 1; }
region_from_cli() { aws configure get region || true; }

authorize_cidr() {
  local sg="$1" port="$2" cidr="$3" proto="${4:-tcp}"
  local out rc
  set +e
  out=$(aws ec2 authorize-security-group-ingress \
        --group-id "$sg" --protocol "$proto" --port "$port" \
        --cidr "$cidr" --region "$AWS_REGION" 2>&1)
  rc=$?
  set -e
  [[ $rc -eq 0 || "$out" == *"InvalidPermission.Duplicate"* ]] || { echo "$out" >&2; return $rc; }
}

ensure_sg() {
  local name="$1" desc="$2"
  local id
  id=$(aws ec2 describe-security-groups \
        --filters Name=vpc-id,Values="$AWS_VPC_ID" Name=group-name,Values="$name" \
        --query 'SecurityGroups[0].GroupId' --output text --region "$AWS_REGION" || true)
  if [[ -n "${id}" && "${id}" != "None" ]]; then
    echo "$id"; return 0
  fi
  aws ec2 create-security-group \
    --group-name "$name" --description "$desc" \
    --vpc-id "$AWS_VPC_ID" --region "$AWS_REGION" \
    --query 'GroupId' --output text
}

ensure_key_pair() {
  local name="${AWS_KEY_NAME:-}"
  local path="${AWS_KEY_PATH:-}"
  if [[ -z "$name" ]]; then
    name="lab-key-$(date +%s)"
    export AWS_KEY_NAME="$name"
  fi
  if [[ -z "$path" ]]; then
    path="$HOME/.ssh/${name}.pem"
    export AWS_KEY_PATH="$path"
  fi
  local exists
  set +e
  exists=$(aws ec2 describe-key-pairs --key-names "$name" \
            --query 'KeyPairs[0].KeyName' --output text --region "$AWS_REGION" 2>/dev/null)
  set -e
  if [[ "$exists" == "$name" ]]; then
    [[ -f "$path" ]] && chmod 600 "$path" || true
    echo "$name"; return 0
  fi
  mkdir -p "$(dirname "$path")"
  aws ec2 create-key-pair --key-name "$name" \
    --query 'KeyMaterial' --output text --region "$AWS_REGION" > "$path"
  chmod 600 "$path"
  echo "$name"
}

# ---- region ----
: "${AWS_REGION:=$(region_from_cli)}"
: "${AWS_REGION:=us-east-1}"
echo "Using region: $AWS_REGION"

# ---- VPC ----
if [[ -z "${AWS_VPC_ID:-}" || "${AWS_VPC_ID}" == "None" ]]; then
  AWS_VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION")
  [[ "$AWS_VPC_ID" != "None" ]] || err "No default VPC in $AWS_REGION. Set AWS_VPC_ID."
fi
echo "VPC: $AWS_VPC_ID"

# ---- Subnets (pick two deterministically by AZ) ----
if [[ -z "${AWS_SUBNET_IDS:-}" ]]; then
  read -r SUB1 SUB2 < <(aws ec2 describe-subnets \
     --filters Name=vpc-id,Values="$AWS_VPC_ID" \
     --query 'sort_by(Subnets,&AvailabilityZone)[].SubnetId' \
     --output text --region "$AWS_REGION" | awk '{print $1, $2}')
  [[ -n "${SUB1:-}" && -n "${SUB2:-}" ]] || err "Need at least two subnets in VPC $AWS_VPC_ID."
  AWS_SUBNET_IDS="${SUB1},${SUB2}"
fi
echo "Subnets: $AWS_SUBNET_IDS"

# ---- Instance Security Group (idempotent) ----
AWS_INSTANCE_SG_ID=${AWS_INSTANCE_SG_ID:-$(ensure_sg "lab-instances" "Instances SG")}
echo "Instance SG: $AWS_INSTANCE_SG_ID"

# SSH/22 from your IP
MYIP=$(curl -s https://checkip.amazonaws.com | tr -d '\r' || true)
if [[ -n "$MYIP" ]]; then
  authorize_cidr "$AWS_INSTANCE_SG_ID" 22 "${MYIP}/32"
else
  echo "WARN: Could not detect public IP; skipping SSH rule."
fi
# NOTE: port 8000 ingress from the LB SG is added later by scripts/provision_lb.py

# ---- Key pair ----
ensure_key_pair >/dev/null
echo "Key pair: $AWS_KEY_NAME ($AWS_KEY_PATH)"

# ---- Ubuntu 22.04 AMI via SSM (gp3 fallback to gp2) ----
if [[ -z "${AWS_AMI_ID:-}" ]]; then
  set +e
  AWS_AMI_ID=$(aws ssm get-parameter \
    --name "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp3/ami-id" \
    --query 'Parameter.Value' --output text --region "$AWS_REGION")
  if [[ -z "$AWS_AMI_ID" || "$AWS_AMI_ID" == "None" ]]; then
    AWS_AMI_ID=$(aws ssm get-parameter \
      --name "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id" \
      --query 'Parameter.Value' --output text --region "$AWS_REGION")
  fi
  set -e
fi
[[ -n "$AWS_AMI_ID" && "$AWS_AMI_ID" != "None" ]] || err "Could not resolve Ubuntu 22.04 AMI."
echo "Ubuntu AMI: $AWS_AMI_ID"

# ---- write .env ----
cat > .env <<EOF
AWS_REGION=$AWS_REGION
AWS_VPC_ID=$AWS_VPC_ID
AWS_SUBNET_IDS=$AWS_SUBNET_IDS
AWS_INSTANCE_SG_ID=$AWS_INSTANCE_SG_ID
AWS_KEY_NAME=$AWS_KEY_NAME
AWS_KEY_PATH=$AWS_KEY_PATH
AWS_AMI_ID=$AWS_AMI_ID
EOF

echo "✅ Wrote .env. Load it with:  set -a; source .env; set +a"
