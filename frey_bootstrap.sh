#/bin/sh

## Bootstrap script to install services and helm charts for Frey
## Initial iterations are pure bash script, later iterations may move to Ansible or Terraform


### CREDENTIALS ###

# Prompt for Vault root token to use
read -s -p "Enter Vault root token to use: " VAULT_TOKEN
echo

# Prompt for NetBox admin password to store in Vault
read -s -p "Enter NetBox admin password to store in Vault: " NETBOX_ADMIN_PASSWORD
echo

# Prompt for NetBox admin e-mail to store in Vault
read -p "Enter NetBox admin e-mail address to store in Vault: " NETBOX_ADMIN_EMAIL
echo

# Prompt for AWX admin password to store in Vault
read -s -p "Enter AWX admin password to store in Vault: " AWX_ADMIN_PASSWORD
echo

# Generate NetBox API token
export NETBOX_APITOKEN=$(openssl rand -hex 20)


### K3S ###

# Install k3s locally
sudo curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" sh -

# Set KUBECONFIG environment variable to use k3s kubeconfig
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml


### VAULT ###

# Run Vault locally in dev mode 
# Note: This is NOT for production use!
docker run -p 8200:8200 hashicorp/vault server -dev -dev-root-token-id="$VAULT_TOKEN" &

# Wait for vault to be fully up and running
until [ "$(docker ps | grep -P 'vault.+Up')" ]; do echo "Waiting for vault to start..." ; sleep 1; done

# Set Vault environment variables
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="$VAULT_TOKEN"
export VAULT_TOKEN_BASE64=$(echo -n $VAULT_TOKEN | base64)

# Seed vault with initial secrets
vault kv put secret/frey/services/netbox/admin username='admin' password="$NETBOX_ADMIN_PASSWORD" email="$NETBOX_ADMIN_EMAIL" api_token="$NETBOX_APITOKEN"
vault kv put secret/frey/services/awx/admin password="$AWX_ADMIN_PASSWORD"

unset NETBOX_ADMIN_PASSWORD
unset NETBOX_ADMIN_EMAIL
unset NETBOX_APITOKEN
unset AWX_ADMIN_PASSWORD

### EXTERNAL-SECRETS OPERATORS ###

# Must create namespaces first for ExternalSecrets to be installed into properly.  This is annoying but necessary.
kubectl create namespace netbox
kubectl create namespace awx-operator

# Install external secrets operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace -f services/external-secrets/frey-external_secrets-values.yaml

# Wait for external-secrets to be fully up and running before applying SecretStore and ExternalSecret
until [ "$(kubectl get all -n external-secrets | grep -P 'pod/external-secrets-webhook-.+1/1.+Running' && kubectl get all -n external-secrets | grep -P 'pod/external-secrets-\d+.+1/1.+Running')" ]; do echo "Waiting for external-secrets-webhook to start..." ; sleep 3; done

# Capture local IP address for use in ClusterSecretStore
export LOCAL_IP_ADDRESS=$(ip route | grep "^default" | awk '{print $(NF-2)}')

# Deploy SecretStore and ExternalSecret for Frey admin user
envsubst < services/external-secrets/frey-external_secrets_vault_ClusterSecretStore.yaml | kubectl apply -f -
unset VAULT_TOKEN_BASE64
unset LOCAL_IP_ADDRESS
kubectl apply -f services/external-secrets/frey-external_secrets_vault_ExternalSecret_frey-netbox-admin.yaml #NetBox secret
kubectl apply -f services/external-secrets/frey-external_secrets_vault_ExternalSecret_frey-awx-admin.yaml #AWX secret

### NETBOX ###

# Install NetBox using netbox-chart
helm install netbox oci://ghcr.io/netbox-community/netbox-chart/netbox --create-namespace --namespace netbox -f services/netbox/frey-netbox-values.yaml


### AWX ###

# Add repo and install AWX operator using Helm chart
helm repo add awx-operator https://ansible-community.github.io/awx-operator-helm
helm install --namespace awx-operator --create-namespace awx-operator awx-operator/awx-operator -f services/awx/frey-awx-values.yaml
