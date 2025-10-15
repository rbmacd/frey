FROM quay.io/ansible/awx-ee:latest

USER root

# Install NetBox collection to system location
RUN ansible-galaxy collection install netbox.netbox:3.19.0 \
    --collections-path /usr/share/ansible/collections

# Install pynetbox Python package
RUN pip3 install --no-cache-dir pynetbox==7.4.0

# Verify installations
RUN ansible-galaxy collection list | grep netbox
RUN pip3 list | grep pynetbox

USER 1000

LABEL name="frey-awx-netbox-ee" \
      description="AWX Execution Environment with NetBox support" \
      version="1.0.0"