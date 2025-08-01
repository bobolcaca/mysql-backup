import os
import subprocess
import re
import logging

from ..utils import sanitize

logger = logging.getLogger("MySQLBackup.MySQLUtils")

def get_mysqldump_version(mysqldump_path: str):
    """获取mysqldump客户端版本"""
    try:
        result = subprocess.run(
            [mysqldump_path, "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        version_str = result.stdout.strip()
        # 解析版本号
        match = re.search(r'Ver\s+(\d+)\.(\d+)\.(\d+)', version_str)
        if match:
            return tuple(map(int, match.groups()))
        return (0, 0, 0)
    except Exception as e:
        logger.error(f"获取mysqldump版本失败: {str(e)}")
        return (0, 0, 0)

def check_missing_tables(config, args, database_name: str) -> list:
    """预检查数据库中不存在的表，避免多次重试
    
    Args:
        config: 配置对象
        args: 命令行参数
        database_name: 数据库名称
    
    Returns:
        list: 不存在的表名列表，格式为 database.table
    """
    try:
        mysql_path = os.path.join(config.backup.mysql_bin_dir, "mysql.exe")
        cmd = [
            mysql_path,
            f"--host={config.database.host}",
            f"--port={config.database.port}",
            f"--user={config.database.user}",
            f"--password={config.database.password}",
            "--silent",
            "--skip-column-names",
            database_name,
            "--execute=SHOW TABLES"
        ]

        if config.database.defaults_file:
            cmd.insert(1, f"--defaults-file={config.database.defaults_file}")
            cmd = [c for c in cmd if not c.startswith("--password")]

        # 记录脱敏后的命令
        sanitized_cmd = sanitize.sanitize_command(cmd, args.debug)
        logger.info(f"[{database_name}] 检查表列表命令: {' '.join(sanitized_cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        # 获取SHOW TABLES列出的表
        tables = [table for table in result.stdout.strip().split('\n') if table]
        
        # 检查每个表是否真实可访问
        missing_tables = []
        for table in tables:
            # 尝试获取表的创建语句，这会验证表是否真实可访问
            cmd_check = [
                mysql_path,
                f"--host={config.database.host}",
                f"--port={config.database.port}",
                f"--user={config.database.user}",
                f"--password={config.database.password}",
                "--silent",
                "--skip-column-names",
                database_name,
                f"--execute=SHOW CREATE TABLE `{table}`"
            ]

            if config.database.defaults_file:
                cmd_check.insert(1, f"--defaults-file={config.database.defaults_file}")
                cmd_check = [c for c in cmd_check if not c.startswith("--password")]

            check_result = subprocess.run(
                cmd_check,
                capture_output=True,
                text=True
            )
            
            # 如果无法获取CREATE TABLE语句，说明表可能有问题
            if check_result.returncode != 0:
                missing_tables.append(f"{database_name}.{table}")
                logger.warning(f"[{database_name}] 表 {table} 检查失败: {check_result.stderr.strip()}")
        
        return missing_tables

    except subprocess.CalledProcessError as e:
        logger.warning(f"[{database_name}] 获取表列表失败: {e.stderr.strip()}")
        return []
    except Exception as e:
        logger.warning(f"[{database_name}] 检查表存在性时出错: {str(e)}")
        return []

def get_remote_mysql_version(config, args):
    """获取远程MySQL服务器版本"""
    try:
        mysql_path = os.path.join(config.backup.mysql_bin_dir, "mysql.exe")
        cmd = [
            mysql_path,
            f"--host={config.database.host}",
            f"--port={config.database.port}",
            f"--user={config.database.user}",
            f"--password={config.database.password}",
            "--silent",
            "--skip-column-names",
            "--execute=SELECT VERSION();"
        ]

        # 使用配置文件认证
        if config.database.defaults_file:
            cmd.insert(1, f"--defaults-file={config.database.defaults_file}")
            cmd = [c for c in cmd if not c.startswith("--password")]

        # 记录脱敏后的命令
        sanitized_cmd = sanitize.sanitize_command(cmd, args.debug)
        logger.info(f"查询远程MySQL版本命令: {' '.join(sanitized_cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        version_str = result.stdout.strip()
        logger.info(f"查询到远程MySQL版本: {version_str}")

        # 解析版本号
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_str)
        if match:
            major, minor, patch = match.groups()
            return (int(major), int(minor), int(patch))

        logger.warning(f"无法解析MySQL版本字符串: {version_str}")
        return (0, 0, 0)
    except subprocess.CalledProcessError as e:
        logger.error(f"查询MySQL版本失败: {e.stderr.strip()}")
        return (0, 0, 0)
    except Exception as e:
        logger.error(f"获取远程MySQL版本时出错: {str(e)}")
        return (0, 0, 0)