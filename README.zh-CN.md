# MySQL Backup Tool

[English](README.md) | [简体中文](README.zh-CN.md)

一个用于自动化MySQL数据库备份的工具，支持多数据库配置、SSH隧道、邮件通知等功能。

## 功能特点

- 支持多个数据库的独立备份配置
- 支持通过SSH隧道进行远程备份
- 智能错误处理，自动跳过问题表
- 支持邮件通知（成功/失败/进行中）
- 支持备份文件的自动清理
- 灵活的配置继承机制

## 配置说明

配置文件分为两层：
1. 项目配置（config.ini）：全局默认配置
2. 业务配置（backup_configs/*.ini）：具体数据库的备份配置

### 项目配置文件 (config.ini)

```ini
[backup]
mysql_bin_dir = C:\Program Files\MySQL\MySQL Server 8.0\bin  # MySQL客户端目录
days_to_keep = 7                # 备份保留天数
backup_time = 23:00            # 默认备份时间
report_time = 09:00            # 默认报告时间
backup_root_path = backups     # 备份根目录（可选）

[email]
enabled = true
smtp_server = smtp.example.com
smtp_port = 465
smtp_user = user@example.com
smtp_password = your_password
sender_name = MySQL备份系统
from_addr = user@example.com
to_addrs = ["user1@example.com", "user2|张三"]  # 支持"邮箱|姓名"格式
copy_to = ["user3@example.com"]                # 抄送列表
additional_to = ["user4@example.com"]          # 密送列表
```

### 业务配置文件 (backup_configs/your_db.ini)

```ini
[database]
host = localhost               # 数据库主机
port = 3306                   # 数据库端口
user = root                   # 数据库用户
password = your_password      # 数据库密码
database_names = db1,db2      # 要备份的数据库，多个用逗号分隔
defaults_file = my.cnf        # MySQL默认配置文件（可选）

[backup]
enabled = true                # 是否启用备份
backup_dir = mysql            # 备份子目录
days_to_keep = 30            # 覆盖项目配置的保留天数
backup_time = 01:00          # 覆盖项目配置的备份时间
report_time = 09:30          # 覆盖项目配置的报告时间

[email]                      # 可选，覆盖项目邮件配置
enabled = true
to_addrs = ["dba@example.com"]
copy_to = ["leader@example.com"]

[ssh]                        # 可选，配置SSH隧道
enabled = true
host = remote.example.com    # SSH服务器地址
port = 22                    # SSH端口
user = ssh_user             # SSH用户名
password = ssh_password     # SSH密码
private_key = ~/.ssh/id_rsa # 或使用私钥（与密码二选一）
local_bind_port = 3307      # 本地绑定端口
remote_bind_host = 127.0.0.1 # 远程绑定主机
remote_bind_port = 3306     # 远程绑定端口
```

## 配置继承关系

1. 业务配置可以继承和覆盖项目配置
2. 未在业务配置中指定的选项将使用项目配置中的默认值
3. 某些字段（如mysql_bin_dir）只能在项目配置中设置

## 使用方法

```bash
# 执行备份
python main.py --backup [--config 配置文件名]

# 检查备份状态
python main.py --check [--config 配置文件名]

# 创建计划任务
Windows: python main.py --schedule    # 需要管理员权限
Linux:   python main.py --schedule    # 需要 crontab 权限

# 交互式恢复数据库备份
python main.py --recovery
```

### 计划任务说明
- Windows 系统：在任务计划程序中创建任务
- Linux 系统：在 crontab 中创建定时任务
- 创建的任务：
  - 备份任务：按配置的时间每天执行备份
  - 状态检查任务：按配置的时间检查备份状态
- 创建新任务时会自动清理旧的任务

### 命令行参数

- `--backup`：执行备份操作
- `--check`：检查备份状态并发送警报
- `--schedule`：创建Windows计划任务（需要管理员权限）
- `--recovery`：交互式恢复数据库备份
- `--debug`：调试模式，显示完整命令（不脱敏）
- `--config`：指定配置文件模式，可选参数
  - 不指定：处理所有.ini配置
  - 指定文件名：如 `Your_CRM`，处理对应配置
  - 多个文件：用逗号分隔，如 `Your_CRM,Your_OA`
  - 支持通配符：如 `backup_configs/*.ini`

### 示例

```bash
# 备份所有配置的数据库
python main.py --backup

# 备份特定的数据库
python main.py --backup --config Your_CRM

# 检查特定数据库的备份状态
python main.py --check --config Your_CRM

# 创建Windows计划任务
python main.py --schedule

# 交互式恢复数据库备份
python main.py --recovery

# 调试模式执行备份（显示完整命令）
python main.py --backup --debug
```

## 邮件通知

工具会在以下情况发送邮件通知：
1. 备份完成（成功/部分成功）
2. 备份失败
3. 备份进行中（防止重复执行）

通知包含以下信息：
- 备份状态（完全成功/部分成功/失败）
- 备份文件信息（路径、大小）
- 跳过的表（如果有）
- 错误信息（如果有）
