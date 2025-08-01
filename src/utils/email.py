# utils/email.py
import smtplib
import socket
import logging
from email.mime.text import MIMEText
from email.header import Header
import os
import datetime
from . import status

from ..config.schemas import FullConfig

logger = logging.getLogger("MySQLBackup.Email")


def send_alert_email(config: FullConfig, subject: str, body: str, is_warning=False):
    """发送警报邮件"""
    if not config.email.enabled:
        logger.warning("邮件通知未启用")
        return

    def parse_name_addr(addr):
        """解析邮箱地址，支持 "邮箱|姓名" 或仅邮箱的格式
        返回 (email, name) 元组
        """
        if '|' in addr:
            email_addr, name = addr.split('|', 1)
            return (email_addr.strip(), name.strip())
        return (addr.strip(), "")

    try:
        # 构建邮件消息
        msg = MIMEText(body, 'plain', 'utf-8')
        
        # 发件人显示名称
        msg['From'] = f"{config.email.sender_name} <{config.email.from_addr}>"
        
        # 处理收件人信息
        to_emails = []
        to_formatted = []
        for addr in config.email.to_addrs:
            email, name = parse_name_addr(addr)
            to_emails.append(email)
            to_formatted.append(f"{name} <{email}>" if name else email)
        
        # 处理抄送信息
        cc_emails = []
        cc_formatted = []
        if config.email.copy_to:
            for addr in config.email.copy_to:
                email, name = parse_name_addr(addr)
                cc_emails.append(email)
                cc_formatted.append(f"{name} <{email}>" if name else email)
        
        # 主送收件人（确保地址格式正确且包含姓名）
        if to_formatted:
            msg['To'] = ", ".join(to_formatted)
        
        # 抄送收件人（确保地址格式正确且包含姓名）
        if cc_formatted:
            msg['Cc'] = ", ".join(cc_formatted)
            
        # 密送收件人列表（用于发送但不显示）
        bcc_emails = []
        if config.email.additional_to:
            for addr in config.email.additional_to:
                email, _ = parse_name_addr(addr)
                bcc_emails.append(email)

        # 如果是警告邮件，主题添加警告标志
        if is_warning:
            subject = "⚠️ " + subject

        msg['Subject'] = Header(subject, 'utf-8')

        # 收集所有收件人的邮箱地址（用于实际发送）
        all_recipients = to_emails + cc_emails + bcc_emails

        logger.info(
            f"尝试连接企业微信邮箱SMTP服务器: {config.email.smtp_server}:{config.email.smtp_port}")
            
        # 记录发送信息（不包含密送）
        visible_recipients = []
        if to_formatted:
            visible_recipients.extend(to_formatted)
        if cc_formatted:
            visible_recipients.extend(cc_formatted)
        logger.info(f"邮件收件人: {', '.join(visible_recipients)}")

        # 使用SMTP_SSL连接
        with smtplib.SMTP_SSL(
            host=config.email.smtp_server,
            port=config.email.smtp_port,
            timeout=30
        ) as server:
            server.ehlo()
            server.login(config.email.smtp_user, config.email.smtp_password)
            logger.info("SMTP登录成功")
            server.sendmail(config.email.from_addr,
                          all_recipients, msg.as_string())
            logger.info(f"邮件发送成功至: {', '.join(visible_recipients)}")

    except smtplib.SMTPAuthenticationError:
        logger.error("认证失败，请检查用户名/密码/授权码和SMTP服务状态")
    except socket.timeout:
        logger.error("连接超时，请检查网络和防火墙设置")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP协议错误: {str(e)}")
    except Exception as e:
        logger.error(f"发送邮件过程中发生异常: {str(e)}", exc_info=True)


def send_success_email(config: FullConfig, status_data: dict):
    """发送备份成功通知邮件（完全成功）"""
    if not config.email.enabled:
        return
    skipped_tables = status_data.get('skipped_tables', [])
    if skipped_tables:
        send_partial_success_email(config, status_data)
        return
    config_name = status_data.get('config_name', config.config_name)
    backup_file = status_data.get('backup_file', '未知文件')
    retry_errors = status_data.get('retry_errors', [])
    try:
        file_size = 0
        if os.path.exists(backup_file):
            file_size = os.path.getsize(backup_file) / (1024 * 1024)
        hostname = socket.gethostname()
        last_run = status_data.get(
            'last_run', datetime.datetime.now().isoformat())
        try:
            dt = datetime.datetime.fromisoformat(last_run)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            formatted_time = last_run
        subject = "MySQL备份成功通知"
        state_text = "完全成功"
        body = f"""
备份时间: {formatted_time}
服务器: {hostname}
配置名称: {config_name}
备份文件: {os.path.basename(backup_file)}
文件大小: {file_size:.2f} MB
存储位置: {os.path.dirname(backup_file)}
状态: {state_text}
"""
        if retry_errors:
            errors = "\n".join(f"  - {error}" for error in retry_errors)
            body += f"""
重试过程中错误:
{errors}
"""
        send_alert_email(config, subject, body, is_warning=False)
        logger.info(f"已发送备份{state_text}通知邮件")
    except Exception as e:
        logger.error(f"发送备份成功邮件时出错: {str(e)}", exc_info=True)


def send_partial_success_email(config: FullConfig, status_data: dict):
    """发送备份部分成功通知邮件"""
    if not config.email.enabled:
        return
    config_name = status_data.get('config_name', config.config_name)
    backup_file = status_data.get('backup_file', '未知文件')
    skipped_tables = status_data.get('skipped_tables', [])
    retry_errors = status_data.get('retry_errors', [])
    try:
        file_size = 0
        if os.path.exists(backup_file):
            file_size = os.path.getsize(backup_file) / (1024 * 1024)
        hostname = socket.gethostname()
        last_run = status_data.get(
            'last_run', datetime.datetime.now().isoformat())
        try:
            dt = datetime.datetime.fromisoformat(last_run)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            formatted_time = last_run
        subject = "MySQL备份部分成功通知"
        state_text = "部分成功"
        body = f"""
备份时间: {formatted_time}
服务器: {hostname}
配置名称: {config_name}
备份文件: {os.path.basename(backup_file)}
文件大小: {file_size:.2f} MB
存储位置: {os.path.dirname(backup_file)}
状态: {state_text}
"""
        if skipped_tables:
            skipped_list = "\n".join(
                f"  - {table}" for table in skipped_tables)
            body += f"""
跳过的表 ({len(skipped_tables)}个):
{skipped_list}
"""
        if retry_errors:
            errors = "\n".join(f"  - {error}" for error in retry_errors)
            body += f"""
重试过程中错误:
{errors}
"""
        send_alert_email(config, subject, body, is_warning=True)
        logger.info(f"已发送备份{state_text}通知邮件")
    except Exception as e:
        logger.error(f"发送备份部分成功邮件时出错: {str(e)}", exc_info=True)


def send_error_email(config: FullConfig, status_data: dict):
    """发送备份失败通知邮件（增强版）"""
    if not config.email.enabled:
        return

    config_name = status_data.get('config_name', config.config_name)
    skipped_tables = status_data.get('skipped_tables', [])

    try:
        last_run = status_data.get('last_run', '未知时间')
        error_message = status_data.get('message', '无错误详细信息')
        alert_subject = f"【告警】MySQL备份失败 - {config_name}"

        alert_body = f"""
MySQL数据库备份失败！
配置名称: {config_name}
失败时间: {last_run}
错误信息: {error_message}
"""
        # 添加跳过的表信息（如果备份过程中检测到了）
        if skipped_tables:
            skipped_list = ", ".join(skipped_tables)
            alert_body += f"""
跳过的表 ({len(skipped_tables)}个): {skipped_list}
"""

        logger.warning(f"[{config_name}] 检测到备份失败，发送警报邮件")
        send_alert_email(config, alert_subject, alert_body)

    except Exception as e:
        logger.error(f"发送备份失败邮件时出错: {str(e)}", exc_info=True)


def send_running_email(config: FullConfig, status_data: dict):
    """发送备份任务正在进行中的提醒邮件"""
    if not config.email.enabled:
        return
    config_name = status_data.get('config_name', config.config_name)
    start_time = status_data.get('start_time')
    now = datetime.datetime.now()
    running_since = start_time or '未知'
    try:
        if start_time:
            try:
                dt = datetime.datetime.strptime(
                    start_time, "%Y-%m-%d %H:%M:%S")
                running_minutes = int((now - dt).total_seconds() // 60)
            except Exception:
                running_minutes = None
        else:
            running_minutes = None
        subject = f"MySQL备份任务正在进行中 - {config_name}"
        body = f"备份任务正在进行中，请稍后关注最终结果。\n\n配置名称: {config_name}\n开始时间: {running_since}\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if running_minutes is not None:
            body += f"已运行时长: {running_minutes} 分钟\n"
        send_alert_email(config, subject, body, is_warning=True)
        logger.info(f"已发送备份进行中提醒邮件: {config_name}")
    except Exception as e:
        logger.error(f"发送备份进行中邮件时出错: {str(e)}", exc_info=True)
