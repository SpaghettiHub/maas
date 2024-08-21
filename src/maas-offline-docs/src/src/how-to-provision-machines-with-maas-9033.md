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

** NEXT clean up how-to version of "Unable to commission server - cloud-init error: 'Can not apply stage final, no datasource found!'" :pulse2417:
SCHEDULED: <2024-08-21 Wed>
### Resolving cloud-init error: “Can not apply stage final, no datasource found!”

When you try to commission servers in a MAAS 3.1 environment, you might see the cloud-init error "Can not apply stage final, no datasource found!" This problem stops the commissioning process, even though your current OpenStack environment is working fine.

To fix this issue, follow these steps:

First, check the network configuration. Make sure the new servers are set up correctly to connect to the MAAS server. Look for network issues that might block access to the necessary metadata. You can check the network interfaces with `ip a`, check the routing with `ip route`, and check DNS resolution with `nslookup maas-server-ip`.

Next, review the MAAS logs for any errors or warnings that could explain the issue.

Then, check the cloud-init configuration. Make sure the configuration is correct and that the datasource is properly defined. If needed, update the cloud-init configuration to ensure it detects the datasource. You can edit the cloud-init configuration file using `sudo nano /etc/cloud/cloud.cfg` and make sure the datasource list includes MAAS, like this:

```yaml
datasources:
  - MAAS
```

After you verify and update the configurations, try recommissioning the server. You can do this through the MAAS UI or by using the CLI command:

```bash
maas $PROFILE machine commission $SYSTEM_ID
```

If the problem continues, try resetting the node and then recommissioning it. This can help fix issues related to temporary network or configuration problems. You can reset the node with these commands:

```bash
maas $PROFILE machine release $SYSTEM_ID
maas $PROFILE machine commission $SYSTEM_ID
```

Make sure both MAAS and cloud-init are up to date, as updates often fix bugs and improve performance. You can update MAAS with `sudo snap refresh maas` and update cloud-init with:

```bash
sudo apt-get update
sudo apt-get install --only-upgrade cloud-init
```

Finally, if the issue still isn’t resolved, check the official MAAS and cloud-init documentation for more troubleshooting tips. You might also want to ask for help from the MAAS community.

By following these steps, you should be able to fix the "Can not apply stage final, no datasource found!" error and successfully commission your servers in MAAS.

## Conclusion

Provisioning machines with MAAS involves commissioning, deploying, and managing machines and their networks. By following these steps, you can efficiently prepare your machines for use and ensure that your infrastructure is running smoothly. Whether you're using the MAAS UI or CLI, you have powerful tools at your disposal to manage your data center like a pro.
