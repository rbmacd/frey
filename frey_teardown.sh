#/bin/sh

## Teardown script to remove services and helm charts for Frey
## Initial iterations are pure bash script, later iterations may move to Ansible or Terraform


### AWX ###

# Leave repo and remove AWX operator using Helm chart
#helm repo add awx-operator https://ansible-community.github.io/awx-operator-helm
helm delete --namespace awx-operator awx-operator


### NETBOX ###

# Remove NetBox using netbox-chart
helm delete netbox --namespace netbox
# Be careful with this one!  Removing all PVCS in netbox namespace
kubectl delete pvc -n netbox $(kubectl get pvc -n netbox -o yaml | yq '.items[].metadata.name')


### EXTERNAL-SECRETS OPERATORS ###
helm delete -n external-secrets external-secrets


### VAULT ###
docker kill $(docker ps | grep vault | awk '{print $1}')
unset VAULT_ADDR
unset VAULT_TOKEN


### K3S ###
sudo /usr/local/bin/k3s-uninstall.sh
unset KUBECONFIG