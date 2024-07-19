> *Errors or typos? Topics missing? Hard to read? <a href="https://docs.google.com/forms/d/e/1FAIpQLScIt3ffetkaKW3gDv6FDk7CfUTNYP_HGmqQotSTtj2htKkVBw/viewform?usp=pp_url&entry.1739714854=https://maas.io/docs/troubleshooting-common-maas-issues" target = "_blank">Let us know.</a>*

## Pre-registering Machine with IPMI Address as FQDN

**Problem:**
Users encounter issues when trying to set the IPMI IP address field as an FQDN in MAAS. The machine gets registered with an IPv4 address associated with the FQDN, and the commissioning process does not complete.

**Solution:**
To address this issue and implement workarounds, follow these steps:

1. **Direct FQDN Usage:**
   - Currently, MAAS does not support using FQDN directly for the `power_address` field. The `power_address` must be an IPv4 or IPv6 address as per the BMC enlistment documentation.

2. **Workarounds:**

   **a. Use Unique Hostnames in the Cluster:**
   - Ensure each machine in the cluster has a unique hostname. This can help in distinguishing and managing machines more effectively.

   **b. Assign FQDN Management Hostnames:**
   - Assign a unique management FQDN to the BMC/IPMI IP of each machine. For example, use `[hostname]-mgmt` as the FQDN for the IPMI address.

   **c. Update BMC IP using Python Script:**
   - Write a Python script that updates the BMC IP address for each machine using the MAAS API. Schedule this script to run periodically (e.g., every 5 minutes) using `cron`.

   Example Python script:
   ```python
   import maas.client
   from maas.client import login
   from maas.client.enum import NodeStatus

   MAAS_API_URL = 'http://<MAAS_SERVER>/MAAS/'
   API_KEY = '<YOUR_API_KEY>'
   FQDN_SUFFIX = '-mgmt'

   def update_bmc_ips():
       client = login(MAAS_API_URL, API_KEY)
       nodes = client.machines.list(status=NodeStatus.READY)
       for node in nodes:
           hostname = node.hostname
           fqdn = f"{hostname}{FQDN_SUFFIX}"
           ip_address = socket.gethostbyname(fqdn)
           node.power_address = ip_address
           node.save()

   if __name__ == "__main__":
       update_bmc_ips()
   ```

   - Add the script to `crontab` to run every 5 minutes:
     ```bash
     */5 * * * * /usr/bin/python3 /path/to/update_bmc_ips.py
     ```

By following these steps, users can manage their MAAS setup more effectively, even when direct FQDN usage is not supported for IPMI addresses. The provided workarounds ensure that the IPMI addresses are updated and managed correctly using the MAAS API and periodic scripts.

## Automating Initial Configuration Settings for New Machines

**Problem:**
Users need to manually configure network interfaces to DHCP and set power configurations to Manual for new machines added to MAAS, seeking a way to automate these settings.

**Solution:**
To automate the initial configuration settings for new machines in MAAS, follow these steps:

1. **Use Preseed Scripts:**
   - Utilize MAAS preseed scripts to automate network and power configurations. Preseed scripts can run commands during different stages of machine deployment.

2. **Curtin Userdata:**
   - Modify `curtin_userdata` to include early commands for setting network interfaces to DHCP and power configuration to Manual. Add these configurations to the preseed file.

   Example preseed configuration:
   ```yaml
   early_commands:
     10_dhcp: |
       for nic in $(ls /sys/class/net/ | grep -v lo); do
         echo "dhclient ${nic}" >> /etc/network/interfaces.d/${nic};
         dhclient ${nic}
       done
     20_power: |
       echo "manual" > /etc/maas/power.conf
   ```

3. **MAAS CLI:**
   - Use the MAAS CLI to automate the setting of DHCP and power configuration for newly added machines. Create a script to be run after the machine is added to MAAS.

   Example script:
   ```bash
   #!/bin/bash
   MACHINE_ID=$1

   # Set network interface to DHCP
   maas admin interface link-subnet $MACHINE_ID \
     $(maas admin interfaces read $MACHINE_ID | jq '.[0].id') \
     mode=DHCP

   # Set power configuration to Manual
   maas admin machine update $MACHINE_ID power_type=manual
   ```

4. **Automate Through Hooks:**
   - Use MAAS hooks to trigger the script whenever a new machine is added. Hooks can be configured to execute scripts based on specific events.

5. **Check Certified Hardware:**
   - Ensure that the hardware being added to MAAS is certified and recognized by MAAS. This helps in automatic detection and configuration.

6. **Custom Automation:**
   - Integrate these steps into your existing automation framework if you have one. Tools like Ansible, Terraform, or custom scripts can be used to manage these configurations.

By implementing these steps, users can automate the initial configuration settings for new machines in MAAS, reducing manual intervention and streamlining the deployment process.

## VLAN Issues and Rack Controller Configuration

**Problem:**
Users encounter issues with VLANs not being utilized on any rack controller, leading to problems with DHCP and network connectivity.

**Solution:**
To troubleshoot and resolve VLAN issues in MAAS, follow these steps:

1. **Configure VLAN Interfaces:**
   - Ensure that VLAN interfaces are correctly configured on the rack controller with proper IDs, links, and IP addresses. Use `netplan` to apply configurations:
     ```bash
     sudo netplan apply
     ```

2. **Define Subnets Properly:**
   - Verify that subnets are defined correctly in MAAS for each VLAN. Check that the network, gateway, and DNS information are accurately entered.

3. **Physical Connections:**
   - Confirm that the rack controller is physically connected to the appropriate networks and VLANs. If using a managed switch, ensure that ports are configured for the correct VLANs.

4. **Check MAAS Logs:**
   - Review rack controller logs for any errors related to VLANs or DHCP:
     ```bash
     tail -f /var/log/maas/*.log
     ```

5. **Force Network Re-detection:**
   - Remove and re-add the rack controller in MAAS to force it to re-detect available networks and VLANs.

6. **Test DHCP on Single VLAN:**
   - Enable DHCP on one VLAN at a time to identify any working configurations.

7. **Static IP Address:**
   - Consider setting a static IP address on the VLAN interface to avoid DHCP conflicts.

8. **Restart Rack Controller:**
   - Restart the rack controller to ensure it reconnects correctly to MAAS and the VLANs.

9. **Reinstall Rack Controller:**
   - As a last resort, reinstall the rack controller following the official documentation to resolve any networking issues:
     - Ensure the rack controller is not installed on the same machine as the region controller.

10. **DHCP Forwarding Considerations:**
    - If using DHCP forwarding on the router, ensure that the rack servers on the VLAN can still communicate with the DHCP server.

By following these steps, users can troubleshoot and resolve issues with VLAN utilization on rack controllers in MAAS, ensuring proper network configuration and connectivity.

## Releasing Old DHCP Leases

**Problem:**
Deploying servers in MAAS results in an error stating "No more IPs available in subnet," despite having unused IP addresses.

**Solution:**
To release old DHCP leases and resolve IP allocation issues, follow these steps:

1. **Check for Orphaned IP Addresses:**
   - Run the following SQL query to identify orphaned IP addresses in the MAAS database:
     ```sql
     sudo -u postgres psql -d maasdb -c "
     SELECT count(*)
     FROM maasserver_staticipaddress
     LEFT JOIN maasserver_interface_ip_addresses ON maasserver_staticipaddress.id = maasserver_interface_ip_addresses.staticipaddress_id
     LEFT JOIN maasserver_interface ON maasserver_interface.id = maasserver_interface_ip_addresses.interface_id
     WHERE maasserver_staticipaddress.ip IS NULL 
       AND maasserver_interface.type = 'unknown' 
       AND maasserver_staticipaddress.alloc_type = 6;
     "
     ```
   - This will help you identify any orphaned addresses that are not properly allocated.

2. **Clean Neighbor Discoveries:**
   - Use the MAAS CLI to clear discovered neighbors, which might be causing IP conflicts:
     ```bash
     maas admin discoveries clear all=True -k
     ```

3. **Verify Cleared Discoveries:**
   - After clearing, check if the discoveries were successfully removed:
     ```bash
     maas admin discoveries read -k
     ```

4. **Clear ARP Table (Optional):**
   - If necessary, clear the ARP table on the Rack server to ensure no stale entries exist:
     ```bash
     arp -d [IP address]
     ```
   - Example to clear all entries:
     ```bash
     arp -d 172.21.68.79
     arp -d 172.21.68.69
     ```

5. **Run Deployment Again:**
   - Attempt to deploy the server again to check if the issue persists. If the error still occurs, check the discoveries once more without cleaning:
     ```bash
     maas admin discoveries read -k
     ```

By following these steps, users can release old DHCP leases and address IP exhaustion issues in MAAS, ensuring successful server deployment.

## Configuring loopback addresses

**Problem:**
Configuring the loopback interface (lo) using MAAS is not straightforward, especially when deploying nodes for use with Free Range Routing (FRR) and BGP.

**Solution:**
To configure loopback addresses in MAAS, follow these steps:

1. **Understand Loopback Interface:**
   - Loopback interfaces do not require MAC addresses since they are used for internal routing within the node itself.

2. **Manually Add Loopback Interface:**
   - After commissioning a node, manually add the loopback interface in MAAS.
   - If the MAAS web UI requires a MAC address for the loopback interface, use a placeholder value like `00:00:00:00:00:00` but ensure it does not conflict with other nodes.

3. **Avoid Duplicate MAC Addresses:**
   - Since MAAS does not support duplicate MAC addresses, manually configure the loopback interface on each node with a unique identifier or find a way to bypass the MAC address requirement.

4. **Alternative Methods:**
   - If manually adding the loopback interface in MAAS is problematic, consider configuring the loopback interface outside of MAAS using post-deployment scripts.
   - Use MAAS to deploy the base configuration, then apply custom network configurations (including loopback interfaces) through cloud-init or other automation tools.

5. **Feedback from Support:**
   - Internal support teams may have additional methods or patches to address this issue. Reach out to MAAS support for the latest solutions or updates regarding loopback interface configuration.

By following these steps, users can effectively configure loopback interfaces on nodes managed by MAAS, facilitating advanced network setups like L3 routing and BGP.

## Shrinking dynamic IP range

**Problem:**
Users may encounter errors when attempting to shrink the dynamic IP address range in MAAS due to conflicts with existing IP addresses or ranges.

**Solution:**
To troubleshoot and resolve this issue, follow these steps:

1. **Check Current IP Ranges and Static Addresses:**
   - Use the following SQL queries to check the current IP ranges and static IP addresses in the MAAS database:
     ```sql
     SELECT * FROM maasserver_iprange;
     SELECT * FROM maasserver_staticipaddress WHERE text(ip) LIKE '192.168.0.%' ORDER BY ip;
     ```
   - Identify any existing IP addresses that may conflict with the desired new range.

2. **Identify Sticky Addresses:**
   - Identify any sticky addresses within the current range that may cause conflicts. Sticky addresses are IP addresses allocated by MAAS DHCP that persist over reboots.

3. **Adjust IP Range:**
   - Ensure that the new IP range does not overlap with any existing reserved or sticky addresses. Modify the start and end IP addresses to avoid conflicts.
   - Example: If the current range is 192.168.0.194 - 192.168.0.220 and sticky addresses occupy 192.168.0.195 - 192.168.0.211, adjust the range to avoid these addresses.

4. **Update MAAS Configuration:**
   - After identifying a non-conflicting range, update the MAAS configuration to reflect the new IP range.

5. **Database Updates:**
   - If necessary, manually update the IP range in the MAAS database to ensure consistency. Make sure to backup the database before making any changes.

By following these steps, users can effectively shrink the dynamic IP address range in MAAS without encountering conflicts with existing IP addresses or ranges.

## Overlapping subnets can break deployments

Ensure that your subnets don't overlap to avoid deployment failures. Check and delete any outdated or redundant subnets through the Web UI.

## Need to reconfigure server IP address

If you need to modify your MAAS server's IP, simply re-run the setup:

```nohighlight
sudo dpkg-reconfigure maas-region-controller
```

## Network booting IBM Power servers

IBM Power servers with OPAL firmware utilise Petitboot for PXE interactions. For smooth deployment, configure a specific NIC as the network boot device via Petitboot.

## Resolve DNS conflicts between LXD and MAAS

If both MAAS and LXD are managing DNS, disable LXD's DNS and DHCP:

```nohighlight
lxc network set $LXD_BRIDGE_NAME dns.mode=none
lxc network set $LXD_BRIDGE_NAME ipv4.dhcp=false
lxc network set $LXD_BRIDGE_NAME ipv6.dhcp=false
```

## Nodes hang on "Commissioning"

**Timing issues**: Make sure the hardware clocks on your nodes and MAAS server are synchronised.

**Network drivers**: Use Linux-compatible network adaptors if commissioning hangs due to driver issues.

Feel free to contribute additional issues and solutions.

## Command 'packer' not found

When you try to run `packer` or execute a `make` command, you may encounter an error message indicating that `packer` is not installed. The issue can be resolved by [referring to this section](/t/how-to-customise-images/5104).

## Error with `packer`:

```nohighlight
stormrider@neuromancer:~$ packer
Command 'packer' not found...
```

## Error with `make`:

```nohighlight
stormrider@neuromancer:~/mnt/Dropbox/src/git/packer-maas/ubuntu$ make
sudo: packer: command not found...
```

## No rule to make target ...OVMF_VARS.fd

Should you see an error like the one below, you've forgotten to [install a needed dependency](/t/how-to-customise-images/5104).

```nohighlight
make: *** No rule to make target '/usr/share/OVMF/OVMF_VARS.fd'...
```

## Failure to create QEMU driver

Encountering the following error means you're missing a dependency. Refer to [this section](/t/how-to-customise-images/5104) for resolution.

```nohighlight
Failed creating Qemu driver: exec: "qemu-img": executable file not found in $PATH
```

## Timeout changes not taking effect

If you've modified the session timeout settings in the MAAS web interface but don't see the changes, do the following:

1. Make sure you've got administrative access to the MAAS web interface for changing session timeout settings.
2. After altering the session timeout duration, don't forget to save the new settings.
3. Clear your browser's cache and cookies. They might be holding on to old settings. Restart your browser and try again.

## Users logged out before timeout expires

If users are getting logged out before the session timeout you've set, consider these checks:

1. Double-check the unit of time you've set for the session timeout (weeks, days, hours, minutes). A mistake in units can cause unexpected timeouts.
2. Inspect any server settings conflicting with MAAS that may cause premature session timeouts, like window manager logout settings in Ubuntu.
3. If you're using a load balancer or proxy, make sure it's not causing additional timeouts conflicting with MAAS.

## Can't set an infinite session timeout

You can't set an "infinite" session timeout in MAAS. The maximum allowed duration is 14 days. This limit strikes a balance between security and usability.

## Users are suddenly logged out

MAAS will auto-logoff users when the session timeout duration is reached. If this happens more often than desired, consider increasing the timeout value to prevent frequent "idle-time" logouts.

## Can't set different timeouts for user groups

MAAS only supports a global session timeout setting. While you can't customise this by user group, you could deploy separate MAAS instances with different configurations to achieve similar effects.

## Can't extend sessions beyond the timeout

The timeout duration resets every time there's activity from the user. To extend a session, simply refresh the page before the timeout period ends. This will reset the session timer.

## Django errors

Sometimes, you may face the following Django error:

```nohighlight
django.core.exceptions.ValidationError: ['Subarchitecture(<value>) must be generic when setting hwe_kernel.']
```

To solve this, try specifying a different commissioning kernel—perhaps upgrading from Xenial to Focal.

## Forgotten password

If you forget your MAAS admin password but have sudo privileges, you can reset it like so:

```nohighlight
sudo maas changepassword $PROFILE
```

Replace `$PROFILE` with the username.

## Missing Web UI

The default MAAS web UI is at `http://<hostname>:5240/MAAS/`. If it's unreachable:

- Verify Apache is running: `sudo /etc/init.d/apache2 status`.
- Validate the hostname or try `http://127.0.0.1:5240/MAAS/`.

## Backdoor image login

Ephemeral images boot nodes during MAAS activities. If you need emergency access, you can create a temporary backdoor in these images. This lets you log in to check logs and debug issues.

## Extract the cloud image

Download the appropriate image and extract its files:

```nohighlight
wget https://cloud-images.ubuntu.com/xenial/current/xenial-server-cloudimg-amd64-root.tar.gz
mkdir xenial
sudo tar -C xenial -xpSf xenial-server-cloudimg-amd64-root.tar.gz --numeric-owner --xattrs "--xattrs-include=*"
```

## Generate password hash

Create a SHA-512 hashed password:

```nohighlight
python3 -c 'import crypt; print(crypt.crypt("ubuntu", crypt.mksalt(crypt.METHOD_SHA512)))'
```

Modify the `xenial/etc/shadow` file to insert this hash.

## Rebuild squashfs image

Create a new SquashFS file with your changes:

```nohighlight
sudo mksquashfs xenial/ xenial-customized.squashfs -xattrs -comp xz
```

Replace the existing MAAS image with this customised one.

## Migrating snap installs

For snap-based MAAS in 'all' mode, you can migrate to a local PostgreSQL:

```nohighlight
sudo /snap/maas/current/helpers/migrate-vd Snapatabase
```

## Manual DB export

To manually move your MAAS database, run:

```nohighlight
export PGPASS=$(sudo awk -F':\\s+' '$1 == "database_pass" {print $2}' \
    /var/snap/maas/current/regiond.conf)
sudo pg_dump -U maas -h /var/snap/maas/common/postgres/sockets \
    -d maasdb -F t -f maasdb-dump.tar
```

Stop the MAAS snap (`sudo snap stop maas`) and create a new PostgreSQL user and database for MAAS on the destination machine.

This should cover various miscellaneous issues you may encounter while using MAAS. Feel free to contribute with your own experiences.

## Leaked admin API key

If MAAS hardware sync leaks your admin API key, you can:

- Rotate all admin tokens
- Re-deploy machines with hardware sync enabled

Or swap the token manually:

## Manually swap the MAAS admin API token

Query the database to identify machines with hardware sync enabled:

```nohighlight
select system_id 
from maasserver_node 
where enable_hw_sync = true;
```

Rotate API keys on any affected machines. To verify an API key belongs to an admin, perform this database query:

```nohighlight
select u.username, u.email 
from auth_user u
left join piston3_consumer c 
on u.id = c.user_id
where key = 'your-leaked-api-key';
```

To remove the leaked API key, log in to the MAAS UI and delete it. Then reconfigure your MAAS CLI and hardware sync as needed.