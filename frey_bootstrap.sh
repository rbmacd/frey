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

# Prompt for NetBox ingress hostname to define in helm chart values
read -p "Enter NetBox ingress URL: " NETBOX_URL

# Generate NetBox API token
export NETBOX_APITOKEN=$(openssl rand -hex 20)


# Prompt for AWX admin password to store in Vault
read -s -p "Enter AWX admin password to store in Vault: " AWX_ADMIN_PASSWORD
echo

# Prompt for AWX ingress hostname to define in helm chart values
read -p "Enter AWX ingress URL: " AWX_URL

# Prompt user for SSH AWX network credential username
read -p "Enter username for AWX's network SSH credential type: " AWX_SSH_USERNAME

# Prompt user for SSH AWX network credential password
read -s -p "Enter password for AWX's network password to store in Vault: " AWX_SSH_PASSWORD
echo

# Prompt user for SSH private key location. If no key is provided, generate one.
read -p "Enter the path to your SSH private key to be used as an AWX credential [~/.ssh/ansible_id_rsa]: " SSH_KEY_PATH

# Check if user provided a valid file path
if [ -z "$SSH_KEY_PATH" ]; then
    # Set default path
    SSH_KEY_PATH="$HOME/.ssh/ansible_id_rsa"
    
    # Check if key already exists at default location
    if [ -f "$SSH_KEY_PATH" ]; then
        echo "Found existing SSH key at $SSH_KEY_PATH"
        echo "Using existing private key: $SSH_KEY_PATH"
    else
        echo "No path provided. Generating new SSH key pair..."
        
        # Create .ssh directory if it doesn't exist
        mkdir -p "$HOME/.ssh"
        chmod 700 "$HOME/.ssh"
        
        # Generate SSH key pair
        ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_PATH" -N "" -C "ansible-key"
        
        if [ $? -eq 0 ]; then
            echo "SSH key pair generated successfully!"
            echo "Private key: $SSH_KEY_PATH"
            echo "Public key: ${SSH_KEY_PATH}.pub"
        else
            echo "Error generating SSH key pair"
            exit 1
        fi
    fi
else
    # Expand tilde if present
    SSH_KEY_PATH="${SSH_KEY_PATH/#\~/$HOME}"
    
    # Verify the provided key exists
    if [ -f "$SSH_KEY_PATH" ]; then
        echo "Using SSH private key: $SSH_KEY_PATH"
    else
        echo "Error: File not found at $SSH_KEY_PATH"
        exit 1
    fi
fi

# Prompt user for AWX git URL & branch name.  If no URL is provided, use Frey's github and main.

# Set default values
DEFAULT_REPO_URL="https://github.com/rbmacd/frey.git"
DEFAULT_BRANCH="main"

# Prompt user for GitHub repository URL
read -p "Enter GitHub repository URL to seed AWX [${DEFAULT_REPO_URL}]: " REPO_URL

# Use default if no input provided
if [ -z "$REPO_URL" ]; then
    REPO_URL="$DEFAULT_REPO_URL"
    echo "Using default repository: $REPO_URL"
fi

# Prompt user for branch name
read -p "Enter branch name [${DEFAULT_BRANCH}]: " BRANCH_NAME

# Use default if no input provided
if [ -z "$BRANCH_NAME" ]; then
    BRANCH_NAME="$DEFAULT_BRANCH"
    echo "Using default branch: $BRANCH_NAME"
fi


### K3S ###

echo ""
echo "============================"
echo "Installing k3s locally"
echo "============================"
echo ""

# Install k3s locally
sudo curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" sh -

# Set KUBECONFIG environment variable to use k3s kubeconfig
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml


### VAULT ###

echo ""
echo "============================"
echo "Installing dev vault container"
echo "============================"
echo ""

# Run Vault locally in dev mode 
# Note: This is NOT for production use!
docker run -p 8200:8200 hashicorp/vault server -dev -dev-root-token-id="$VAULT_TOKEN" &

# Set Vault environment variables
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="$VAULT_TOKEN"
export VAULT_TOKEN_BASE64=$(echo -n $VAULT_TOKEN | base64)

# Wait for vault to be fully up and running
until [ "$(docker ps | grep -P 'vault.+Up')" ]; do echo "Waiting for vault to start..." ; sleep 1; done
until [ "$(vault status | grep -P 'Initialized.+true')" ]; do echo "Waiting for vault to start..." ; sleep 1; done


echo ""
echo "============================"
echo "Seeding Vault secrets"
echo "============================"
echo ""

# Seed vault with initial secrets
vault kv put secret/frey/services/netbox/admin username='admin' password="$NETBOX_ADMIN_PASSWORD" email="$NETBOX_ADMIN_EMAIL" api_token="$NETBOX_APITOKEN" host="https://netbox.netbox.svc.cluster.local" #Note the hardcoded host URL!  This is for internal cluster access from AWX->NetBox
vault kv put secret/frey/services/awx/admin password="$AWX_ADMIN_PASSWORD"
vault kv put secret/frey/services/awx/ssh username="$AWX_SSH_USERNAME" private_key="$(cat $SSH_KEY_PATH)" ssh_password="$AWX_SSH_PASSWORD"
vault kv put secret/frey/services/awx/config git_repo_url="$REPO_URL" git_branch="$BRANCH_NAME"

# Validate that secrets are added properly
until [ "$(vault kv list secret/frey/services/netbox | grep admin)" ]; do echo "Waiting for Vault to install netbox secrets..." ; sleep 1; done
until [ "$(vault kv list secret/frey/services/awx | grep -e ssh -e admin -e config)" ]; do echo "Waiting for Vault to install netbox secrets..." ; sleep 1; done

unset NETBOX_ADMIN_PASSWORD
unset NETBOX_APITOKEN
unset AWX_ADMIN_PASSWORD

### EXTERNAL-SECRETS OPERATORS ###

echo ""
echo "============================"
echo "Installing external-secrets"
echo "============================"
echo ""

# Must create namespaces first for ExternalSecrets to be installed into properly.  This is annoying but necessary.
kubectl create namespace netbox
kubectl create namespace awx-operator

# Install external secrets operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace -f services/external-secrets/frey-external_secrets-values.yaml --wait

# A secondary wait check for external-secrets to be fully up and running before applying SecretStore and ExternalSecret
until [ "$(kubectl get all -n external-secrets | grep -P 'pod/external-secrets-webhook-.+1/1.+Running' && kubectl get all -n external-secrets | grep -P 'pod/external-secrets-\d+.+1/1.+Running')" ]; do echo "Waiting for external-secrets-webhook to start..." ; sleep 3; done

# Capture local IP address for use in ClusterSecretStore
export LOCAL_IP_ADDRESS=$(ip route | grep "^default" | awk 'NR==1 {print $(NF-2)}')

# Deploy SecretStore and ExternalSecret for Frey admin user
envsubst < services/external-secrets/frey-external_secrets_vault_ClusterSecretStore.yaml | kubectl apply -f -
unset VAULT_TOKEN_BASE64
kubectl apply -f services/external-secrets/frey-external_secrets_vault_ExternalSecret_frey-netbox-admin.yaml #NetBox secret
kubectl wait --for=condition=Ready externalsecret/vault-external-frey-services-netbox-admin-secret -n netbox #Wait for NetBox secret to be properly sync'd
kubectl apply -f services/external-secrets/frey-external_secrets_vault_ExternalSecret_frey-awx-admin.yaml #AWX secret
kubectl wait --for=condition=Ready externalsecret/vault-external-frey-services-awx-admin-secret -n awx-operator #Wait for AWX secret to be properly sync'd

### NETBOX ###

echo ""
echo "============================"
echo "Installing NetBox Helm Chart"
echo "============================"
echo ""

# Install NetBox using netbox-chart

echo "DEBUG: NETBOX_URL = $NETBOX_URL"
#helm install netbox oci://ghcr.io/netbox-community/netbox-chart/netbox --create-namespace --namespace netbox -f services/netbox/frey-netbox-values.yaml
sleep 5 #testing.  trying to determine why we see random failures where the NETBOX_URL value is not properly inserted and/or parsed in the helm values file
envsubst '${NETBOX_URL}' < services/netbox/frey-netbox-values.yaml | helm install netbox oci://ghcr.io/netbox-community/netbox-chart/netbox --create-namespace --namespace netbox -f -

### AWX ###

export AWX_HELM_TIMEOUT="15m"

echo ""
echo "============================"
echo "Installing AWX Helm Chart"
echo " ...be patient..."
echo " ...this can take a while..."
echo ""
echo "Install timeout value is $AWX_HELM_TIMEOUT"
echo "============================"
echo ""

# Add repo and install AWX operator using Helm chart
helm repo add awx-operator https://ansible-community.github.io/awx-operator-helm
envsubst '${AWX_URL}' < services/awx/frey-awx-values.yaml | helm install --namespace awx-operator --create-namespace awx-operator awx-operator/awx-operator --timeout $AWX_HELM_TIMEOUT --debug -f -