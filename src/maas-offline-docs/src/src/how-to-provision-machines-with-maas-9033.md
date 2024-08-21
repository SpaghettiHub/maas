## Introduction

This guide explains how to provision machines using MAAS (Metal as a Service). Whether you're new to MAAS or need a refresher, this guide will walk you through the process of commissioning, deploying, and managing machines. We'll keep things simple and easy to follow.

## Commissioning machines

**Commissioning** is the first step in getting a machine ready for deployment. It allows MAAS to gather information about the machine, such as its hardware details and network configuration.

### How to commission a machine using the MAAS UI

1. **Open the MAAS UI**: Navigate to the "Machines" tab.
2. **Select the machine**: Choose the machine you want to commission.
3. **Start commissioning**:
   - For MAAS 3.4: Go to *Actions* > *Commission*.
   - For other versions: Go to *Take action* > *Commission*.
4. **Set optional parameters**:
   - **Allow SSH access and prevent the machine from powering off**: Keeps the machine on and enables SSH access.
   - **Retain network configuration**: Keeps any custom network settings.
   - **Retain storage configuration**: Keeps any custom storage settings.
   - **Update firmware**: Runs firmware update scripts.
   - **Configure HBA**: Runs scripts for configuring Host Bus Adapters (HBA).

5. **Run hardware tests**: You can choose hardware tests to run during commissioning.
6. **Commission the machine**: Click *Commission machine*.

Once commissioning starts, the machine’s status will change to “Commissioning,” and after completion, it will be marked as "Ready." The results of the commissioning process will be available under the "Commissioning" tab for that machine.

### Commissioning via the CLI

You can also commission a machine using the MAAS command-line interface (CLI):

```bash
maas $PROFILE machine commission $SYSTEM_ID
```

Replace `$PROFILE` with your MAAS profile and `$SYSTEM_ID` with the ID of the machine you want to commission. You can find the machine's `$SYSTEM_ID` with:

```bash
maas $PROFILE machines read | jq '.[] | .hostname, .system_id'
```

## Uploading and managing scripts

MAAS allows you to upload scripts that can be run during commissioning, testing, or other machine states.

### Uploading scripts via the UI

1. Go to *Settings* > *User scripts* > *Commissioning scripts*.
2. Click *Upload* and choose your script file.
3. Click *Upload* again to add the script to MAAS.

### Uploading scripts via the CLI

```bash
maas $PROFILE node-scripts create name=$SCRIPT_NAME script=$PATH_TO_SCRIPT type=commissioning
```

You can change the `type` to `testing` if needed.

## Deploying machines

**Deployment** is the process of installing an operating system on a commissioned machine, making it ready for use.

### Deploying machines via the MAAS UI

1. **Select the machine**: In the "Machines" tab, choose the machine(s) to deploy.
2. **Deploy the machine**:
   - Go to *Take action* > *Deploy* > *Deploy machine*.
   - The machine's status will change to "Deploying" followed by the OS name (e.g., "Ubuntu 20.04 LTS") once the process is complete.

### Deploying via the CLI

```bash
maas $PROFILE machine deploy $SYSTEM_ID
```

To deploy a machine as a KVM host:

```bash
maas $PROFILE machine deploy $SYSTEM_ID install_kvm=True
```

## Advanced deployment options

### Deploying an ephemeral OS

If you want to deploy an ephemeral (temporary) OS, select "Deploy in memory" during the deployment process. Note that networking for ephemeral OS images is only set up for Ubuntu images.

### Setting deployment timeout

By default, MAAS will consider a deployment failed if it doesn’t complete within 30 minutes. You can change this timeout:

```bash
maas $PROFILE maas set-config name=node-timeout value=$NUMBER_OF_MINUTES
```

## Managing network links and testing connectivity

MAAS can test network connections and detect issues like slow or broken links.

### Checking network links via the CLI

To check if network links are connected:

```bash
maas $PROFILE interfaces read $SYSTEM_ID | jq -r '(["LINK_NAME","LINK_CONNECTED?","LINK_SPEED", "I/F_SPEED"] | (., map(length*"-"))), (.[] | [.name, .link_connected, .link_speed, .interface_speed]) | @tsv' | column -t
```

This command shows whether each network link is connected and its speed.

### Resetting network links

You can reset a network link if needed:

```bash
maas $PROFILE interface update $SYSTEM_ID $INTERFACE_ID link_connected=true
```

## Tips, tricks, and traps

There are some occasional issues with commissioning and deployment.  This section covers some of the most common items.

### Resolving "cloud-init data source not found" during MAAS deployment

When deploying an OS or a Juju controller on a node using MAAS, you might encounter the error "cloud-init data source not found." This section provides a step-by-step guide to troubleshoot and resolve this issue, ensuring successful deployment.

#### Step 1: Verify connectivity to MAAS metadata server

Cloud-init relies on the MAAS metadata server to retrieve essential information such as SSH keys and user data. If the node cannot reach this server, the deployment will fail.

- **Ensure DNS configuration:**
  - Verify that the DNS server for your environment is set to the MAAS region or rack controller IP.
  - In the MAAS UI, navigate to the subnet summary and ensure that the "allow DNS resolution" option is enabled and configured correctly with the MAAS server’s IP.

  **Command:**
  ```bash
  maas $PROFILE subnet update $SUBNET_ID dns_servers="[$MAAS_IP]"
  ```

#### Step 2: Address MAAS services or proxy issues

Sometimes, issues with proxy services like Squid or BIND can cause the deployment to fail. Toggling the proxy settings might resolve the problem.

- **Toggle proxy configuration:**
  - Change the proxy settings from ‘don’t use a proxy’ to ‘MAAS built-in’ or vice versa to check if it resolves the issue.

  **Commands:**
  ```bash
  maas $PROFILE maas set-config name=http_proxy value="http://proxy.example.com:8000/"
  maas $PROFILE maas set-config name=http_proxy value=""
  ```

#### Step 3: Check network configuration and connectivity

Proper network setup is crucial for the MAAS metadata service to function correctly.

- **Verify network setup:**
  - Ensure that the network configuration allows proper routing to the MAAS metadata service.
  - Check for firewalls or other network issues that might be blocking access to the MAAS server.

#### Step 4: Restart MAAS services

If the issue persists, restarting the MAAS services can often resolve intermittent problems.

- **Restart services:**
  - Use the following command to restart the MAAS services.

  **Command:**
  ```bash
  sudo systemctl restart maas-rackd maas-regiond
  ```

#### Step 5: Verify BIOS configuration

Incorrect BIOS settings, especially those related to network boot and BMCs, can cause deployment issues.

- **Check and update BIOS settings:**
  - Ensure that the BIOS settings on the nodes are consistent and correctly configured for network boot.

#### Step 6: Validate subnet and IP configuration

Conflicting, overlapping, or duplicate subnets can disrupt the deployment process.

- **Check subnet configurations:**
  - In the MAAS UI, verify that the subnet and IP configurations are correct and free of conflicts.

#### Step 7: Analyze logs

If the problem is still unresolved, logs can provide detailed insights.

- **Check MAAS and cloud-init logs:**
  - Review the logs for any errors or warnings that might indicate the root cause of the issue. Refer to the MAAS logging documentation for specific commands.

  **Example commands:**
  ```bash
  # Example command to check MAAS logs
  less /var/log/maas/*.log

  # Example command to check cloud-init logs
  less /var/log/cloud-init.log
  ```

#### Community tips

- Some users resolved the issue by adding a dynamic reserved range to the IPv6 subnet.
- Make sure the DNS IP in the subnet summary is set to the MAAS region/rack servers’ IP.

By following these troubleshooting steps, you should be able to resolve the "cloud-init data source not found" error and successfully deploy your OS using MAAS.

### How to resolve DHCP services not starting in MAAS

If you're having trouble with the DHCP services in MAAS not starting, especially after fixing memory and disk problems, this guide will help you troubleshoot and resolve the issue.

#### Step 1: Check MAAS logs

Start by looking at the MAAS logs to find any errors related to DHCP services.

1. **Access MAAS logs:**
   - Look for errors in the MAAS logs that might explain why the DHCP services aren’t starting.

   **Example log entry:**
   ```plaintext
   2021-06-09 08:58:43 maasserver.rack_controller: [critical] Failed configuring DHCP on rack controller 'id:1'.
   File "/snap/maas/12555/lib/python3.8/site-packages/maasserver/dhcp.py", line 864, in configure_dhcp
   config = yield deferToDatabase(get_dhcp_configuration, rack_controller)
   ...
   ```

#### Step 2: Check for configuration corruption

Problems might be due to configuration corruption from earlier memory and disk issues.

1. **Verify subnet and fabric configuration:**
   - Make sure subnets are correctly assigned to the right fabrics in the MAAS UI.

   **Steps:**
   - Go to the "Subnets" section in the MAAS UI.
   - Open the configuration page for each subnet.
   - Reassign the subnet to the correct fabric if needed.

#### Step 3: Restart MAAS services

After fixing any misconfigurations, restart the MAAS services to apply the changes.

**Commands:**
```bash
sudo systemctl restart maas-rackd
sudo systemctl restart maas-regiond
```

#### Step 4: Clean up proxy cache (if applicable)

If you use a proxy, clearing the proxy cache might help resolve issues related to DHCP services.

**Commands:**
```bash
sudo mv /var/snap/maas/common/proxy /var/snap/maas/common/proxy.old
sudo mkdir -p /var/snap/maas/common/proxy
sudo chown -R proxy:proxy /var/snap/maas/common/proxy
sudo chmod -R 0750 /var/snap/maas/common/proxy
sudo systemctl restart maas-proxy
```

#### Step 5: Verify DHCP settings

Make sure the DHCP settings are correct in the MAAS UI.

1. **Check DHCP configuration:**
   - Ensure that DHCP is enabled on the correct subnets.

#### Step 6: Check and repair the database

The problem might be related to the MAAS database. Checking and repairing the database can help fix these issues.

**Commands:**
```bash
sudo maas-region dbshell
# Inside the database shell
VACUUM FULL;
```

By following these steps, you should be able to diagnose and resolve issues that are preventing the DHCP services from starting in MAAS.
## Conclusion

Provisioning machines with MAAS involves commissioning, deploying, and managing machines and their networks. By following these steps, you can efficiently prepare your machines for use and ensure that your infrastructure is running smoothly. Whether you're using the MAAS UI or CLI, you have powerful tools at your disposal to manage your data center like a pro.