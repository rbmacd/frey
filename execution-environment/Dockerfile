FROM quay.io/ansible/awx-ee:latest

USER root

# Install various NetDevOps collections to system location
RUN ansible-galaxy collection install netbox.netbox:3.19.0 arista.eos:6.2.2 cisco.ios:5.3.0 cisco.iosxr:6.1.1 cisco.nxos:5.3.0 junipernetworks.junos:5.3.1 arista.avd:latest \
    --collections-path /usr/share/ansible/collections

# Install pynetbox Python package
RUN pip3 install --no-cache-dir pynetbox==7.4.0

# Verify installations
RUN ansible-galaxy collection list | grep netbox
RUN pip3 list | grep pynetbox

USER 1000

LABEL name="frey-awx-ee" \
      description="AWX Execution Environment for Frey NetDevOps services" \
      version="1.0.0"