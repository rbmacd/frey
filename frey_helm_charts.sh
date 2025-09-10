#/bin/sh
helm --kubeconfig /etc/rancher/k3s/k3s.yaml install --namespace awx --create-namespace awx-operator awx-operator/awx-operator -f services/awx/frey-awx-values.yaml
helm --kubeconfig /etc/rancher/k3s/k3s.yaml install netbox oci://ghcr.io/netbox-community/netbox-chart/netbox --create-namespace --namespace netbox -f services/netbox/frey-netbox-values.yaml
