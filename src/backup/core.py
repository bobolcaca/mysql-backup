import os
import datetime
from ..utils.platform_utils import PlatformUtils
import shutil
import gzip
import subprocess
import logging
import re
import tempfile
from typing import List
from ..config.schemas import FullConfig
from ..utils import status, email, ssh
from . import mysql_utils, cleanup
from .mysql_utils import get_mysqldump_version, get_remote_mysql_version
from ..utils.sanitize import sanitize_command
from .db_info import get_db_variables, write_db_info_header

logger = logging.getLogger("MySQLBackup.Core")


def perform_backup_for_config(config: FullConfig, args):
    """为单个配置执行备份任务（智能错误处理）"""
    config_name = config.config_name
    logger.info(f"开始处理配置: {config_name}")

    ssh_client = None
    skipped_tables: List[str] = []  # 存储跳过的表
    retry_errors = []  # 存储重试的错误信息
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    start_time = now.strftime("%Y-%m-%d %H:%M:%S")
    # 标记备份开始
    status.save_backup_status(
        config_name,
        False,
        f"[{config_name}] 备份进行中...",
        backup_file=None,
        running=True,
        start_time=start_time,
        end_time=None,
        skipped_tables=skipped_tables,
        retry_errors=retry_errors,
        mail_sent_time=None
    )

    try:
        # SSH隧道处理
        if config.ssh and config.ssh.enabled:
            if not ssh.check_ssh_connectivity(config.ssh.host, config.ssh.port):
                raise Exception("SSH服务器不可达")

            ssh_client = ssh.setup_ssh_tunnel(config.ssh)
            if not ssh_client:
                raise Exception("SSH隧道建立失败，无法继续备份")

        # 创建备份目录
        os.makedirs(config.backup.backup_dir, exist_ok=True)

        # 生成带时间戳的文件名，确保存储路径来自配置
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        db_name = config.database.database_names or 'all-databases'
        backup_dir = config.backup.backup_dir
        temp_file = os.path.join(backup_dir, f"backup_{config_name}_{db_name}_{timestamp}.sql")
        backup_file = os.path.join(backup_dir, f"backup_{config_name}_{db_name}_{timestamp}.sql.gz")

        # 获取MySQL服务器版本
        server_version = get_remote_mysql_version(config, args)

        # 构建mysqldump命令
        mysqldump_path = PlatformUtils.get_mysql_executable(
            config.backup.mysql_bin_dir, "mysqldump")

        # 检查客户端版本兼容性
        client_version = get_mysqldump_version(mysqldump_path)
        if client_version[0] > server_version[0]:
            logger.warning(
                f"[{config_name}] 警告：客户端版本({'.'.join(map(str, client_version))})高于服务器版本({'.'.join(map(str, server_version))})")

        cmd = [
            mysqldump_path,
            f"--host={config.database.host}",
            f"--port={config.database.port}",
            f"--user={config.database.user}",
            f"--password={config.database.password}",
            "--single-transaction",
            "--no-tablespaces",
        ]

        # 添加列统计选项 (解决5.7兼容性问题)
        if server_version < (8, 0, 0):
            cmd.append("--column-statistics=0")
            logger.info(f"[{config_name}] 添加--column-statistics=0选项")

        # 使用配置文件认证
        if config.database.defaults_file:
            cmd.insert(1, f"--defaults-file={config.database.defaults_file}")
            cmd = [c for c in cmd if not c.startswith("--password")]

        # 添加备份对象
        if server_version >= (8, 0, 13):
            cmd.extend(["--routines", "--triggers", "--events"])
        else:
            logger.info(f"[{config_name}] 不使用--routines/--triggers/--events参数")

        # 添加数据库
        if config.database.database_names:
            cmd.append("--databases")
            cmd.extend(config.database.database_names.split(','))
        else:
            cmd.append("--all-databases")

        # 添加输出文件
        cmd.append(f"--result-file={temp_file}")

        # 预先检查缺失的表并添加忽略参数
        if config.database.database_names:
            for db_name in config.database.database_names.split(','):
                missing_tables = mysql_utils.check_missing_tables(config, args, db_name)
                if missing_tables:
                    for table in missing_tables:
                        table_lower = table.lower()
                        if table_lower not in skipped_tables:
                            skipped_tables.append(table_lower)
                            logger.warning(f"[{config_name}] 预检查发现缺失表: {table}")
                            cmd.append(f"--ignore-table={table_lower}")
                            retry_errors.append(f"[{config_name}] 预检查发现缺失表: {table}")

        # 记录脱敏后的命令
        sanitized_cmd = sanitize_command(cmd, args.debug)
        logger.info(f"[{config_name}] 执行备份命令: {' '.join(sanitized_cmd)}")

        # 备份执行与智能错误处理逻辑
        backup_success = False
        used_force = False  # 是否使用过--force
        max_force_retry = 3  # --force最大使用次数
        force_attempts = 0   # --force使用计数器
        retry_count = 0     # 添加重试计数器

        while not backup_success:
            # 使用force_cmd作为当前命令
            current_cmd = cmd + ["--force"] if used_force else cmd

            process = subprocess.Popen(
                current_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()

            # 处理错误
            table_not_found = False
            if process.returncode != 0:
                # 查找缺失的表（用于处理预检查可能漏掉的情况）
                table_matches = re.findall(r"Table '([\w\.]+)' doesn't exist", stderr)

                # 只处理第一个缺失的表
                if table_matches:
                    table_name = table_matches[0]
                    table_name_lower = table_name.lower()

                    # 避免重复添加同一个表的忽略规则
                    if table_name_lower not in skipped_tables:
                        skipped_tables.append(table_name_lower)
                        logger.warning(f"[{config_name}] 备份过程中发现新的缺失表: {table_name}")
                        # 添加--ignore-table参数
                        cmd += [f"--ignore-table={table_name_lower}"]
                        logger.info(f"[{config_name}] 添加忽略参数: --ignore-table={table_name_lower}")
                        # 标记有表需要重试
                        table_not_found = True

            # 处理其他兼容性错误
            compatibility_error = False
            if not table_not_found and process.returncode != 0 and "Unknown table 'LIBRARIES'" in stderr:
                logger.warning(f"[{config_name}] 降级兼容：移除问题参数并重试...")
                cmd = [c for c in cmd if not any(
                    p in c for p in ["--routines", "--triggers", "--events"])]
                compatibility_error = True

            # 记录当前错误信息
            if process.returncode != 0:
                retry_count += 1
                attempt_info = f"第{retry_count}次尝试错误" if table_not_found else f"错误"
                error_msg = f"[{config_name}] {attempt_info}: {stderr.strip()}"
                retry_errors.append(error_msg)
                logger.info(error_msg)

            # 如果有表缺失错误，继续重试
            if table_not_found:
                continue

            # 如果有兼容性错误，继续重试（只处理一次）
            if compatibility_error:
                continue

            # 如果是未知错误，尝试使用--force
            if process.returncode != 0 and not used_force:
                logger.warning(f"[{config_name}] 使用--force作为最后兜底方案")
                used_force = True
                force_attempts += 1
                continue

            # 如果已经使用过--force仍然失败，则结束
            if process.returncode != 0 and force_attempts > 0:
                # 检查是否达到最大重试次数
                if force_attempts < max_force_retry:
                    logger.warning(
                        f"[{config_name}] --force重试 ({force_attempts}/{max_force_retry})")
                    force_attempts += 1
                    continue
                else:
                    logger.error(f"[{config_name}] 多次使用--force后备份仍然失败")
                    break

            # 成功完成备份
            if process.returncode == 0:
                backup_success = True
                break

        # 检查最终结果
        end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not backup_success:
            final_error = stderr or "未知错误"
            error_msg = f"[{config_name}] 备份失败！错误信息：{final_error}"
            logger.error(error_msg)
            status.save_backup_status(
                config_name, False, error_msg, skipped_tables=skipped_tables,
                retry_errors=retry_errors, running=False, start_time=start_time, end_time=end_time, mail_sent_time=None
            )
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            return None

        # 在备份完成后，创建一个临时文件来存储数据库参数
        temp_info_file = None
        try:
            # 获取数据库参数
            db_info = get_db_variables(config, args)
            if db_info:
                # 创建临时文件
                temp_fd, temp_info_file = tempfile.mkstemp(suffix='.sql')
                os.close(temp_fd)
                
                # 写入数据库参数和原始备份内容
                with open(temp_info_file, 'w', encoding='utf-8') as f_out:
                    write_db_info_header(f_out, db_info)
                    with open(temp_file, 'r', encoding='utf-8') as f_in:
                        shutil.copyfileobj(f_in, f_out)
                
                # 用新文件替换原始备份文件
                os.replace(temp_info_file, temp_file)
                logger.info(f"[{config_name}] 已记录数据库参数信息")
        except Exception as e:
            logger.warning(f"[{config_name}] 记录数据库参数时出错: {str(e)}")
        finally:
            if temp_info_file and os.path.exists(temp_info_file):
                try:
                    os.remove(temp_info_file)
                except:
                    pass

        # 压缩备份文件
        with open(temp_file, 'rb') as f_in:
            with gzip.open(backup_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(temp_file)

        # 验证备份文件
        if not os.path.exists(backup_file) or os.path.getsize(backup_file) == 0:
            error_msg = f"[{config_name}] 备份文件创建失败或文件为空"
            logger.error(error_msg)
            status.save_backup_status(
                config_name, False, error_msg, skipped_tables=skipped_tables,
                retry_errors=retry_errors, running=False, start_time=start_time, end_time=end_time, mail_sent_time=None
            )
            return None

        # 构建成功消息
        file_size = os.path.getsize(backup_file) / (1024 * 1024)  # 转换为MB

        # 如果有跳过的表，状态为部分成功
        success_type = "部分成功" if skipped_tables else "完全成功"
        success_msg = f"[{config_name}] 备份{success_type}: {backup_file} ({file_size:.2f} MB)"

        if skipped_tables:
            skipped_list = ", ".join(skipped_tables)
            success_msg += f"\n跳过的表: {skipped_list}"
            logger.warning(f"[{config_name}] 备份部分成功，跳过的表: {skipped_list}")

        # 保存状态（先保存备份结果，不含mail_sent_time）
        status.save_backup_status(
            config_name,
            True,
            success_msg,
            backup_file,
            skipped_tables=skipped_tables,
            retry_errors=retry_errors,
            running=False,
            start_time=start_time,
            end_time=end_time,
            mail_sent_time=None
        )

        # 检查是否需要补发邮件（允许一天多次发，无论成功失败都发）
        report_time = getattr(config.backup, 'report_time', None)
        now_dt = datetime.datetime.now()
        status_data = status.load_backup_status(config_name)
        if report_time:
            report_dt = datetime.datetime.strptime(f"{today_str} {report_time}", "%Y-%m-%d %H:%M")
            if now_dt > report_dt:
                # 发送邮件（成功或失败都发，开关由email.py内部判断）
                if status_data.get('success', False):
                    email.send_success_email(config, status_data)
                else:
                    email.send_error_email(config, status_data)
                # 仅在邮件发送后再写 mail_sent_time
                status.save_backup_status(
                    config_name,
                    status_data.get('success', False),
                    status_data.get('msg', ''),
                    status_data.get('backup_file', None),
                    skipped_tables=status_data.get('skipped_tables', []),
                    retry_errors=status_data.get('retry_errors', []),
                    running=False,
                    start_time=status_data.get('start_time'),
                    end_time=status_data.get('end_time'),
                    mail_sent_time=now_dt.strftime("%Y-%m-%d %H:%M:%S")
                )
        else:
            # 没有配置邮件发送时间但邮件配置打开，采集完成后立即发送邮件
            if config.email and config.email.enabled:
                if status_data.get('success', False):
                    email.send_success_email(config, status_data)
                else:
                    email.send_error_email(config, status_data)
                status.save_backup_status(
                    config_name,
                    status_data.get('success', False),
                    status_data.get('msg', ''),
                    status_data.get('backup_file', None),
                    skipped_tables=status_data.get('skipped_tables', []),
                    retry_errors=status_data.get('retry_errors', []),
                    running=False,
                    start_time=status_data.get('start_time'),
                    end_time=status_data.get('end_time'),
                    mail_sent_time=now_dt.strftime("%Y-%m-%d %H:%M:%S")
                )

        return backup_file

    except Exception as e:
        error_msg = f"[{config_name}] 备份过程中发生异常: {str(e)}"
        logger.exception(error_msg)
        end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status.save_backup_status(
            config_name,
            False,
            error_msg,
            skipped_tables=skipped_tables,
            retry_errors=retry_errors,
            running=False,
            start_time=start_time,
            end_time=end_time,
            mail_sent_time=None
        )
        return None

    finally:
        if ssh_client:
            ssh_client.close()
        logger.info(f"[{config_name}] 处理完成")


def check_backup_status_for_config(config: FullConfig):
    """检查单个配置的备份状态"""
    config_name = config.config_name
    status_data = status.load_backup_status(config_name)

    if not status_data:
        alert_msg = f"[{config_name}] 未找到备份状态记录"
        logger.warning(alert_msg)
        email.send_alert_email(
            config, f"MySQL备份状态未知 - {config_name}", alert_msg)
        return

    # 如果备份正在进行中，直接发“正在备份中”邮件
    if status_data.get('running', False):
        email.send_running_email(config, status_data)
        logger.info(f"[{config_name}] 备份任务正在进行中，已发送提醒邮件")
        return

    # 检查最后一次备份是否成功（开关由email.py内部判断）
    if not status_data.get('success', False):
        email.send_error_email(config, status_data)
    else:
        email.send_success_email(config, status_data)

    # 仅在邮件发送后再写 mail_sent_time
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status.save_backup_status(
        config_name,
        status_data.get('success', False),
        status_data.get('msg', ''),
        status_data.get('backup_file', None),
        skipped_tables=status_data.get('skipped_tables', []),
        retry_errors=status_data.get('retry_errors', []),
        running=False,
        start_time=status_data.get('start_time'),
        end_time=status_data.get('end_time'),
        mail_sent_time=now_str
    )


def process_config(config: FullConfig, args):
    """处理单个配置的任务"""
    try:
        if args.backup:
            logger.info(f"[{config.config_name}] 执行备份操作")
            backup_file = perform_backup_for_config(config, args)
            if backup_file:
                cleanup.clean_old_backups_for_config(config)
            return backup_file
        elif args.check:
            logger.info(f"[{config.config_name}] 执行备份状态检查")
            check_backup_status_for_config(config)
        else:
            logger.info(f"[{config.config_name}] 执行单次备份")
            backup_file = perform_backup_for_config(config, args)
            if backup_file:
                cleanup.clean_old_backups_for_config(config)
            return backup_file
    except Exception as e:
        logger.error(
            f"[{config.config_name}] 处理配置时出错: {str(e)}", exc_info=True)
    return None
