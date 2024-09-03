By default, MAAS logs a lot of runtime information to `systemd` log files, which are useful when things don’t work as expected. This guide will explain how to use these logs to manage your MAAS setup. We’ll cover version 3.5 and later, as well as earlier versions.

## MAAS 3.5 and later

Starting with version 3.5, MAAS uses systemd logs, replacing all the special-purpose log files used previously. Below are some examples of the commands you'll use to retrieve various log combinations.

### Common log commands for all services

You can use some generic commands to check logs for any MAAS service:

- **View recent logs:**
  ```bash
  journalctl -u maas-regiond --since "1 hour ago"
  ```
This command will show all the log entries referring to the `maas-regiond` service that were generated in the the last hour.

- **Filter logs by specific criteria:**
  ```bash
  journalctl -u maas-regiond -g "ERROR"
  ```
This command retrieves only those log lines that contain the word “ERROR,” which serves as a coarse issue filter. 

### Service-specific log commands

Each service in MAAS still writes its own log entries. Here’s how you can differentiate them.

#### 1. Regiond (Region Controller)

The Region Controller manages all MAAS web UI and API requests. If you’re having trouble with the web interface or API, these are the logs to check:

- **Snap installation:**
  ```bash
  journalctl -u snap.maas.pebble -t maas-regiond
  ```
- **Debian package:**
  ```bash
  journalctl -u maas-regiond
  ```

#### 2. Rackd (Rack Controller)

The Rack Controller communicates with machines, moderating network services like DHCP and DNS. If machines can’t get IP addresses or you have network problems, these logs may help:

- **Snap installation:**
  ```bash
  journalctl -u snap.maas.pebble -t maas-rackd
  ```
- **Debian package:**
  ```bash
  journalctl -u maas-rackd
  ```

#### 3. MAAS Agent

The MAAS Agent the machine life-cycle.  If commissioning or deployment fail, you’ll want to look here:

- **Snap installation:**
  ```bash
  journalctl -u snap.maas.pebble -t maas-agent
  ```
- **Debian package:**
  ```bash
  journalctl -u maas-agent
  ```

#### 4. API Server

If API requests seem to fail, check for these logs entries:

- **Snap installation:**
  ```bash
  journalctl -u snap.maas.pebble -t maas-apiserver
  ```
- **Debian package:**
  ```bash
  journalctl -u maas-apiserver
  ```

#### 5. HTTP (Nginx)

Web-server-related logs entries can be useful if you can't access the MAAS web interface:

- **Snap installation:**
  ```bash
  journalctl -u snap.maas.pebble -t maas-http
  ```
- **Debian package:**
  ```bash
  journalctl -u maas-http
  ```

### Examples and use cases

Here are more log examples:

#### Example 1: Troubleshooting a machine that won't boot

If a machine won't boot, you might want to look for `rackd` that point to network issues:

```bash
journalctl -u maas-rackd --since "2 hours ago"
```

For example, look for problems with DHCP or DNS.

#### Example 2: Debugging API issues

If the MAAS API won't respond, check the API server log entries:

```bash
journalctl -u maas-apiserver -g "500"
```

This particular filter shows any "500" error messages, which usually means there's a server problem.

#### Example 3: Monitoring changes over time

If you’re trying to see what changed over a given time period (e.g., since yesterday), you can check all logs for a specific service like this:

```bash
journalctl -u maas-regiond --since "24 hours ago"
```

This command may isolate any recent updates or changes that affected your system.

#### Example 4: Checking NTP synchronization issues

If your machines show incorrect times, NTP (Network Time Protocol) might be the issue, so check the **NTP (chrony)** logs:

- **Snap installation:**
  ```bash
  journalctl -u snap.maas.pebble -t chronyd
  ```
- **Debian package:**
  ```bash
  journalctl -u chrony
  ```

Look for entries related to time synchronization errors or failures.

### Advanced logging techniques

#### Filtering logs by machine or IP

Use a filtering tool (like the `-g` option to `journalctl`) to find log entries for a specific machine. For example:

```bash
journalctl -u maas-regiond --since "30 minutes ago" -g "MAAS_MACHINE_HOSTNAME=example-machine"
```

This command finds entries only for `example-machine` in the last 30 minutes. You can filter by anything that shows up in the log entries (like IP address).

#### Custom log searches with specific tags

Sometimes specific tags will help pinpoint issues quickly:

```bash
journalctl -u maas-agent --since "1 day ago" -g "MAAS_MACHINE_SYSLOG_TAG=commissioning"
```

This command searches the MAAS Agent logs for any commissioning-related tags.

### Logging for MAAS versions pre-3.5

Before version 3.5, MAAS used custom log files for each major component. Here’s how you can access those logs:

#### Regiond

- **Snap installation:**
  ```bash
  less /var/snap/maas/common/log/regiond.log
  ```
- **Debian package:**
  ```bash
  less /var/log/maas/regiond.log
  ```

#### Rackd

- **Snap installation:**
  ```bash
  less /var/snap/maas/common/log/rackd.log
  ```
- **Debian package:**
  ```bash
  less /var/log/maas/rackd.log
  ```

### Best practices for log management

#### Rotate logs

To keep your logs from filling your disk, rotate them regularly. Use the `logrotate` tool, which automatically rotates, compresses, and removes old logs.

#### Set up alerts

You can also set up alerts to notify you about specific log entries. Tools like Nagios or Prometheus can scan your logs and alert you if something goes wrong.

#### Secure logs

Make sure your log files are stored securely and have the right permissions. This prevents unauthorized users from accessing sensitive information.