import os
import gzip
import glob
import logging
import subprocess
import tempfile
from typing import Optional, Tuple, List, Dict
from datetime import datetime
from pick import pick
from ..config.schemas import FullConfig
from ..utils import ssh
from .mysql_utils import get_remote_mysql_version
from ..utils.sanitize import sanitize_command
from .db_info import read_db_info_header

logger = logging.getLogger("MySQLBackup.Recovery")


def list_available_backups(config: FullConfig) -> List[Dict]:
    """列出指定配置的所有可用备份"""
    backup_dir = config.backup.backup_dir
    if not os.path.exists(backup_dir):
        return []

    # 搜索所有备份文件
    backup_pattern = os.path.join(
        backup_dir, f"backup_{config.config_name}_*.sql*")
    backup_files = glob.glob(backup_pattern)

    # 解析并排序备份信息
    backups = []
    for file_path in backup_files:
        try:
            filename = os.path.basename(file_path)
            # 解析文件名中的时间戳部分
            # 从文件名中提取日期部分，格式应该是: backup_配置名_数据库名_2025-07-30_00-35-23.sql[.gz]
            name_parts = filename.split('_')
            if len(name_parts) >= 5:
                date_str = name_parts[-2]  # 取倒数第二个部分作为日期
                time_str = name_parts[-1].replace('.sql.gz', '').replace('.sql', '')  # 取最后一个部分作为时间
                full_timestamp_str = f"{date_str}_{time_str}"
                timestamp = datetime.strptime(full_timestamp_str, "%Y-%m-%d_%H-%M-%S")

                # 获取文件大小
                size_mb = os.path.getsize(file_path) / (1024 * 1024)

            backups.append({
                'file_path': file_path,
                'filename': filename,
                'timestamp': timestamp,
                'size_mb': size_mb
            })
        except Exception as e:
            logger.warning(f"解析备份文件失败: {file_path}, 错误: {str(e)}")
            continue

    # 按时间戳倒序排序
    return sorted(backups, key=lambda x: x['timestamp'], reverse=True)


def select_config_interactive(configs: List[FullConfig]) -> Optional[FullConfig]:
    """交互式选择配置"""
    title = "请选择要恢复的配置 (使用上下方向键选择，Enter确认):"
    options = [cfg.config_name for cfg in configs]

    try:
        _, index = pick(options, title, indicator="→")
        return configs[index]
    except KeyboardInterrupt:
        return None


def select_backup_interactive(backups: List[Dict]) -> Optional[str]:
    """交互式选择备份文件"""
    if not backups:
        print("没有找到可用的备份文件")
        return None

    title = "请选择要恢复的备份文件 (使用上下方向键选择，Enter确认):"
    options = []

    # 准备显示选项
    for backup in backups:
        timestamp_str = backup['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        size_str = f"{backup['size_mb']:.2f} MB"
        option = f"{backup['filename']}\n  创建时间: {timestamp_str}\n  文件大小: {size_str}"
        options.append(option)

    try:
        _, index = pick(options, title, indicator="→")
        return backups[index]['file_path']
    except KeyboardInterrupt:
        return None


def perform_recovery(config: FullConfig, backup_file: str, args) -> bool:
    """执行数据库恢复操作"""
    if not os.path.exists(backup_file):
        logger.error(f"备份文件不存在: {backup_file}")
        return False

    config_name = config.config_name
    logger.info(f"[{config_name}] 开始恢复操作: {backup_file}")

    ssh_client = None
    temp_file = None

    try:
        # SSH隧道处理
        if config.ssh and config.ssh.enabled:
            if not ssh.check_ssh_connectivity(config.ssh.host, config.ssh.port):
                raise Exception("SSH服务器不可达")

            ssh_client = ssh.setup_ssh_tunnel(config.ssh)
            if not ssh_client:
                raise Exception("SSH隧道建立失败，无法继续恢复")

        # 如果是gz文件，先解压
        if backup_file.endswith('.gz'):
            temp_fd, temp_file = tempfile.mkstemp(suffix='.sql')
            os.close(temp_fd)

            with gzip.open(backup_file, 'rb') as f_in:
                with open(temp_file, 'wb') as f_out:
                    f_out.write(f_in.read())

            actual_backup_file = temp_file
        else:
            actual_backup_file = backup_file

        # 获取MySQL服务器版本
        server_version = get_remote_mysql_version(config, args)

        # 读取备份文件中的数据库参数
        db_info = {}
        if actual_backup_file.endswith('.gz'):
            # 如果是gz文件，我们已经解压到temp_file了
            db_info = read_db_info_header(temp_file)
        else:
            db_info = read_db_info_header(actual_backup_file)

        # 构建mysql命令
        mysql_path = os.path.join(config.backup.mysql_bin_dir, "mysql.exe")

        # 构建初始化命令
        init_commands = []
        if db_info:
            # 使用备份文件中记录的参数
            if 'character_set_server' in db_info:
                init_commands.append(f"SET GLOBAL character_set_server='{db_info['character_set_server']}'")
            if 'character_set_database' in db_info:
                init_commands.append(f"SET character_set_database='{db_info['character_set_database']}'")
            if 'collation_server' in db_info:
                init_commands.append(f"SET GLOBAL collation_server='{db_info['collation_server']}'")
            if 'innodb_file_format' in db_info:
                init_commands.append(f"SET GLOBAL innodb_file_format='{db_info['innodb_file_format']}'")
            if 'innodb_large_prefix' in db_info:
                init_commands.append(f"SET GLOBAL innodb_large_prefix={db_info['innodb_large_prefix']}")
            if 'innodb_file_per_table' in db_info:
                init_commands.append(f"SET GLOBAL innodb_file_per_table={db_info['innodb_file_per_table']}")
            if 'sql_mode' in db_info:
                init_commands.append(f"SET GLOBAL sql_mode='{db_info['sql_mode']}'")
        
        # 如果没有读到参数，使用默认值
        if not init_commands:
            init_commands = [
                "SET innodb_strict_mode=0",
                "SET GLOBAL innodb_file_per_table=1",
                "SET GLOBAL innodb_file_format=Barracuda",
                "SET GLOBAL innodb_large_prefix=1"
            ]

        cmd = [
            mysql_path,
            f"--host={config.database.host}",
            f"--port={config.database.port}",
            f"--user={config.database.user}",
            f"--password={config.database.password}",
            f"--default-character-set={db_info.get('character_set_server', 'utf8mb4')}",
            f"--init-command={';'.join(init_commands)}",
            "--max-allowed-packet=1G"
        ]

        # 使用配置文件认证
        if config.database.defaults_file:
            cmd.insert(1, f"--defaults-file={config.database.defaults_file}")
            cmd = [c for c in cmd if not c.startswith("--password")]

        # 从备份文件读取数据库参数
        db_info = read_db_info_header(backup_file)
        if db_info:
            logger.info(f"[{config_name}] 从备份文件读取到数据库参数")
            
            # 构建初始化命令
            init_commands = []
            if 'character_set_server' in db_info:
                init_commands.append(f"SET GLOBAL character_set_server='{db_info['character_set_server']}'")
            if 'character_set_database' in db_info:
                init_commands.append(f"SET character_set_database='{db_info['character_set_database']}'")
            if 'collation_server' in db_info:
                init_commands.append(f"SET GLOBAL collation_server='{db_info['collation_server']}'")
            if 'innodb_file_format' in db_info:
                init_commands.append(f"SET GLOBAL innodb_file_format='{db_info['innodb_file_format']}'")
            if 'innodb_large_prefix' in db_info:
                init_commands.append(f"SET GLOBAL innodb_large_prefix={db_info['innodb_large_prefix']}")
            if 'innodb_file_per_table' in db_info:
                init_commands.append(f"SET GLOBAL innodb_file_per_table={db_info['innodb_file_per_table']}")
            if 'sql_mode' in db_info:
                init_commands.append(f"SET GLOBAL sql_mode='{db_info['sql_mode']}'")

            # 添加参数到mysql命令
            if init_commands:
                cmd.append(f"--init-command={';'.join(init_commands)}")
                cmd.append(f"--default-character-set={db_info.get('character_set_server', 'utf8mb4')}")

        # 记录脱敏后的命令
        sanitized_cmd = sanitize_command(cmd, args.debug)
        logger.info(f"[{config_name}] 执行恢复命令: {' '.join(sanitized_cmd)}")

        # 执行恢复
        with open(actual_backup_file, 'rb') as f:
            process = subprocess.Popen(
                cmd,
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"[{config_name}] 恢复失败: {stderr.strip()}")
            return False

        logger.info(f"[{config_name}] 恢复成功完成")
        return True

    except Exception as e:
        logger.exception(f"[{config_name}] 恢复过程中发生异常: {str(e)}")
        return False

    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass

        if ssh_client:
            ssh_client.close()
