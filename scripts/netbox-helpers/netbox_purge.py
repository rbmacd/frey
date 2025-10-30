#!/usr/bin/env python3

###
# 
# Helper script to purge the NetBox inventory and start fresh
# 
# Part of the Frey project - https://github.com/rbmacd/frey#
# 
# This script helps users purge the NetBox inventory without requiring
# a full helm teardown and rebuild.  The goal is easy iteration in lab or
# non-production environments.
#
# THIS SCRIPT IS AS DANGEROUS AS IT SOUNDS.  USE YOUR BRAIN BEFORE USING THE SCRIPT.
#
###

import os
import sys
import logging
import pynetbox # type: ignore
import urllib3
from urllib3.exceptions import InsecureRequestWarning

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def purge_netbox():
    """Purge all data from NetBox database."""
    
    # Get credentials from environment
    netbox_url = os.getenv('NETBOX_URL')
    netbox_token = os.getenv('NETBOX_APITOKEN')
    
    if not netbox_url or not netbox_token:
        logger.error("NETBOX_URL and NETBOX_APITOKEN environment variables must be set")
        sys.exit(1)
    
    try:
        # Connect to NetBox
        logger.info(f"Connecting to NetBox at {netbox_url}")
        nb = pynetbox.api(netbox_url, token=netbox_token)
        nb.http_session.verify=False ##This is needed for local testing.  Should make this a script config option in later iterations. -RM
        urllib3.disable_warnings(InsecureRequestWarning) ##Also needed for local testing to suppress annoying SSL self-signed cert warnings.  -RM
        
        # Define deletion order (dependencies first)
        # Order matters - delete child objects before parents
        deletion_plan = [
            # IP Addressing
            ('ipam.ip_addresses', 'IP Addresses'),
            ('ipam.prefixes', 'Prefixes'),
            ('ipam.aggregates', 'Aggregates'),
            ('ipam.vlans', 'VLANs'),
            ('ipam.vlan_groups', 'VLAN Groups'),
            ('ipam.vrfs', 'VRFs'),
            ('ipam.rirs', 'RIRs'),
            
            # Circuits
            ('circuits.circuit_terminations', 'Circuit Terminations'),
            ('circuits.circuits', 'Circuits'),
            ('circuits.providers', 'Providers'),
            ('circuits.circuit_types', 'Circuit Types'),
            
            # DCIM - Cables and connections
            ('dcim.cables', 'Cables'),
            ('dcim.power_feeds', 'Power Feeds'),
            ('dcim.power_panels', 'Power Panels'),
            
            # DCIM - Devices
            ('dcim.console_ports', 'Console Ports'),
            ('dcim.console_server_ports', 'Console Server Ports'),
            ('dcim.power_ports', 'Power Ports'),
            ('dcim.power_outlets', 'Power Outlets'),
            ('dcim.interfaces', 'Interfaces'),
            ('dcim.front_ports', 'Front Ports'),
            ('dcim.rear_ports', 'Rear Ports'),
            ('dcim.device_bays', 'Device Bays'),
            ('dcim.inventory_items', 'Inventory Items'),
            ('dcim.devices', 'Devices'),
            
            # DCIM - Racks
            ('dcim.rack_reservations', 'Rack Reservations'),
            ('dcim.racks', 'Racks'),
            ('dcim.rack_roles', 'Rack Roles'),
            ('dcim.rack_groups', 'Rack Groups'),
            
            # DCIM - Sites and locations
            ('dcim.locations', 'Locations'),
            ('dcim.sites', 'Sites'),
            ('dcim.site_groups', 'Site Groups'),
            ('dcim.regions', 'Regions'),
            
            # DCIM - Device types and platforms
            ('dcim.device_types', 'Device Types'),
            ('dcim.module_types', 'Module Types'),
            ('dcim.manufacturers', 'Manufacturers'),
            ('dcim.platforms', 'Platforms'),
            ('dcim.device_roles', 'Device Roles'),
            
            # Virtualization
            ('virtualization.virtual_disks', 'Virtual Disks'),
            ('virtualization.vm_interfaces', 'VM Interfaces'),
            ('virtualization.virtual_machines', 'Virtual Machines'),
            ('virtualization.clusters', 'Clusters'),
            ('virtualization.cluster_groups', 'Cluster Groups'),
            ('virtualization.cluster_types', 'Cluster Types'),
            
            # Tenancy
            ('tenancy.contacts', 'Contacts'),
            ('tenancy.contact_groups', 'Contact Groups'),
            ('tenancy.contact_roles', 'Contact Roles'),
            ('tenancy.tenant_groups', 'Tenant Groups'),
            ('tenancy.tenants', 'Tenants'),
            
            # Extras
            ('extras.tags', 'Tags'),
            ('extras.custom_links', 'Custom Links'),
            ('extras.webhooks', 'Webhooks'),
            ('extras.custom_fields', 'Custom Fields'),
        ]
        
        logger.info("=" * 60)
        logger.info("Starting NetBox purge - this will delete ALL data!")
        logger.info("=" * 60)
        
        total_deleted = 0
        
        # Execute deletion plan
        for endpoint_path, name in deletion_plan:
            try:
                # Navigate to the endpoint
                parts = endpoint_path.split('.')
                endpoint = nb
                for part in parts:
                    endpoint = getattr(endpoint, part)
                
                # Get all objects
                objects = list(endpoint.all())
                count = len(objects)
                
                if count > 0:
                    logger.info(f"Deleting {count} {name}...")
                    for obj in objects:
                        try:
                            obj.delete()
                        except Exception as e:
                            logger.warning(f"  Failed to delete {name} (ID: {obj.id}): {e}")
                    
                    total_deleted += count
                    logger.info(f"  ✓ Deleted {count} {name}")
                else:
                    logger.info(f"No {name} to delete")
                    
            except AttributeError:
                logger.warning(f"Endpoint not found: {endpoint_path} - skipping")
            except Exception as e:
                logger.error(f"Error deleting {name}: {e}")
        
        logger.info("=" * 60)
        logger.info(f"Purge complete! Total objects deleted: {total_deleted}")
        logger.info("NetBox is now in a fresh state")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Fatal error during purge: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Confirmation prompt
    print("\n" + "!" * 60)
    print("WARNING: This will DELETE ALL DATA from NetBox!")
    print("!" * 60)
    response = input("\nType 'DELETE ALL DATA' to confirm: ")
    
    if response == "DELETE ALL DATA":
        purge_netbox()
    else:
        print("Purge cancelled.")
        sys.exit(0)