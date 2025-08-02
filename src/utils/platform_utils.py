"""Platform specific utilities and abstractions."""
import os
import sys
import subprocess
import logging
from typing import Optional, Tuple

logger = logging.getLogger("MySQLBackup.Platform")

class PlatformUtils:
    """Platform specific utilities"""
    
    @staticmethod
    def is_windows() -> bool:
        """Check if running on Windows"""
        return sys.platform.startswith('win')

    @staticmethod
    def get_mysql_executable(mysql_bin_dir: str, cmd: str = 'mysql') -> str:
        """Get the platform-specific MySQL executable path"""
        if PlatformUtils.is_windows():
            return os.path.join(mysql_bin_dir, f"{cmd}.exe")
        return os.path.join(mysql_bin_dir, cmd)

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize path for current platform"""
        return os.path.normpath(path)

    @staticmethod
    def clean_old_tasks():
        """清理所有旧的备份相关任务"""
        if PlatformUtils.is_windows():
            PlatformUtils._clean_old_windows_tasks()
        else:
            PlatformUtils._clean_old_linux_tasks()

    @staticmethod
    def schedule_task(task_name: str, schedule_time: str, command: str) -> Tuple[bool, Optional[str]]:
        """Schedule a task based on platform"""
        if PlatformUtils.is_windows():
            return PlatformUtils._schedule_windows_task(task_name, schedule_time, command)
        else:
            return PlatformUtils._schedule_linux_task(task_name, schedule_time, command)

    @staticmethod
    def _clean_old_windows_tasks() -> None:
        """清理所有前缀为MySQLBackup_和MySQLBackupCheck_的旧任务"""
        try:
            # 获取所有任务的列表
            result = subprocess.run(['schtasks', '/Query', '/FO', 'CSV'], 
                                 capture_output=True, text=True, check=True)
            
            # 解析CSV输出（跳过标题行）
            tasks = result.stdout.splitlines()[1:]
            for task in tasks:
                # CSV格式，第一列是任务名（带引号）
                task_name = task.split(',')[0].strip('"')
                if task_name.startswith('MySQLBackup_') or task_name.startswith('MySQLBackupCheck_'):
                    try:
                        subprocess.run(['schtasks', '/Delete', '/TN', task_name, '/F'],
                                    capture_output=True, check=True)
                        logger.info(f"已删除旧的计划任务: {task_name}")
                    except subprocess.CalledProcessError:
                        logger.warning(f"删除计划任务失败: {task_name}")
                        
        except subprocess.CalledProcessError as e:
            logger.error(f"获取计划任务列表失败: {e.stderr}")
        except Exception as e:
            logger.error(f"清理旧任务时出错: {str(e)}")

    @staticmethod
    def _schedule_windows_task(task_name: str, schedule_time: str, command: str) -> Tuple[bool, Optional[str]]:
        """Schedule a Windows task"""
        try:
            # 创建新任务
            subprocess.run([
                'schtasks', '/Create', '/TN', task_name,
                '/SC', 'DAILY', '/ST', schedule_time,
                '/TR', command, '/RL', 'HIGHEST', '/F'
            ], check=True, capture_output=True, text=True)
            return True, None
        except subprocess.CalledProcessError as e:
            return False, str(e.stderr)

    @staticmethod
    def _clean_old_linux_tasks() -> None:
        """清理所有包含MySQLBackup_和MySQLBackupCheck_注释的crontab任务"""
        try:
            # 获取当前crontab
            current_cron = subprocess.run(['crontab', '-l'], 
                                       capture_output=True, 
                                       text=True)
            
            if current_cron.returncode != 0:
                if "no crontab" in current_cron.stderr.lower():
                    return  # 用户没有crontab是正常的
                logger.error(f"获取crontab失败: {current_cron.stderr}")
                return

            # 过滤掉所有MySQL备份相关的任务
            cron_lines = current_cron.stdout.splitlines()
            new_lines = [line for line in cron_lines 
                        if not any(prefix in line 
                                 for prefix in ['MySQLBackup_', 'MySQLBackupCheck_'])]
            
            # 写入新的crontab
            process = subprocess.Popen(['crontab', '-'], 
                                    stdin=subprocess.PIPE, 
                                    text=True)
            process.communicate(input='\n'.join(new_lines))
            
            if process.returncode == 0:
                removed_count = len(cron_lines) - len(new_lines)
                if removed_count > 0:
                    logger.info(f"已清理 {removed_count} 个旧的crontab任务")
            else:
                logger.error("更新crontab失败")
                
        except Exception as e:
            logger.error(f"清理crontab任务时出错: {str(e)}")

    @staticmethod
    def _schedule_linux_task(task_name: str, schedule_time: str, command: str) -> Tuple[bool, Optional[str]]:
        """Schedule a Linux cron task"""
        try:
            # Parse time
            hour, minute = schedule_time.split(':')
            cron_line = f"{minute} {hour} * * * {command} # {task_name}\n"
            
            # Get current crontab
            current_cron = subprocess.run(['crontab', '-l'], 
                                       capture_output=True, 
                                       text=True)
            
            cron_lines = []
            if current_cron.returncode == 0:
                # Remove old task if exists
                cron_lines = [line for line in current_cron.stdout.splitlines() 
                            if task_name not in line]
            
            # Add new task
            cron_lines.append(cron_line)
            
            # Write new crontab
            process = subprocess.Popen(['crontab', '-'], 
                                    stdin=subprocess.PIPE, 
                                    text=True)
            process.communicate(input='\n'.join(cron_lines))
            
            if process.returncode == 0:
                return True, None
            return False, "Failed to update crontab"
            
        except subprocess.CalledProcessError as e:
            return False, str(e.stderr)
        except Exception as e:
            return False, str(e)
