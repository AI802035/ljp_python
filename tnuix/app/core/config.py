from typing import Dict

# 系统配置
SAMPLING_RATE = 1000  # 采样频率
NOTCH_FREQ = 50      # 工频
QUALITY_FACTOR = 30  # 品质因数

# 用户配置
USERS: Dict[str, Dict] = {
    "admin": {
        "username": "admin",
        "password_hash": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",  # admin123
        "full_name": "管理员"
    }
}

# 会话配置
SESSION_EXPIRY = 3600  # 会话过期时间（秒）

# 串口配置
SERIAL_BUFFER_MAX_SIZE = 1000  # 串口数据缓冲区大小
DEFAULT_BAUDRATE = 115200

# 安全范围配置
PULSE_RANGES = {
    'cun': {
        'safe': [-0.5, 1.5],
        'warning': [-1.0, 2.0]
    },
    'guan': {
        'safe': [-0.4, 1.2],
        'warning': [-0.8, 1.6]
    },
    'chi': {
        'safe': [-0.3, 0.9],
        'warning': [-0.6, 1.2]
    }
}

PULSE_RATE_RANGES = {
    'safe': [60, 100],
    'warning': [50, 110]
} 