#/bin/sh

### k3s helm commands with kubeconfig manually defined
#helm --kubeconfig /etc/rancher/k3s/k3s.yaml install --namespace awx --create-namespace awx-operator awx-operator/awx-operator -f services/awx/frey-awx-values.yaml
#helm --kubeconfig /etc/rancher/k3s/k3s.yaml install netbox oci://ghcr.io/netbox-community/netbox-chart/netbox --create-namespace --namespace netbox -f services/netbox/frey-netbox-values.yaml

helm install --namespace awx --create-namespace awx-operator awx-operator/awx-operator -f services/awx/frey-awx-values.yaml
helm install netbox oci://ghcr.io/netbox-community/netbox-chart/netbox --create-namespace --namespace netbox -f services/netbox/frey-netbox-values.yaml
