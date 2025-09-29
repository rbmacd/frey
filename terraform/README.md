# Frey EKS Terraform Configuration

This directory contains Terraform configuration to deploy a basic EKS cluster on AWS for running Frey services.

## Prerequisites

- AWS account with appropriate permissions
- AWS CLI installed and configured with credentials
- Terraform >= 1.0
- kubectl installed

## AWS Permissions Required

Your AWS user/role needs permissions to create:

- VPC, subnets, route tables, internet gateways, NAT gateways
- EKS clusters and node groups
- IAM roles and policies
- EC2 instances and security groups

## Quick Start

### 1. Initialize Terraform

```bash
terraform init
```

### 2. Review the deployment plan

```bash
terraform plan
```

### 3. Deploy the cluster

```bash
terraform apply
```

Type `yes` when prompted to confirm.

### 4. Configure kubectl

```bash
aws eks update-kubeconfig --region us-east-1 --name frey-eks-cluster
```

### 5. Verify cluster access

```bash
kubectl get nodes
```

You should see 3 nodes in Ready state.

## Deploying Frey Services

After the cluster is running, deploy the Frey services using the Helm charts from the main repository:

```bash
# Navigate back to repository root
cd ..

# Install external-secrets operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace \
  -f services/external-secrets/frey-external_secrets-values.yaml

# Install NetBox
kubectl create namespace netbox
helm install netbox oci://ghcr.io/netbox-community/netbox-chart/netbox \
  --namespace netbox -f services/netbox/frey-netbox-values.yaml

# Install AWX
helm repo add awx-operator https://ansible-community.github.io/awx-operator-helm
kubectl create namespace awx-operator
helm install awx-operator awx-operator/awx-operator \
  --namespace awx-operator -f services/awx/frey-awx-values.yaml
```

**Note:** The current Vault configuration in `frey_bootstrap.sh` is designed for local development. For AWS deployments, you'll need to configure secrets management separately (AWS Secrets Manager or Parameter Store integration is planned for future releases).

## Configuration

Edit `variables.tf` to customize:

- AWS region
- Cluster name
- Node instance type
- Number of nodes

Or override variables during apply:

```bash
terraform apply -var="aws_region=us-west-2" -var="node_instance_type=t3.medium"
```

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

Type `yes` when prompted. This will delete the cluster and all associated AWS resources.