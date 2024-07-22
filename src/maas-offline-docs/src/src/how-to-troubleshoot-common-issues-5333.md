> *Errors or typos? Topics missing? Hard to read? <a href="https://docs.google.com/forms/d/e/1FAIpQLScIt3ffetkaKW3gDv6FDk7CfUTNYP_HGmqQotSTtj2htKkVBw/viewform?usp=pp_url&entry.1739714854=https://maas.io/docs/troubleshooting-common-maas-issues" target = "_blank">Let us know.</a>*

## Legacy BIOS boot from second NIC

**Problem:**
When using MAAS with machines that boot via legacy BIOS, there's an issue where PXE booting from the second NIC results in a "No boot filename received" error. This occurs despite the machine receiving a DHCP offer.

**Solution:**
The issue is likely due to the limitation that, until MAAS version 3.5, booting from the first NIC is required for machines using legacy BIOS. To resolve this, you need to configure the machines to boot from the first NIC and use the second NIC for other network configurations.

**Steps to resolve:**

1. **Verify boot order:**
   - Ensure that the boot order in the BIOS settings of your machines prioritizes the first NIC for PXE booting.

2. **Reconfigure MAAS network settings:**
   - Ensure that the MAAS server and DHCP configurations are set up correctly for the first NIC.

3. **Update MAAS machine entries:**
   - If necessary, re-add the machines in MAAS using the MAC address of the first NIC.

**Detailed steps:**

**a. Check and configure BIOS settings:**

1. **Access BIOS/UEFI settings:**
   - Restart the machine and enter the BIOS/UEFI setup (usually by pressing F2, F10, F12, or Delete during boot).
   
2. **Set boot order:**
   - Navigate to the boot settings and set the first NIC as the primary boot device for PXE booting.

**b. Update MAAS configuration:**

1. **Re-add machine with first NIC:**
   - In the MAAS UI, ensure the machine is enlisted with the MAC address of the first NIC.
   
   **Example command to add machine with first NIC:**
   ```bash
   maas $PROFILE machines add mac_addresses=$FIRST_NIC_MAC
   ```

2. **Verify DHCP configuration:**
   - Ensure DHCP is correctly configured for the first NIC in the subnet used for PXE booting.

**Example DHCP configuration check:**
   ```bash
   sudo nano /etc/dhcp/dhcpd.conf
   ```
   - Ensure the correct interface and subnet are specified.

**c. Re-commission the machine:**

1. **Commission the machine:**
   - Re-commission the machine in MAAS using the first NIC for PXE booting.

   **Example command to commission machine:**
   ```bash
   maas $PROFILE machine commission $MACHINE_ID
   ```

2. **Check logs for errors:**
   - Monitor the commissioning logs for any errors related to network configuration.

   **Example command to check logs:**
   ```bash
   sudo tail -f /var/log/maas/regiond.log
   sudo tail -f /var/log/maas/rackd.log
   ```

**Example workflow:**

1. **Verify boot order in BIOS:**
   - Ensure the first NIC is set as the primary boot device.

2. **Add machine to MAAS with first NIC:**
   ```bash
   maas $PROFILE machines add mac_addresses=$FIRST_NIC_MAC
   ```

3. **Configure and verify DHCP for first NIC:**
   ```bash
   sudo nano /etc/dhcp/dhcpd.conf
   ```

4. **Commission the machine:**
   ```bash
   maas $PROFILE machine commission $MACHINE_ID
   ```

5. **Monitor logs:**
   ```bash
   sudo tail -f /var/log/maas/regiond.log
   sudo tail -f /var/log/maas/rackd.log
   ```

By following these steps, you can ensure that machines with legacy BIOS can successfully PXE boot from the first NIC, resolving the "No boot filename received" error and enabling proper commissioning and deployment in MAAS.

## Using routed subnets

**Problem:**
The MAAS server is set up on VLAN 1000 with subnet 10.10.10.0/24 and is configured to serve another subnet 10.20.20.0/24 via DHCP relay. Devices in the 10.20.20.0/24 subnet can receive DHCP addresses but fail to connect to the TFTP server, resulting in timeouts.

**Solution:**
To resolve this issue, you need to ensure that TFTP and other necessary services can communicate properly across subnets. This involves verifying network configurations and ensuring that MAAS is set up to handle requests from both subnets.

**Steps to resolve the issue:**

1. **Check rackd logs:**
   - Inspect the rackd logs to verify that the TFTP requests are being received and to identify any potential issues.

   **Example command to view rackd logs:**
   ```bash
   sudo tail -f /var/log/maas/rackd.log
   ```

2. **Verify network configuration:**
   - Ensure that network devices are correctly configured to route traffic between the subnets. This includes ensuring that the DHCP relay is functioning properly and that there are no routing issues.

   **Example configuration check:**
   - Verify that routers or switches between the VLANs are configured to allow TFTP traffic.

3. **Enable ProxyDHCP:**
   - Ensure that ProxyDHCP is enabled on the MAAS server to handle PXE boot requests.

   **Example command to enable ProxyDHCP:**
   ```bash
   maas $PROFILE maas set-config name=enable_proxy value=true
   ```

4. **Check TFTP configuration:**
   - Verify that the TFTP server on the MAAS rack controller is properly configured to serve requests from both subnets.

   **Example TFTP configuration check:**
   ```bash
   sudo nano /etc/default/tftpd-hpa
   ```
   - Ensure the TFTP server is listening on the correct interfaces.

5. **Ensure IP forwarding:**
   - Verify that IP forwarding is enabled on the MAAS server to allow routing between the subnets.

   **Example command to enable IP forwarding:**
   ```bash
   sudo sysctl -w net.ipv4.ip_forward=1
   ```

6. **Firewall configuration:**
   - Double-check that there are no firewall rules blocking traffic between the subnets.

   **Example firewall check:**
   ```bash
   sudo ufw status
   ```

7. **Network device configuration:**
   - Ensure that network devices (routers/switches) are configured to forward TFTP and HTTP requests from devices in the 10.20.20.0/24 subnet to the MAAS server in the 10.10.10.0/24 subnet.

   **Example network configuration:**
   ```text
   Router Configuration:
   - DHCP relay pointing to 10.10.10.2
   - IP routes allowing traffic between 10.20.20.0/24 and 10.10.10.0/24
   ```

**Example workflow:**

1. **Check rackd Logs:**
   ```bash
   sudo tail -f /var/log/maas/rackd.log
   ```

2. **Verify network devices configuration:**
   - Ensure that all routers and switches are correctly configured to allow TFTP traffic.

3. **Enable ProxyDHCP on MAAS:**
   ```bash
   maas $PROFILE maas set-config name=enable_proxy value=true
   ```

4. **Check TFTP server configuration:**
   ```bash
   sudo nano /etc/default/tftpd-hpa
   ```
   - Ensure it listens on the correct interfaces.

5. **Enable IP forwarding:**
   ```bash
   sudo sysctl -w net.ipv4.ip_forward=1
   ```

6. **Check firewall status:**
   ```bash
   sudo ufw status
   ```

By following these steps, you can troubleshoot and resolve the issue of the MAAS server not responding to TFTP requests from the 10.20.20.0/24 subnet, ensuring that all devices can properly communicate with the MAAS server across different subnets.

## Commissioning failed due to lldpd

**Problem:**
The commissioning process fails at the "lldpd" installation step due to the error "Unable to locate package lldpd." This issue occurs in a disconnected environment where a local mirror of the Ubuntu repository is used.

**Solution:**
The issue is likely due to missing repository components in the local mirror configuration, particularly the "universe" component where the `lldpd` package resides.

**Steps to resolve:**

1. **Check repository components:**
   - Ensure that the local mirror includes the necessary repository components (`main`, `universe`, `restricted`, and `multiverse`).

2. **Update MAAS settings:**
   - Update the MAAS settings to ensure it uses the local mirror correctly, including all required components.

3. **Verify and update preseed configuration:**
   - Verify the preseed configuration to ensure it includes all necessary components.

4. **Detailed steps:**

   **a. Verify local mirror configuration:**
   - Ensure your local mirror configuration includes the `universe` component. 

   **Example local mirror configuration:**
   ```bash
   deb http://192.168.1.100/repos/archive.ubuntu.com/ubuntu focal main universe restricted multiverse
   ```

   **b. Update MAAS proxy settings:**
   - Ensure MAAS is configured to use the local mirror as a proxy and includes all components.

   **Example MAAS proxy configuration:**
   ```bash
   sudo maas $PROFILE maas set-config name=http_proxy value="http://192.168.1.100:8000/"
   ```

   **c. Verify preseed configuration:**
   - Access the preseed configuration to ensure it includes all necessary repository components.

   **Example command to access preseed:**
   ```bash
   http://<maas_ip>:5240/MAAS/metadata/latest/by-id/<system_id>/?op=get_preseed
   ```

   **Example preseed configuration:**
   ```yaml
   sources:
     repo_infra_3:
       source: deb http://192.168.1.100/repos/archive.ubuntu.com/ubuntu $RELEASE main universe restricted multiverse
   ```

   **d. Disable official repositories:**
   - Since the environment is disconnected from the internet, disable the official repositories to avoid errors.

   **Example configuration to disable official repositories:**
   ```yaml
   sources:
     repo_infra_3:
       source: deb http://192.168.1.100/repos/archive.ubuntu.com/ubuntu $RELEASE main universe restricted multiverse
   ```

   **e. Re-run commissioning:**
   - Re-run the commissioning process to ensure the changes take effect.

5. **Verify package availability:**
   - Confirm that the `lldpd` package is available in the local mirror by running the following command on a test machine:
   ```bash
   sudo apt-get update
   sudo apt-get install lldpd
   ```

By following these steps, you can ensure that the necessary repository components are included and configured correctly, allowing the commissioning process to complete successfully without errors related to the `lldpd` package.

## Adding domains to the DNS search list

**Problem:**
You want to add two additional domains to the DNS search list for a subnet in MAAS, but there doesn't seem to be an option to set this directly in the UI or through typical configuration methods.

**Solution:**
To add additional domains to the DNS search list for a subnet in MAAS, you can use a custom cloud-init script to configure the `resolv.conf` file. Follow these steps:

1. **Use cloud-init configuration:**
   - Cloud-init can be used to configure the DNS search list by specifying the appropriate settings in a custom cloud-init script.

2. **Steps to configure DNS search list:**

   **a. Create a custom cloud-init script:**
   - Create a cloud-init script that adds the desired search domains to the `resolv.conf` file.

   **Example cloud-init script:**
   ```yaml
   #cloud-config
   write_files:
     - path: /etc/cloud/cloud.cfg.d/99-custom-dns.cfg
       content: |
         network:
           config: disabled
   runcmd:
     - echo "search domain1.com domain2.com" >> /etc/resolv.conf
     - netplan apply
   ```

   **b. Update MAAS machine configuration:**
   - Apply this cloud-init script to the machines managed by MAAS. You can do this by adding the script to the custom commissioning and deployment scripts in the MAAS UI or via the CLI.

   **Example command to apply custom cloud-init script:**
   ```bash
   maas $PROFILE machine update $MACHINE_ID user_data="$(base64 -w 0 /path/to/your/cloud-init.yaml)"
   ```

   **c. Verify DNS configuration:**
   - After the machines have been deployed, verify that the `resolv.conf` file has the correct DNS search list entries.

   **Example command to check `resolv.conf`:**
   ```bash
   cat /etc/resolv.conf
   ```

3. **Ensure persistence:**
   - Since cloud-init might overwrite the network configuration on reboot, ensure that your custom cloud-init script disables network configuration management by cloud-init.

   **Example configuration to disable network configuration by cloud-init:**
   ```yaml
   network:
     config: disabled
   ```

   - Add this configuration to your cloud-init script to prevent cloud-init from overwriting your custom DNS settings.

**Example workflow:**

1. **Create custom cloud-init script:**
   ```yaml
   #cloud-config
   write_files:
     - path: /etc/cloud/cloud.cfg.d/99-custom-dns.cfg
       content: |
         network:
           config: disabled
   runcmd:
     - echo "search domain1.com domain2.com" >> /etc/resolv.conf
     - netplan apply
   ```

2. **Apply script to MAAS machine:**
   ```bash
   maas $PROFILE machine update $MACHINE_ID user_data="$(base64 -w 0 /path/to/your/cloud-init.yaml)"
   ```

3. **Deploy and verify:**
   - Deploy the machine and verify the DNS configuration.
   ```bash
   cat /etc/resolv.conf
   ```

By following these steps, you can add additional domains to the DNS search list for your MAAS-managed subnets, ensuring proper DNS resolution for your deployed machines.

## Clients get the image but don’t appear on the GUI

**Problem:**
Clients (VMs) receive the image and boot correctly from MAAS, but they do not appear in the MAAS GUI under the Machines section.

**Solution:**
This issue could be due to network misconfiguration or incorrect settings in MAAS that prevent the clients from being properly enlisted and commissioned. Follow these steps to resolve the issue:

1. **Verify network configuration:**
   - Ensure that DHCP is enabled on the correct VLAN where your VMs are located.
   - Check that the DHCP server sends the DHCP offer with the MAAS IP provided in the "next server" property.

2. **Check MAAS logs:**
   - Review MAAS logs for any errors or warnings that might indicate why the clients are not appearing in the GUI.

3. **Ensure proper enlistment:**
   - Confirm that the clients are properly enlisting with MAAS. This includes ensuring that the correct commissioning scripts are running.

4. **Steps to resolve the issue:**

   **a. Verify DHCP configuration:**
   - Ensure that the DHCP server on MAAS is correctly configured to provide IP addresses to the VMs on the correct VLAN.

   **Example command to check DHCP configuration:**
   ```bash
   maas $PROFILE dhcps read
   ```

   **b. Check MAAS logs:**
   - Check the logs for any errors or issues related to DHCP or network configuration.

   **Example command to view logs:**
   ```bash
   tail -f /var/log/maas/*.log
   ```

   **c. Verify network interface configuration:**
   - Ensure that the network interfaces on the MAAS VM are correctly configured and match the settings in MAAS.

   **d. Ensure correct enlistment:**
   - Verify that the VMs are set up to enlist correctly with MAAS. This includes making sure they are using the correct PXE boot settings.

   **Example steps to verify PXE boot:**
   1. Ensure the VM is set to network boot (PXE).
   2. Verify that the correct boot image is being used.

   **e. Check commissioning status:**
   - Make sure the VMs are commissioning correctly and check their status in MAAS.

   **Example command to check commissioning status:**
   ```bash
   maas $PROFILE machines read
   ```

5. **Additional configuration:**
   - Ensure that the MAAS server and clients are on the same network and that there are no firewall rules blocking communication.

**Example workflow:**

1. **Check DHCP and network configuration:**
   ```bash
   maas $PROFILE dhcps read
   ```

2. **Check MAAS logs:**
   ```bash
   tail -f /var/log/maas/*.log
   ```

3. **Verify PXE boot settings:**
   - Ensure VMs are set to boot from the network (PXE).

4. **Check commissioning status:**
   ```bash
   maas $PROFILE machines read
   ```

By following these steps, you can diagnose and resolve the issue of clients receiving images but not appearing in the MAAS GUI. This approach ensures proper network configuration and correct commissioning of the VMs.

## HA DHCP for relayed subnets

**Problem:**
Implementing high availability (HA) for DHCP in relayed subnets using MAAS is not straightforward, and the standard architecture restricts adding a secondary rack controller in these scenarios.

**Solution:**
To achieve HA for DHCP services in relayed subnets with MAAS, follow these steps:

1. **Understand MAAS DHCP configuration:**
   - MAAS typically allows for setting a primary and secondary rack controller for DHCP services directly connected to subnets. For relayed DHCP, both rack controllers must be aware of each other and be able to manage the DHCP relay for the target subnets.

2. **Update VLAN configuration via CLI:**
   - Use the MAAS CLI to configure the primary and secondary rack controllers for DHCP. Ensure both rack controllers are on the same VLAN where they can communicate effectively.

3. **Steps for Configuration:**

   **a. Identify VLAN and fabric IDs:**
   - Determine the fabric ID and VLAN ID for the subnets where DHCP needs to be relayed.

   **b. Configure primary and secondary rack controllers:**
   - Update the VLAN configuration to set the primary and secondary rack controllers.

   **Example commands:**
   ```bash
   maas $PROFILE vlan update $FABRIC_ID $VLAN_TAG dhcp_on=True \
       primary_rack=$PRIMARY_RACK_CONTROLLER \
       secondary_rack=$SECONDARY_RACK_CONTROLLER 
   ```

   **c. Configure DHCP relay:**
   - Use the CLI to set up the DHCP relay, ensuring both rack controllers can handle the relayed DHCP traffic.

   **Example command:**
   ```bash
   maas $PROFILE vlan update $FABRIC_ID $VLAN_ID_SRC relay_vlan=$VLAN_ID_TARGET
   ```

4. **Network considerations:**
   - Ensure that both rack controllers are connected to the same network infrastructure that supports VLANs and DHCP relay. They should be able to communicate over the same VLAN.

5. **HA setup with IP helpers:**
   - Configure IP helpers on your network switches to relay DHCP requests to both the primary and secondary rack controllers. This will ensure that if one rack controller goes down, the other can still handle DHCP requests.

6. **Verify configuration:**
   - After configuration, verify that both rack controllers are operational and can handle DHCP requests. Check the MAAS UI and logs to confirm there are no errors.

**Example workflow:**

1. **Get fabric and VLAN IDs:**
   ```bash
   maas $PROFILE fabrics read
   maas $PROFILE vlans read $FABRIC_ID
   ```

2. **Update VLAN for DHCP and relay:**
   ```bash
   maas $PROFILE vlan update $FABRIC_ID $VLAN_TAG dhcp_on=True \
       primary_rack=$PRIMARY_RACK_CONTROLLER \
       secondary_rack=$SECONDARY_RACK_CONTROLLER 

   maas $PROFILE vlan update $FABRIC_ID $VLAN_ID_SRC relay_vlan=$VLAN_ID_TARGET
   ```

3. **Configure IP helpers on network switch:**
   - Set IP helpers to point to both rack controllers' IP addresses on the network switch.

By following these steps, you can set up HA for DHCP in relayed subnets using MAAS, ensuring redundancy and high availability for your network configuration. This approach leverages both the MAAS CLI for detailed configuration and network infrastructure for effective DHCP relay.

## External DHCP configuration

**Problem:**
MAAS passes the commissioning and deployment stages but gets stuck in the "rebooting" stage with an `errno 101 network is unreachable` error. This issue may be related to the external DHCP configuration.

**Solution:**
To resolve issues related to external DHCP configuration in MAAS, follow these steps:

1. **Verify external DHCP server:**
   - Ensure that the external DHCP server is properly configured and operational on the subnet where the MAAS rack controller is connected.

2. **Enable network discovery:**
   - Make sure that network discovery is enabled in MAAS and that the rack controller is checking for external DHCP servers regularly.

3. **Check rackd logs:**
   - Inspect the rackd logs to verify that the rack controller is detecting the external DHCP server.

4. **Set static IP configuration:**
   - If using a virtual environment like OpenVSwitch, configure the server’s network settings to static IP addresses to avoid issues during boot.

5. **Detailed steps:**

   **a. Verify external DHCP server:**
   - Ensure that the external DHCP server is providing IP addresses correctly. Check if the external DHCP server's host is visible in the network discovery results.

   **b. Enable network discovery:**
   - Confirm that network discovery is enabled and set to check every 10 minutes.

   **Example:**
   ```bash
   maas admin subnet update <subnet-id> manage_discovery=true
   ```

   **c. Check rackd logs:**
   - Review the rackd logs to ensure the external DHCP server is being detected.

   **Example command:**
   ```bash
   tail -f /var/log/maas/rackd.log
   ```

   **d. Set static IP configuration:**
   - If the issue persists, configure the server's network settings to use a static IP address. This is particularly useful for virtual environments where DHCP might not function as expected.

   **Example netplan configuration (static IP):**
   ```yaml
   network:
     ethernets:
       ens16:
         addresses:
           - 192.168.30.20/23
         nameservers:
           addresses:
             - 192.168.30.1
             - 192.168.30.2
         routes:
           - to: default
             via: 192.168.30.10
     version: 2
   ```

   **Apply the changes:**
   ```bash
   sudo netplan apply
   ```

6. **Additional configuration:**
   - Ensure that the network interfaces and routing are correctly set up to allow communication with the MAAS server.

By following these steps, users can resolve the `errno 101 network is unreachable` error and ensure that the MAAS deployment process completes successfully. This approach addresses both DHCP configuration issues and network interface settings.

## Errno 101 - network is unreachable

**Problem:**
MAAS passes the commissioning and deployment stages but gets stuck in the "rebooting" stage with an `errno 101 network is unreachable` error. This occurs even with a standard installation without using a cloud-init script.

**Solution:**
This issue can often be related to external DHCP configuration or network misconfiguration. Here are steps to resolve the issue:

1. **Verify network configuration:**
   - Ensure that the network interfaces are correctly configured and can reach the MAAS metadata service.

2. **Check DHCP settings:**
   - Verify that DHCP is correctly set up and that the deployed machine receives the correct IP address and can communicate with the MAAS server.

3. **Modify cloud-init configuration:**
   - Ensure that the cloud-init configuration is correctly set up to avoid network-related issues during the rebooting stage.

4. **Detailed steps:**

   **a. Verify network interfaces:**
   - Check the network configuration on the deployed machine to ensure it has the correct IP settings and can reach the MAAS server.

   **Example commands:**
   ```bash
   ip addr show
   ip route show
   ```

   **b. Check DHCP and DNS configuration:**
   - Ensure that the DHCP server provides the correct IP address, subnet mask, gateway, and DNS settings to the deployed machine.

   **Example:**
   - Ensure that the machine receives an IP address in the correct subnet and can reach the MAAS server.

   **c. Modify cloud-init configuration:**
   - Modify the cloud-init configuration to disable attempts to contact the MAAS metadata server if it is not reachable.

   **Example cloud-init script:**
   ```bash
   #!/bin/bash
   # disable cloud-init network configuration after deployment
   sudo touch /etc/cloud/cloud-init.disabled
   ```

   **d. Update network configuration:**
   - Update the network configuration files on the deployed machine to ensure it uses the correct network settings.

   **Example netplan configuration:**
   ```yaml
   network:
     version: 2
     ethernets:
       enp1s0:
         dhcp4: true
         nameservers:
           addresses:
             - 8.8.8.8
             - 8.8.4.4
   ```

   **Apply the changes:**
   ```bash
   sudo netplan apply
   ```

5. **Check external DHCP configuration:**
   - If using an external DHCP server, ensure it is correctly configured to work with MAAS.

By following these steps, you can resolve the `errno 101 network is unreachable` error during the rebooting stage in MAAS, ensuring that the deployed machine can correctly communicate with the MAAS server and complete the deployment process.

## Post-deployment network issues

**Problem:**
Users face issues when switching the network interface of a deployed VM from an isolated deployment network to a bridged network, causing the VM to hang or freeze during boot.

**Solution:**
MAAS does not support reassigning a deployed machine to a new subnet directly. To address this, follow these steps:

1. **Avoid switching networks:**
   - To avoid issues, do not switch the VM's network interface after deployment. Instead, ensure that the VM is configured with the correct network settings from the start.

2. **Use a different router:**
   - If using an ISP router that does not support VLANs or advanced network settings, consider adding another router that can manage your home network effectively.

3. **Manual network configuration:**
   - If you must change the network interface, manually reconfigure the network settings on the VM after switching it to the bridged network.

4. **Detailed steps:**

   **a. Update cloud-init configuration:**
   - Ensure cloud-init does not attempt to contact the MAAS metadata server on the isolated network once the VM is moved.

   **Example script:**
   ```bash
   #!/bin/bash
   # disable cloud-init network configuration after deployment
   sudo touch /etc/cloud/cloud-init.disabled
   ```

   **b. Modify network configuration:**
   - Manually update the network configuration files on the VM to match the new network settings.

   **Example netplan configuration:**
   ```yaml
   network:
     version: 2
     ethernets:
       enp1s0:
         dhcp4: true
   ```

   **c. Apply network changes:**
   - Apply the changes to ensure the VM uses the new network configuration.

   **Example commands:**
   ```bash
   sudo netplan apply
   ```

5. **Add a custom router:**
   - Add a custom router in front of your ISP router to handle DHCP, VLANs, and other advanced network features.

   **Example setup:**
   - ISP router provides internet connectivity.
   - Custom router manages the internal network, DHCP, and VLANs.
   - Connect MAAS and VMs to the custom router.

By following these steps, users can manage network configurations more effectively and avoid issues related to switching network interfaces post-deployment. This approach ensures that VMs operate correctly within the desired network setup.

## Controller interface/network issues

**Problem:**
Users experience issues with MAAS using unintended network interfaces, particularly in multi-homed environments with Docker running on the same system. Specific challenges include unwanted interface detection, persistent subnets, and network discovery on unselected subnets.

**Solution:**
To address these issues and better manage network interfaces and subnets in MAAS, follow these steps:

1. **Bind MAAS to a single interface:**
   - While MAAS does not support binding to a single interface out of the box, you can control which interfaces MAAS services use by configuring individual components such as nginx, squid, and rsyslogd.

2. **Remove unwanted interfaces:**
   - Unfortunately, MAAS does not provide a direct way to remove interfaces through the GUI or CLI if they keep reappearing. However, you can take steps to ignore certain interfaces like `docker0`.

3. **Ignore certain interfaces:**
   - To ignore specific interfaces, you can use custom scripts or configuration files to exclude them from MAAS management.

4. **Configure network services:**
   - Customize the `named.conf` file to control DNS behavior and prevent unwanted DNS resolution on specific subnets.

5. **Detailed steps:**

   **a. Exclude Docker interface:**
   - Prevent MAAS from using the `docker0` interface by configuring the system to exclude it. Create a script to modify the network configuration.

   **Example script:**
   ```bash
   #!/bin/bash
   # Exclude docker0 interface from MAAS management
   INTERFACE="docker0"
   IP_ADDR=$(ip addr show $INTERFACE | grep "inet\b" | awk '{print $2}' | cut -d/ -f1)

   if [ -n "$IP_ADDR" ]; then
     echo "Exclude $INTERFACE ($IP_ADDR) from MAAS"
     ip link set $INTERFACE down
     ip addr flush dev $INTERFACE
   fi
   ```

   **b. Customize `named.conf`:**
   - Modify the `named.conf` file to prevent `named` from using specific subnets.

   **Example configuration:**
   ```bash
   options {
     ...
     listen-on { 127.0.0.1; <your-desired-interface-ip>; };
     ...
   };
   ```

   **c. Modify network configuration:**
   - Adjust the network configuration files to ensure MAAS services bind only to the desired interface.

   **Example for `nginx`:**
   ```bash
   server {
       listen <your-desired-interface-ip>:80;
       server_name maas.local;
       ...
   }
   ```

   **d. Disable unwanted subnet management:**
   - Use MAAS CLI to disable subnet management features on undesired subnets.

   **Example CLI commands:**
   ```bash
   maas admin subnet update <subnet-id> manage_allocation=false
   maas admin subnet update <subnet-id> manage_discovery=false
   maas admin subnet update <subnet-id> allow_dns=false
   ```

6. **Review and restart services:**
   - After making these changes, restart the MAAS services to apply the new configuration.

   **Restart MAAS services:**
   ```bash
   sudo systemctl restart maas-regiond
   sudo systemctl restart maas-rackd
   ```

By following these steps, users can better control which network interfaces and subnets are managed by MAAS, addressing issues related to unwanted interface usage and persistent subnets. This approach ensures that MAAS operates within the desired network configuration parameters.

## Adding VLAN interfaces to LXD VMs

**Problem:**
Users need to add VLAN interfaces to LXD VMs in MAAS but face limitations in modifying VMs post-creation and ensuring proper VLAN tagging.

**Solution:**
To add VLAN interfaces to LXD VMs, follow these steps:

1. **Configure VLAN interfaces on the VM host:**
   - The VM host should have VLAN interfaces configured to match the desired VLANs. This setup is done on the VM host at the OS level.

2. **Create bridges for VLAN interfaces:**
   - For each VLAN you want to expose to the VMs, create a bridge with the corresponding VLAN interface inside it. This allows the VMs to have untagged interfaces while ensuring that the traffic is tagged as it leaves the host.

3. **Step-by-step configuration:**

   **a. Add VLAN interface to MAAS rack controller:**
   - Add a VLAN interface to the MAAS rack controller and assign an IP address.
   - Restart MAAS to ensure it detects the new interface.
   - Add a subnet and VLAN in MAAS and enable DHCP on the VLAN.

   **Example:**
   ```bash
   # Add VLAN 500 to physical interface eth0
   sudo ip link add link eth0 name eth0.500 type vlan id 500
   sudo ip addr add 150.150.150.1/24 dev eth0.500
   sudo ip link set dev eth0.500 up
   ```

   **b. Create bridge interface:**
   - Create a bridge interface with the new VLAN interface as a member.
   
   **Example:**
   ```bash
   # Create bridge br500 and add eth0.500 as a member
   sudo brctl addbr br500
   sudo brctl addif br500 eth0.500
   sudo ip link set dev br500 up
   ```

   **c. Configure netplan (if using):**
   - Update the Netplan configuration to persist the VLAN and bridge setup.

   **Example:**
   ```yaml
   network:
     version: 2
     ethernets:
       eth0:
         dhcp4: true
     vlans:
       eth0.500:
         id: 500
         link: eth0
         addresses: [150.150.150.1/24]
     bridges:
       br500:
         interfaces: [eth0.500]
         dhcp4: no
   ```
   - Apply the Netplan configuration:
   ```bash
   sudo netplan apply
   ```

4. **Create VMs in MAAS:**
   - When creating VMs in MAAS, specify an interface and select the subnet corresponding to the desired VLAN. This ensures that the VMs are placed in the correct VLAN.

By following these steps, users can successfully add VLAN interfaces to LXD VMs in MAAS, ensuring proper VLAN tagging and network configuration. This setup allows VMs to operate with untagged interfaces while maintaining VLAN traffic tagging at the host level.

## Netplan configuration ignored when deploying a machine

**Problem:**
The Netplan configuration provided in the `cloud-init` script is being ignored, resulting in static IP settings instead of the desired DHCP configuration.

**Solution:**
To ensure the network configuration is correctly applied during deployment, follow these steps:

1. **Edit machine's interfaces in MAAS:**
   - Before deploying the machine, edit the machine's network interfaces in MAAS to set the IP mode to DHCP. This avoids the need for `cloud-init` to handle network configuration.

2. **Default DHCP for future machines:**
   - While it's not currently possible to make DHCP the default for all future machines in MAAS, you can include this configuration as part of your deployment automation.

3. **Custom `cloud-init` script:**
   - If you still prefer to use a `cloud-init` script, ensure it correctly sets up the network interfaces. However, due to current limitations, you may need a workaround to apply Netplan configuration.

4. **Workaround with bash script:**
   - Use a bash script within `cloud-init` to manually write the Netplan configuration and apply it. This can be done using the `runcmd` section of the `cloud-init` script.

   Example `cloud-init` script with bash workaround:
   ```yaml
   #cloud-config
   packages:
     - qemu-guest-agent
     - openssh-server

   users:
     - default
     - name: untouchedwagons
       gecos: untouchedwagons
       primary_group: untouchedwagons
       groups: sudo
       sudo: ALL=(ALL) NOPASSWD:ALL
       shell: /bin/bash
       ssh_import_id:
         - gh:UntouchedWagons

   runcmd:
     - [ systemctl, enable, --now, qemu-guest-agent ]
     - [ systemctl, enable, --now, ssh ]
     - |
       cat <<EOF > /etc/netplan/01-netcfg.yaml
       network:
         version: 2
         ethernets:
           ens18:
             match:
               macaddress: 'bc:24:11:e5:41:b7'
             dhcp4: true
             dhcp-identifier: mac
       EOF
       netplan apply
   ```

5. **Automation integration:**
   - Integrate these configurations into your existing automation framework (e.g., Ansible, Terraform) to ensure consistent and repeatable deployments.

By following these steps, you can ensure that the network configuration is applied correctly during machine deployment in MAAS, avoiding the issues with ignored Netplan settings.

## Pre-registering machine with IPMI address as FQDN

**Problem:**
Users encounter issues when trying to set the IPMI IP address field as an FQDN in MAAS. The machine gets registered with an IPv4 address associated with the FQDN, and the commissioning process does not complete.

**Solution:**
To address this issue and implement workarounds, follow these steps:

1. **Direct FQDN usage:**
   - Currently, MAAS does not support using FQDN directly for the `power_address` field. The `power_address` must be an IPv4 or IPv6 address as per the BMC enlistment documentation.

2. **Workarounds:**

   **a. Use Unique hostnames in the cluster:**
   - Ensure each machine in the cluster has a unique hostname. This can help in distinguishing and managing machines more effectively.

   **b. Assign FQDN management hostnames:**
   - Assign a unique management FQDN to the BMC/IPMI IP of each machine. For example, use `[hostname]-mgmt` as the FQDN for the IPMI address.

   **c. Update BMC IP using Python script:**
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

## Automating initial configuration settings for new machines

**Problem:**
Users need to manually configure network interfaces to DHCP and set power configurations to Manual for new machines added to MAAS, seeking a way to automate these settings.

**Solution:**
To automate the initial configuration settings for new machines in MAAS, follow these steps:

1. **Use preseed scripts:**
   - Utilize MAAS preseed scripts to automate network and power configurations. Preseed scripts can run commands during different stages of machine deployment.

2. **Curtin userdata:**
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

4. **Automate through hooks:**
   - Use MAAS hooks to trigger the script whenever a new machine is added. Hooks can be configured to execute scripts based on specific events.

5. **Check certified hardware:**
   - Ensure that the hardware being added to MAAS is certified and recognized by MAAS. This helps in automatic detection and configuration.

6. **Custom automation:**
   - Integrate these steps into your existing automation framework if you have one. Tools like Ansible, Terraform, or custom scripts can be used to manage these configurations.

By implementing these steps, users can automate the initial configuration settings for new machines in MAAS, reducing manual intervention and streamlining the deployment process.

## VLAN issues and rack controller configuration

**Problem:**
Users encounter issues with VLANs not being utilized on any rack controller, leading to problems with DHCP and network connectivity.

**Solution:**
To troubleshoot and resolve VLAN issues in MAAS, follow these steps:

1. **Configure VLAN interfaces:**
   - Ensure that VLAN interfaces are correctly configured on the rack controller with proper IDs, links, and IP addresses. Use `netplan` to apply configurations:
     ```bash
     sudo netplan apply
     ```

2. **Define subnets properly:**
   - Verify that subnets are defined correctly in MAAS for each VLAN. Check that the network, gateway, and DNS information are accurately entered.

3. **Physical connections:**
   - Confirm that the rack controller is physically connected to the appropriate networks and VLANs. If using a managed switch, ensure that ports are configured for the correct VLANs.

4. **Check MAAS logs:**
   - Review rack controller logs for any errors related to VLANs or DHCP:
     ```bash
     tail -f /var/log/maas/*.log
     ```

5. **Force network re-detection:**
   - Remove and re-add the rack controller in MAAS to force it to re-detect available networks and VLANs.

6. **Test DHCP on single VLAN:**
   - Enable DHCP on one VLAN at a time to identify any working configurations.

7. **Static IP address:**
   - Consider setting a static IP address on the VLAN interface to avoid DHCP conflicts.

8. **Restart rack controller:**
   - Restart the rack controller to ensure it reconnects correctly to MAAS and the VLANs.

9. **Reinstall rack controller:**
   - As a last resort, reinstall the rack controller following the official documentation to resolve any networking issues:
     - Ensure the rack controller is not installed on the same machine as the region controller.

10. **DHCP forwarding considerations:**
    - If using DHCP forwarding on the router, ensure that the rack servers on the VLAN can still communicate with the DHCP server.

By following these steps, users can troubleshoot and resolve issues with VLAN utilization on rack controllers in MAAS, ensuring proper network configuration and connectivity.

## Releasing old DHCP leases

**Problem:**
Deploying servers in MAAS results in an error stating "No more IPs available in subnet," despite having unused IP addresses.

**Solution:**
To release old DHCP leases and resolve IP allocation issues, follow these steps:

1. **Check for orphaned IP addresses:**
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

2. **Clean neighbor discoveries:**
   - Use the MAAS CLI to clear discovered neighbors, which might be causing IP conflicts:
     ```bash
     maas admin discoveries clear all=True -k
     ```

3. **Verify cleared discoveries:**
   - After clearing, check if the discoveries were successfully removed:
     ```bash
     maas admin discoveries read -k
     ```

4. **Clear ARP table (optional):**
   - If necessary, clear the ARP table on the Rack server to ensure no stale entries exist:
     ```bash
     arp -d [IP address]
     ```
   - Example to clear all entries:
     ```bash
     arp -d 172.21.68.79
     arp -d 172.21.68.69
     ```

5. **Run deployment again:**
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

1. **Understand loopback interface:**
   - Loopback interfaces do not require MAC addresses since they are used for internal routing within the node itself.

2. **Manually add loopback interface:**
   - After commissioning a node, manually add the loopback interface in MAAS.
   - If the MAAS web UI requires a MAC address for the loopback interface, use a placeholder value like `00:00:00:00:00:00` but ensure it does not conflict with other nodes.

3. **Avoid duplicate MAC addresses:**
   - Since MAAS does not support duplicate MAC addresses, manually configure the loopback interface on each node with a unique identifier or find a way to bypass the MAC address requirement.

4. **Alternative methods:**
   - If manually adding the loopback interface in MAAS is problematic, consider configuring the loopback interface outside of MAAS using post-deployment scripts.
   - Use MAAS to deploy the base configuration, then apply custom network configurations (including loopback interfaces) through cloud-init or other automation tools.

5. **Feedback from support:**
   - Internal support teams may have additional methods or patches to address this issue. Reach out to MAAS support for the latest solutions or updates regarding loopback interface configuration.

By following these steps, users can effectively configure loopback interfaces on nodes managed by MAAS, facilitating advanced network setups like L3 routing and BGP.

## Shrinking dynamic IP range

**Problem:**
Users may encounter errors when attempting to shrink the dynamic IP address range in MAAS due to conflicts with existing IP addresses or ranges.

**Solution:**
To troubleshoot and resolve this issue, follow these steps:

1. **Check current IP ranges and static addresses:**
   - Use the following SQL queries to check the current IP ranges and static IP addresses in the MAAS database:
     ```sql
     SELECT * FROM maasserver_iprange;
     SELECT * FROM maasserver_staticipaddress WHERE text(ip) LIKE '192.168.0.%' ORDER BY ip;
     ```
   - Identify any existing IP addresses that may conflict with the desired new range.

2. **Identify sticky addresses:**
   - Identify any sticky addresses within the current range that may cause conflicts. Sticky addresses are IP addresses allocated by MAAS DHCP that persist over reboots.

3. **Adjust IP range:**
   - Ensure that the new IP range does not overlap with any existing reserved or sticky addresses. Modify the start and end IP addresses to avoid conflicts.
   - Example: If the current range is 192.168.0.194 - 192.168.0.220 and sticky addresses occupy 192.168.0.195 - 192.168.0.211, adjust the range to avoid these addresses.

4. **Update MAAS configuration:**
   - After identifying a non-conflicting range, update the MAAS configuration to reflect the new IP range.

5. **Database updates:**
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