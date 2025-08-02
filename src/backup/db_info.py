from typing import Dict, Optional, Tuple
import subprocess
import logging
import re
import json
import gzip
import os
from ..config.schemas import FullConfig

logger = logging.getLogger("MySQLBackup.DBInfo")

def get_db_variables(config: FullConfig, args) -> Dict[str, str]:
    """获取数据库重要变量"""
    mysql_path = os.path.join(config.backup.mysql_bin_dir, "mysql.exe")
    variables_to_check = [
        'character_set_server',
        'character_set_database',
        'character_set_client',
        'collation_server',
        'collation_database',
        'innodb_file_format',
        'innodb_large_prefix',
        'innodb_file_per_table',
        'innodb_strict_mode',
        'sql_mode'
    ]
    
    # 使用 SHOW VARIABLES 命令替代 information_schema 查询
    variables_clause = ' OR '.join([f"Variable_name = '{v}'" for v in variables_to_check])
    query = f"SHOW GLOBAL VARIABLES WHERE {variables_clause}"
    
    cmd = [
        mysql_path,
        f"--host={config.database.host}",
        f"--port={config.database.port}",
        f"--user={config.database.user}",
        f"--password={config.database.password}",
        "--skip-column-names",
        "-e", query
    ]

    if config.database.defaults_file:
        cmd.insert(1, f"--defaults-file={config.database.defaults_file}")
        cmd = [c for c in cmd if not c.startswith("--password")]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            logger.warning(f"获取数据库变量失败: {stderr}")
            return {}
            
        variables = {}
        for line in stdout.splitlines():
            if '\t' in line:
                name, value = line.split('\t')
                variables[name.lower()] = value
                
        return variables
    except Exception as e:
        logger.warning(f"获取数据库变量时发生错误: {str(e)}")
        return {}

def write_db_info_header(f_out, db_info: Dict[str, str]):
    """在输出流中写入数据库信息
    Args:
        f_out: 文件对象或类文件对象，必须以文本模式打开
        db_info: 要写入的数据库参数信息
    """
    header = (
        "/* START DATABASE PARAMETERS\n"
        f"{json.dumps(db_info, indent=2, ensure_ascii=False)}\n"
        "END DATABASE PARAMETERS */\n\n"
    )
    f_out.write(header)

def read_db_info_header(file_path: str) -> Dict[str, str]:
    """从SQL文件读取数据库信息，支持gz压缩文件"""
    try:
        # 检查是否为gz文件
        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                content = f.read(4096)  # 只读取开头部分
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(4096)  # 只读取开头部分
            
        match = re.search(r'/\* START DATABASE PARAMETERS\n(.*?)\nEND DATABASE PARAMETERS \*/', 
                         content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        logger.warning(f"读取数据库信息头失败: {str(e)}")
    
    return {}
