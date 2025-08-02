# MySQL Backup Tool

[English](README.md) | [简体中文](README.zh-CN.md)

An automated MySQL database backup tool with support for multiple database configurations, SSH tunneling, and email notifications.

## Features

- Multiple database backup configurations
- SSH tunnel support for remote backups
- Smart error handling with automatic problem table skipping
- Email notifications (success/failure/in-progress)
- Automatic backup file cleanup
- Flexible configuration inheritance mechanism

## Configuration

Configuration files are divided into two layers:
1. Project configuration (config.ini): Global default settings
2. Business configuration (backup_configs/*.ini): Specific database backup settings

### Project Configuration (config.ini)

```ini
[backup]
mysql_bin_dir = C:\Program Files\MySQL\MySQL Server 8.0\bin  # MySQL client directory
days_to_keep = 7                # Days to keep backups
backup_time = 23:00            # Default backup time
report_time = 09:00            # Default report time
backup_root_path = backups     # Backup root directory (optional)

[email]
enabled = true
smtp_server = smtp.example.com
smtp_port = 465
smtp_user = user@example.com
smtp_password = your_password
sender_name = MySQL Backup System
from_addr = user@example.com
to_addrs = ["user1@example.com", "user2|John"]  # Supports "email|name" format
copy_to = ["user3@example.com"]                # CC list
additional_to = ["user4@example.com"]          # BCC list
```

### Business Configuration (backup_configs/your_db.ini)

```ini
[database]
host = localhost               # Database host
port = 3306                   # Database port
user = root                   # Database user
password = your_password      # Database password
database_names = db1,db2      # Databases to backup, comma-separated
defaults_file = my.cnf        # MySQL defaults file (optional)

[backup]
enabled = true                # Enable backup
backup_dir = mysql            # Backup subdirectory
days_to_keep = 30            # Override project retention days
backup_time = 01:00          # Override project backup time
report_time = 09:30          # Override project report time

[email]                      # Optional, override project email settings
enabled = true
to_addrs = ["dba@example.com"]
copy_to = ["leader@example.com"]

[ssh]                        # Optional, SSH tunnel configuration
enabled = true
host = remote.example.com    # SSH server address
port = 22                    # SSH port
user = ssh_user             # SSH username
password = ssh_password     # SSH password
private_key = ~/.ssh/id_rsa # Or use private key (choose one)
local_bind_port = 3307      # Local binding port
remote_bind_host = 127.0.0.1 # Remote binding host
remote_bind_port = 3306     # Remote binding port
```

## Configuration Inheritance

1. Business configurations can inherit and override project configuration
2. Unspecified options in business configuration will use project defaults
3. Some fields (like mysql_bin_dir) can only be set in project configuration

## Usage

```bash
# Execute backup
python main.py --backup [--config config_name]

# Check backup status
python main.py --check [--config config_name]

# Create scheduled tasks
Windows: python main.py --schedule    # Requires administrator privileges
Linux:   python main.py --schedule    # Requires crontab permissions

# Interactive database recovery
python main.py --recovery
```

### Scheduled Tasks
- On Windows: Creates tasks in Windows Task Scheduler
- On Linux: Creates crontab entries
- Tasks created:
  - Backup task: Runs daily backup at configured time
  - Status check task: Checks backup status at configured time
- Automatically removes old tasks before creating new ones

### Command Line Arguments

- `--backup`: Execute backup operation
- `--check`: Check backup status and send alerts
- `--schedule`: Create Windows scheduled task (requires admin privileges)
- `--recovery`: Interactive database backup recovery
- `--debug`: Debug mode, show full commands (unmasked)
- `--config`: Specify configuration file pattern, optional
  - No specification: Process all .ini configs
  - Specific file: e.g., `Your_CRM`
  - Multiple files: Comma-separated, e.g., `Your_CRM,Your_OA`
  - Wildcards supported: e.g., `backup_configs/*.ini`

### Examples

```bash
# Backup all configured databases
python main.py --backup

# Backup a specific database
python main.py --backup --config Your_CRM

# Check specific database backup status
python main.py --check --config Your_CRM

# Create Windows scheduled task
python main.py --schedule

# Interactive database recovery
python main.py --recovery

# Execute backup in debug mode (show full commands)
python main.py --backup --debug
```

## Email Notifications

The tool sends email notifications in the following cases:
1. Backup complete (success/partial success)
2. Backup failure
3. Backup in progress (prevents duplicate execution)

Notifications include:
- Backup status (complete success/partial success/failure)
- Backup file information (path, size)
- Skipped tables (if any)
- Error messages (if any)
