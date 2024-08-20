## How to Provision Machines with MAAS: A Step-by-Step Guide

### Introduction

This guide explains how to provision machines using MAAS (Metal as a Service). Whether you're new to MAAS or need a refresher, this guide will walk you through the process of commissioning, deploying, and managing machines. We'll keep things simple and easy to follow.

### Commissioning Machines

**Commissioning** is the first step in getting a machine ready for deployment. It allows MAAS to gather information about the machine, such as its hardware details and network configuration.

#### How to Commission a Machine Using the MAAS UI

1. **Open the MAAS UI**: Navigate to the "Machines" tab.
2. **Select the Machine**: Choose the machine you want to commission.
3. **Start Commissioning**:
   - For MAAS 3.4: Go to *Actions* > *Commission*.
   - For other versions: Go to *Take action* > *Commission*.
4. **Set Optional Parameters**:
   - **Allow SSH access and prevent machine from powering off**: Keeps the machine on and enables SSH access.
   - **Retain network configuration**: Keeps any custom network settings.
   - **Retain storage configuration**: Keeps any custom storage settings.
   - **Update firmware**: Runs firmware update scripts.
   - **Configure HBA**: Runs scripts for configuring Host Bus Adapters (HBA).

5. **Run Hardware Tests**: You can choose hardware tests to run during commissioning.
6. **Commission the Machine**: Click *Commission machine*.

Once commissioning starts, the machine’s status will change to “Commissioning,” and after completion, it will be marked as "Ready." The results of the commissioning process will be available under the "Commissioning" tab for that machine.

#### Commissioning via the CLI

You can also commission a machine using the MAAS command-line interface (CLI):

```bash
maas $PROFILE machine commission $SYSTEM_ID
```

Replace `$PROFILE` with your MAAS profile and `$SYSTEM_ID` with the ID of the machine you want to commission. You can find the machine's `$SYSTEM_ID` with:

```bash
maas $PROFILE machines read | jq '.[] | .hostname, .system_id'
```

### Uploading and Managing Scripts

MAAS allows you to upload scripts that can be run during commissioning, testing, or other machine states.

#### Uploading Scripts via the UI

1. Go to *Settings* > *User scripts* > *Commissioning scripts*.
2. Click *Upload* and choose your script file.
3. Click *Upload* again to add the script to MAAS.

#### Uploading Scripts via the CLI

```bash
maas $PROFILE node-scripts create name=$SCRIPT_NAME script=$PATH_TO_SCRIPT type=commissioning
```

You can change the `type` to `testing` if needed.

### Deploying Machines

**Deployment** is the process of installing an operating system on a commissioned machine, making it ready for use.

#### Deploying Machines via the MAAS UI

1. **Select the Machine**: In the "Machines" tab, choose the machine(s) to deploy.
2. **Deploy the Machine**:
   - Go to *Take action* > *Deploy* > *Deploy machine*.
   - The machine's status will change to "Deploying" followed by the OS name (e.g., "Ubuntu 20.04 LTS") once the process is complete.

#### Deploying via the CLI

```bash
maas $PROFILE machine deploy $SYSTEM_ID
```

To deploy a machine as a KVM host:

```bash
maas $PROFILE machine deploy $SYSTEM_ID install_kvm=True
```

### Advanced Deployment Options

#### Deploying an Ephemeral OS

If you want to deploy an ephemeral (temporary) OS, select "Deploy in memory" during the deployment process. Note that networking for ephemeral OS images is only set up for Ubuntu images.

#### Setting Deployment Timeout

By default, MAAS will consider a deployment failed if it doesn’t complete within 30 minutes. You can change this timeout:

```bash
maas $PROFILE maas set-config name=node-timeout value=$NUMBER_OF_MINUTES
```

### Managing Network Links and Testing Connectivity

MAAS can test network connections and detect issues like slow or broken links.

#### Checking Network Links via the CLI

To check if network links are connected:

```bash
maas $PROFILE interfaces read $SYSTEM_ID | jq -r '(["LINK_NAME","LINK_CONNECTED?","LINK_SPEED", "I/F_SPEED"] | (., map(length*"-"))), (.[] | [.name, .link_connected, .link_speed, .interface_speed]) | @tsv' | column -t
```

This command shows whether each network link is connected and its speed.

#### Resetting Network Links

You can reset a network link if needed:

```bash
maas $PROFILE interface update $SYSTEM_ID $INTERFACE_ID link_connected=true
```

### Conclusion

Provisioning machines with MAAS involves commissioning, deploying, and managing machines and their networks. By following these steps, you can efficiently prepare your machines for use and ensure that your infrastructure is running smoothly. Whether you're using the MAAS UI or CLI, you have powerful tools at your disposal to manage your data center like a pro.
