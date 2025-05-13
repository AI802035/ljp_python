from fastapi import FastAPI, WebSocket, Request, Depends, HTTPException, status, Cookie, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
import json
import asyncio
import numpy as np
from scipy import signal
import websockets
from typing import List, Optional
import math
import uvicorn
import socket
import serial
import serial.tools.list_ports
from datetime import datetime, timedelta
import hashlib
import secrets
import time
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import logging

app = FastAPI()
security = HTTPBasic()

# 用户管理（示例用户数据，实际应用中应该使用数据库）
users = {
    "admin": {
        "username": "admin",
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
        "full_name": "管理员"
    }
}

# 会话管理
sessions = {}
SESSION_EXPIRY = 3600  # 会话过期时间（秒）

# 创建会话
def create_session(username: str) -> str:
    session_id = secrets.token_hex(16)
    sessions[session_id] = {
        "username": username,
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_EXPIRY
    }
    return session_id

# 验证会话
def verify_session(session_id: Optional[str] = Cookie(None)) -> Optional[str]:
    if not session_id or session_id not in sessions:
        return None
    
    session = sessions[session_id]
    if time.time() > session["expires_at"]:
        # 会话已过期
        del sessions[session_id]
        return None
        
    # 更新会话过期时间
    session["expires_at"] = time.time() + SESSION_EXPIRY
    return session["username"]

# 认证依赖
def get_current_user(session_id: Optional[str] = Cookie(None)):
    username = verify_session(session_id)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或会话已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username

def find_available_port(start_port=8000, max_port=8999):
    """查找可用端口"""
    for port in range(start_port, max_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return None

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 存储所有WebSocket连接
active_connections: List[WebSocket] = []

# 串口连接状态
serial_connection = None
is_connected = False

# 数字滤波器参数
fs = 1000  # 采样频率
f_notch = 50  # 工频
Q = 30  # 品质因数

# 全局变量，用于控制数据来源和存储设置
use_simulated_data = True  # 初始使用模拟数据
serial_data_buffer = {
    'cun': [],
    'guan': [],
    'chi': []
}
serial_buffer_max_size = 1000  # 串口数据缓冲区大小
data_processing_lock = asyncio.Lock()  # 数据处理锁，防止并发冲突

logging.basicConfig(level=logging.DEBUG,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',datefmt='%Y-%m-%d %H:%M:%S')


# 登录页面HTML
login_html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>寸关尺部脉搏监测系统 - 登录</title>
    <link href="https://cdn.bootcdn.net/ajax/libs/tailwindcss/2.2.19/tailwind.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f3f4f6;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .login-container {
            background: white;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 400px;
            padding: 2rem;
        }
        .header {
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: white;
            padding: 1rem;
            border-radius: 0.5rem;
            text-align: center;
            margin-bottom: 1.5rem;
        }
        .form-group {
            margin-bottom: 1.5rem;
        }
        .form-label {
            display: block;
            margin-bottom: 0.5rem;
            color: #4b5563;
            font-weight: 500;
        }
        .form-input {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 1px solid #d1d5db;
            border-radius: 0.375rem;
            font-size: 1rem;
        }
        .form-input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3);
        }
        .btn-login {
            width: 100%;
            padding: 0.75rem;
            background-color: #3b82f6;
            color: white;
            border: none;
            border-radius: 0.375rem;
            font-weight: 500;
            font-size: 1rem;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .btn-login:hover {
            background-color: #2563eb;
        }
        .error-message {
            color: #ef4444;
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="header">
            <h1 class="text-xl font-bold">寸关尺部脉搏监测系统</h1>
        </div>
        
        <form action="/login" method="post" class="login-form">
            <div class="form-group">
                <label for="username" class="form-label">用户名</label>
                <input type="text" id="username" name="username" class="form-input" required>
            </div>
            
            <div class="form-group">
                <label for="password" class="form-label">密码</label>
                <input type="password" id="password" name="password" class="form-input" required>
            </div>
            
            <div id="error-message" class="error-message">
                <!-- 错误信息将在这里显示 -->
                {% if error %}
                <p>{{ error }}</p>
                {% endif %}
            </div>
            
            <button type="submit" class="btn-login">登录</button>
        </form>
        
        <div class="mt-4 text-center text-sm text-gray-500">
            <p>默认用户名: admin</p>
            <p>默认密码: admin123</p>
        </div>
    </div>
</body>
</html>
"""

# HTML内容中添加退出按钮
html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>寸关尺部脉搏监测系统</title>
    <script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <link href="https://cdn.bootcdn.net/ajax/libs/tailwindcss/2.2.19/tailwind.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f3f4f6;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }
        .header {
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: white;
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .chart-container {
            background: white;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }
        .chart {
            height: 300px;
            width: 100%;
        }
        .control-panel {
            background: white;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .status-connected {
            background-color: #10b981;
        }
        .status-disconnected {
            background-color: #ef4444;
        }
        .btn {
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            font-weight: 500;
            transition: all 0.2s;
        }
        .btn-primary {
            background-color: #3b82f6;
            color: white;
        }
        .btn-primary:hover {
            background-color: #2563eb;
        }
        .btn-secondary {
            background-color: #6b7280;
            color: white;
        }
        .btn-secondary:hover {
            background-color: #4b5563;
        }
        .data-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }
        .info-card {
            background: #f8fafc;
            padding: 1rem;
            border-radius: 0.375rem;
            text-align: center;
        }
        .info-value {
            font-size: 1.5rem;
            font-weight: 600;
            color: #1e3a8a;
        }
        .info-label {
            color: #64748b;
            font-size: 0.875rem;
        }
        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-top: 1rem;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin-right: 1rem;
        }
        .legend-color {
            width: 24px;
            height: 12px;
            margin-right: 0.5rem;
            border-radius: 2px;
        }
        .safe-level {
            background-color: rgba(16, 185, 129, 0.2);
        }
        .warning-level {
            background-color: rgba(245, 158, 11, 0.2);
        }
        .danger-level {
            background-color: rgba(239, 68, 68, 0.2);
        }
        .pulse-status {
            display: flex;
            align-items: center;
            margin-bottom: 0.5rem;
            padding: 0.5rem;
            border-radius: 0.375rem;
            border-left: 4px solid transparent;
        }
        .pulse-normal {
            background-color: rgba(16, 185, 129, 0.1);
            border-left-color: #10b981;
        }
        .pulse-warning {
            background-color: rgba(245, 158, 11, 0.1);
            border-left-color: #f59e0b;
        }
        .pulse-danger {
            background-color: rgba(239, 68, 68, 0.1);
            border-left-color: #ef4444;
        }
    </style>
</head>
<body class="p-6">
    <div class="header flex items-center justify-between">
        <h1 class="text-2xl font-bold">寸关尺部脉搏监测系统</h1>
        <div class="flex items-center">
            <span id="userInfo" class="text-sm mr-4"></span>
            <a href="/logout" class="text-white bg-blue-700 hover:bg-blue-800 px-3 py-1 rounded text-sm">退出登录</a>
        </div>
    </div>

    <div class="control-panel">
        <div class="flex items-center justify-between mb-4">
            <div class="flex items-center">
                <span class="status-indicator" id="connectionStatus"></span>
                <span id="statusText" class="text-gray-700">未连接</span>
            </div>
            <div class="space-x-4">
                <select id="portSelect" class="border rounded px-3 py-2">
                    <option value="">选择串口</option>
                </select>
                <select id="baudrateSelect" class="border rounded px-3 py-2">
                    <option value="9600">9600</option>
                    <option value="19200">19200</option>
                    <option value="38400">38400</option>
                    <option value="57600">57600</option>
                    <option value="115200" selected>115200</option>
                </select>
                <button id="connectBtn" class="btn btn-primary">连接设备</button>
                <button id="disconnectBtn" class="btn btn-secondary" disabled>断开连接</button>
            </div>
        </div>
        <div class="bg-blue-50 p-2 rounded-md mb-3">
            <p id="dataSourceIndicator" class="text-sm">数据源: <span class="font-semibold text-blue-600">模拟</span></p>
            <p class="text-xs text-gray-600 mt-1">STM32硬件连接说明: 连接到STM32单片机后，需确保数据格式为"timestamp,cun_value,guan_value,chi_value[,pulse_rate]"</p>
            <div class="mt-1 text-xs text-gray-600 border-t border-blue-100 pt-1">
                <p>没有实际硬件？您可以：</p>
                <ol class="list-decimal pl-5 mt-1">
                    <li>使用下拉框中的DEBUG_COM选项进行测试</li>
                    <li>安装<a href="https://www.eltima.com/products/vspdxp/" target="_blank" class="text-blue-600">虚拟串口软件</a>创建虚拟串口测试</li>
                    <li>连接实际的STM32设备</li>
                </ol>
            </div>
        </div>
        <div class="data-info">
            <div class="info-card">
                <div class="info-value" id="pulseRate">--</div>
                <div class="info-label">脉搏率 (次/分)</div>
                <div id="pulseStatus" class="mt-2 text-sm"></div>
            </div>
            <div class="info-card">
                <div class="info-value" id="samplingRate">--</div>
                <div class="info-label">采样率 (Hz)</div>
            </div>
            <div class="info-card">
                <div class="info-value" id="timestamp">--</div>
                <div class="info-label">最后更新时间</div>
            </div>
        </div>
    </div>
    
    <div class="chart-container">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-semibold">寸部</h2>
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color safe-level"></div>
                    <span class="text-sm">安全范围</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color warning-level"></div>
                    <span class="text-sm">警告范围</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color danger-level"></div>
                    <span class="text-sm">危险范围</span>
                </div>
            </div>
        </div>
        <div id="cunChart" class="chart"></div>
    </div>
    
    <div class="chart-container">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-semibold">关部</h2>
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color safe-level"></div>
                    <span class="text-sm">安全范围</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color warning-level"></div>
                    <span class="text-sm">警告范围</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color danger-level"></div>
                    <span class="text-sm">危险范围</span>
                </div>
            </div>
        </div>
        <div id="guanChart" class="chart"></div>
    </div>
    
    <div class="chart-container">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-semibold">尺部</h2>
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color safe-level"></div>
                    <span class="text-sm">安全范围</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color warning-level"></div>
                    <span class="text-sm">警告范围</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color danger-level"></div>
                    <span class="text-sm">危险范围</span>
                </div>
            </div>
        </div>
        <div id="chiChart" class="chart"></div>
    </div>

    <script>
        // 获取用户信息
        async function getUserInfo() {
            try {
                const response = await fetch('/api/user');
                if (response.ok) {
                    const data = await response.json();
                    document.getElementById('userInfo').textContent = `${data.full_name} (${data.username})`;
                }
            } catch (error) {
                console.error('获取用户信息失败:', error);
            }
        }
        
        // 页面加载时获取用户信息
        getUserInfo();
        
        // 获取当前页面URL的端口号
        const port = window.location.port;
        
        // 安全范围设置
        const ranges = {
            cun: {
                safe: [-0.5, 1.5],  // 安全范围
                warning: [-1.0, 2.0]  // 警告范围
                // 超出警告范围即为危险范围
            },
            guan: {
                safe: [-0.4, 1.2],
                warning: [-0.8, 1.6]
            },
            chi: {
                safe: [-0.3, 0.9],
                warning: [-0.6, 1.2]
            }
        };
        
        // 脉搏率正常范围
        const pulseRateRanges = {
            safe: [60, 100],
            warning: [50, 110]
        };
        
        // 初始化图表
        const charts = {
            cun: echarts.init(document.getElementById('cunChart')),
            guan: echarts.init(document.getElementById('guanChart')),
            chi: echarts.init(document.getElementById('chiChart'))
        };

        // 为每个位置创建基础配置
        function createBaseOption(position) {
            return {
                grid: {
                    left: '5%',
                    right: '5%',
                    bottom: '8%',
                    top: '10%',
                    containLabel: true
                },
                tooltip: {
                    trigger: 'axis',
                    formatter: function(params) {
                        const data = params[0].data;
                        return `<div style="padding: 5px;">
                            <div style="font-weight: bold; margin-bottom: 5px;">数据点信息</div>
                            <div>时间: ${data[0].toFixed(2)}秒</div>
                            <div>数值: ${data[1].toFixed(2)}</div>
                        </div>`;
                    },
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    borderColor: '#ccc',
                    borderWidth: 1,
                    textStyle: {
                        color: '#333'
                    }
                },
                xAxis: {
                    type: 'value',
                    boundaryGap: false,
                    axisLabel: {
                        color: '#64748b',
                        formatter: '{value} 秒',
                        margin: 12
                    },
                    splitLine: {
                        lineStyle: {
                            color: 'rgba(120, 120, 120, 0.2)'
                        }
                    },
                    axisTick: {
                        show: true
                    },
                    axisLine: {
                        show: true,
                        lineStyle: {
                            color: '#ccc'
                        }
                    },
                    name: '时间 (秒)',
                    nameLocation: 'middle',
                    nameGap: 30
                },
                yAxis: {
                    type: 'value',
                    scale: true,
                    axisLabel: {
                        color: '#64748b',
                        formatter: '{value}',
                        margin: 16
                    },
                    splitLine: {
                        lineStyle: {
                            color: 'rgba(120, 120, 120, 0.2)'
                        }
                    },
                    axisTick: {
                        show: true
                    },
                    axisLine: {
                        show: true,
                        lineStyle: {
                            color: '#ccc'
                        }
                    },
                    name: '脉搏强度',
                    nameLocation: 'middle',
                    nameGap: 40
                },
                series: [
                    {
                        type: 'line',
                        smooth: true,
                        symbol: 'circle',
                        symbolSize: 5,
                        showSymbol: false,
                        sampling: 'average',
                        lineStyle: {
                            color: '#3b82f6',
                            width: 2
                        },
                        emphasis: {
                            itemStyle: {
                                shadowBlur: 10,
                                shadowColor: 'rgba(0, 0, 0, 0.3)'
                            }
                        },
                        areaStyle: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
                                { offset: 1, color: 'rgba(59, 130, 246, 0.1)' }
                            ])
                        },
                        data: []
                    }
                ],
                visualMap: {
                    show: false,
                    pieces: [
                        {
                            gt: ranges[position].warning[1],
                            lte: 10,
                            color: '#ef4444'
                        },
                        {
                            gt: ranges[position].safe[1],
                            lte: ranges[position].warning[1],
                            color: '#f59e0b'
                        },
                        {
                            gt: ranges[position].safe[0],
                            lte: ranges[position].safe[1],
                            color: '#3b82f6'
                        },
                        {
                            gt: ranges[position].warning[0],
                            lte: ranges[position].safe[0],
                            color: '#f59e0b'
                        },
                        {
                            gt: -10,
                            lte: ranges[position].warning[0],
                            color: '#ef4444'
                        }
                    ],
                    dimension: 1
                },
                // 添加标记区域
                markArea: {
                    silent: true,
                    data: [
                        // 安全范围
                        [
                            { yAxis: ranges[position].safe[0], xAxis: 0, name: '安全范围', itemStyle: { opacity: 0.2 } },
                            { yAxis: ranges[position].safe[1], xAxis: 'max' }
                        ],
                        // 警告范围 (上)
                        [
                            { yAxis: ranges[position].safe[1], xAxis: 0, name: '警告', itemStyle: { opacity: 0.2 } },
                            { yAxis: ranges[position].warning[1], xAxis: 'max' }
                        ],
                        // 警告范围 (下)
                        [
                            { yAxis: ranges[position].warning[0], xAxis: 0, name: '警告', itemStyle: { opacity: 0.2 } },
                            { yAxis: ranges[position].safe[0], xAxis: 'max' }
                        ],
                        // 危险范围 (上)
                        [
                            { yAxis: ranges[position].warning[1], xAxis: 0, name: '危险', itemStyle: { opacity: 0.2 } },
                            { yAxis: 10, xAxis: 'max' }
                        ],
                        // 危险范围 (下)
                        [
                            { yAxis: -10, xAxis: 0, name: '危险', itemStyle: { opacity: 0.2 } },
                            { yAxis: ranges[position].warning[0], xAxis: 'max' }
                        ]
                    ],
                    itemStyle: {
                        color: function(params) {
                            // 根据区域返回不同的颜色
                            const idx = params.dataIndex;
                            if (idx === 0) {
                                return 'rgba(16, 185, 129, 0.2)'; // 安全范围
                            } else if (idx === 1 || idx === 2) {
                                return 'rgba(245, 158, 11, 0.2)'; // 警告范围
                            } else {
                                return 'rgba(239, 68, 68, 0.2)'; // 危险范围
                            }
                        }
                    },
                    label: {
                        show: true,
                        position: 'right',
                        color: '#555',
                        fontSize: 10,
                        distance: 5
                    }
                },
                animation: true
            };
        }

        // 应用基础配置到所有图表
        Object.keys(charts).forEach(position => {
            charts[position].setOption(createBaseOption(position));
        });

        // 数据缓存
        const dataCache = {
            cun: [],
            guan: [],
            chi: []
        };

        // 检查脉搏率是否在安全范围内
        function checkPulseRate(pulseRate) {
            const pulseStatusElement = document.getElementById('pulseStatus');
            
            if (pulseRate >= pulseRateRanges.safe[0] && pulseRate <= pulseRateRanges.safe[1]) {
                // 正常范围
                pulseStatusElement.innerHTML = `<div class="pulse-status pulse-normal">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                    <span>正常</span>
                </div>`;
                return 'normal';
            } else if (pulseRate >= pulseRateRanges.warning[0] && pulseRate <= pulseRateRanges.warning[1]) {
                // 警告范围
                pulseStatusElement.innerHTML = `<div class="pulse-status pulse-warning">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>注意</span>
                </div>`;
                return 'warning';
            } else {
                // 危险范围
                pulseStatusElement.innerHTML = `<div class="pulse-status pulse-danger">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>异常</span>
                </div>`;
                return 'danger';
            }
        }

        // 连接WebSocket
        let ws = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 5;
        const reconnectDelay = 3000; // 3秒

        function connectWebSocket() {
            try {
                ws = new WebSocket(`ws://localhost:${port}/ws`);
                
                ws.onopen = function() {
                    console.log('WebSocket连接已建立');
                    reconnectAttempts = 0;
                };
                
                ws.onclose = function(event) {
                    console.log('WebSocket连接已关闭:', event.code, event.reason);
                    if (reconnectAttempts < maxReconnectAttempts) {
                        reconnectAttempts++;
                        console.log(`尝试重新连接 (${reconnectAttempts}/${maxReconnectAttempts})...`);
                        setTimeout(connectWebSocket, reconnectDelay);
                    } else {
                        console.log('达到最大重连次数，停止重连');
                    }
                };
                
                ws.onerror = function(error) {
                    console.error('WebSocket错误:', error);
                };
                
                ws.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        
                        // 更新数据缓存
                        ['cun', 'guan', 'chi'].forEach(position => {
                            dataCache[position].push([data.timestamp, data[position]]);
                            if (dataCache[position].length > 100) {
                                dataCache[position].shift();
                            }
                            
                            // 更新图表
                            charts[position].setOption({
                                series: [{
                                    data: dataCache[position],
                                    markPoint: {
                                        data: [
                                            { type: 'max', name: '最大值', symbol: 'pin', symbolSize: 45, label: { show: true, formatter: '{c}' } },
                                            { type: 'min', name: '最小值', symbol: 'arrow', symbolSize: 45, label: { show: true, formatter: '{c}' } }
                                        ],
                                        silent: false
                                    }
                                }]
                            });
                        });

                        // 更新状态信息
                        document.getElementById('pulseRate').textContent = data.pulse_rate || '--';
                        document.getElementById('samplingRate').textContent = data.sampling_rate || '--';
                        document.getElementById('timestamp').textContent = new Date().toLocaleTimeString();
                        
                        // 如果数据来源发生变化，更新指示器
                        if (data.source) {
                            if (data.source === 'hardware') {
                                document.getElementById('dataSourceIndicator').innerHTML = '数据源: <span class="font-semibold text-green-600">硬件</span>';
                            } else {
                                document.getElementById('dataSourceIndicator').innerHTML = '数据源: <span class="font-semibold text-blue-600">模拟</span>';
                            }
                        }
                        
                        // 检查脉搏率
                        if (data.pulse_rate) {
                            checkPulseRate(data.pulse_rate);
                        }
                    } catch (error) {
                        console.error('处理WebSocket消息时出错:', error);
                    }
                };
            } catch (error) {
                console.error('创建WebSocket连接时出错:', error);
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    setTimeout(connectWebSocket, reconnectDelay);
                }
            }
        }

        // 初始连接
        connectWebSocket();

        // 页面关闭时清理WebSocket连接
        window.addEventListener('beforeunload', function() {
            if (ws) {
                ws.close();
            }
        });

        // 处理窗口大小变化
        window.addEventListener('resize', function() {
            Object.values(charts).forEach(chart => chart.resize());
        });

        // 串口连接相关功能
        const connectBtn = document.getElementById('connectBtn');
        const disconnectBtn = document.getElementById('disconnectBtn');
        const portSelect = document.getElementById('portSelect');
        const connectionStatus = document.getElementById('connectionStatus');
        const statusText = document.getElementById('statusText');

        // 获取可用串口列表
        async function getPorts() {
            try {
                const response = await fetch('/api/ports');
                const ports = await response.json();
                portSelect.innerHTML = '<option value="">选择串口</option>';
                ports.forEach(port => {
                    portSelect.innerHTML += `<option value="${port}">${port}</option>`;
                });
            } catch (error) {
                console.error('获取串口列表失败:', error);
            }
        }

        // 连接设备
        connectBtn.addEventListener('click', async () => {
            const selectedPort = portSelect.value;
            if (!selectedPort) {
                alert('请选择串口');
                return;
            }

            try {
                const baudrate = parseInt(document.getElementById('baudrateSelect').value);
                const response = await fetch('/api/connect', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ 
                        port: selectedPort,
                        baudrate: baudrate 
                    })
                });

                const result = await response.json();
                if (result.status === 'success') {
                    connectionStatus.className = 'status-indicator status-connected';
                    statusText.textContent = `已连接 (${result.port}, ${result.baudrate}波特率)`;
                    connectBtn.disabled = true;
                    disconnectBtn.disabled = false;
                    portSelect.disabled = true;
                    document.getElementById('baudrateSelect').disabled = true;
                    
                    // 设置数据源标识
                    document.getElementById('dataSourceIndicator').innerHTML = '数据源: <span class="font-semibold text-green-600">硬件</span>';
                } else {
                    throw new Error(result.message || '连接失败');
                }
            } catch (error) {
                alert('连接设备失败: ' + error.message);
            }
        });

        // 断开连接
        disconnectBtn.addEventListener('click', async () => {
            try {
                const response = await fetch('/api/disconnect', {
                    method: 'POST'
                });

                const result = await response.json();
                if (result.status === 'success') {
                    connectionStatus.className = 'status-indicator status-disconnected';
                    statusText.textContent = '未连接';
                    connectBtn.disabled = false;
                    disconnectBtn.disabled = true;
                    portSelect.disabled = false;
                    document.getElementById('baudrateSelect').disabled = false;
                    
                    // 更新数据源指示
                    document.getElementById('dataSourceIndicator').innerHTML = '数据源: <span class="font-semibold text-blue-600">模拟</span>';
                } else {
                    throw new Error(result.message || '断开连接失败');
                }
            } catch (error) {
                alert('断开连接失败: ' + error.message);
            }
        });

        // 页面加载时获取串口列表
        getPorts();
    </script>
</body>
</html>
"""

# 创建陷波滤波器
def create_notch_filter():
    b, a = signal.iirnotch(f_notch, Q, fs)
    return b, a

# 应用滤波器
def apply_filter(data, b, a):
    return signal.filtfilt(b, a, data)

# 生成模拟脉搏数据
def generate_pulse_data(t):
    # 基础脉搏波形（使用正弦波模拟）
    base_freq = 1.2  # 每秒1.2次脉搏
    amplitude = 1.0
    
    # 每30秒切换一次状态（正常/异常）
    is_abnormal = (int(t) // 30) % 2 == 1
    
    # 添加一些随机变化使波形更自然
    noise = np.random.normal(0, 0.1 if not is_abnormal else 0.3)
    
    if is_abnormal:
        # 异常状态：更快的心率，更大的波动
        base_freq = 2.0  # 每秒2次脉搏（120次/分钟）
        pulse_rate = 120
    else:
        # 正常状态
        pulse_rate = 72
    
    # 生成三个不同位置的脉搏数据，共用同一个状态
    t_with_freq = 2 * math.pi * base_freq * t
    cun = amplitude * (1.8 if is_abnormal else 1.0) * math.sin(t_with_freq) + noise
    guan = amplitude * (1.5 if is_abnormal else 0.8) * math.sin(t_with_freq + 0.2) + noise
    chi = amplitude * (1.2 if is_abnormal else 0.6) * math.sin(t_with_freq + 0.4) + noise
    
    return cun, guan, chi, pulse_rate, is_abnormal

async def simulate_pulse_data():
    """生成模拟脉搏数据"""
    t = 0
    while True:
        try:
            # 只有当使用模拟数据且有活动连接时才生成数据
            if not use_simulated_data or not active_connections:
                await asyncio.sleep(1)
                continue
                
            # 生成模拟数据
            cun, guan, chi, pulse_rate, is_abnormal = generate_pulse_data(t)
            
            # 发送数据到所有连接的客户端
            message = {
                'cun': cun,
                'guan': guan,
                'chi': chi,
                'timestamp': t,
                'pulse_rate': pulse_rate,
                'sampling_rate': fs,
                'source': 'simulation',
                'status': 'abnormal' if is_abnormal else 'normal'
            }
            
            # 创建连接列表的副本以避免在迭代时修改
            connections = active_connections.copy()
            
            # 发送数据到每个连接
            for connection in connections:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception as e:
                    if connection in active_connections:
                        active_connections.remove(connection)
                        print(f"移除断开的连接，当前活动连接数: {len(active_connections)}")
                    print(f"发送数据到客户端失败: {e}")
            
            t += 0.1
            await asyncio.sleep(0.1)  # 每100ms发送一次数据
                
        except Exception as e:
            print(f"数据生成错误: {e}")
            await asyncio.sleep(1)
            continue

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            try:
                # 保持连接活跃
                data = await websocket.receive_text()
                # 发送心跳响应
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
            except websockets.exceptions.ConnectionClosed:
                print("WebSocket连接已关闭")
                break
            except Exception as e:
                print(f"WebSocket接收错误: {e}")
                break
    finally:
        # 确保连接被移除
        if websocket in active_connections:
            active_connections.remove(websocket)
            print(f"当前活动连接数: {len(active_connections)}")

@app.on_event("startup")
async def startup_event():
    # 启动模拟数据生成任务
    print("------启动模拟数据生成任务------")
    asyncio.create_task(simulate_pulse_data())
    # 启动串口数据读取任务
    print("------启动串口数据读取任务------")
    asyncio.create_task(read_serial_data())

# 登录页面
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, username: Optional[str] = Depends(verify_session)):
    if username is None:
        return login_html.replace("{% if error %}\n                <p>{{ error }}</p>\n                {% endif %}", "")
    return HTMLResponse(content=html_content)

# 登录处理
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    # 验证用户名和密码
    if username not in users:
        return HTMLResponse(
            content=login_html.replace("{% if error %}\n                <p>{{ error }}</p>\n                {% endif %}", 
                                      "<p>用户名不存在</p>"),
            status_code=401
        )
    
    user = users[username]
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if password_hash != user["password_hash"]:
        return HTMLResponse(
            content=login_html.replace("{% if error %}\n                <p>{{ error }}</p>\n                {% endif %}", 
                                      "<p>密码错误</p>"),
            status_code=401
        )
    
    # 创建会话
    session_id = create_session(username)
    
    # 创建响应
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=SESSION_EXPIRY)
    
    return response

# 获取当前用户信息
@app.get("/api/user")
async def get_user_info(username: str = Depends(get_current_user)):
    if username not in users:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user = users[username]
    return {
        "username": user["username"],
        "full_name": user["full_name"]
    }

# 退出登录
@app.get("/logout")
async def logout(session_id: Optional[str] = Cookie(None)):
    if session_id and session_id in sessions:
        del sessions[session_id]
    
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="session_id")
    
    return response

# 串口相关API
@app.get("/api/ports")
async def get_ports(username: str = Depends(get_current_user)):
    """获取可用串口列表"""
    real_ports = [port.device for port in serial.tools.list_ports.comports()]
    print(f"系统检测到的实际串口: {real_ports}")
    
    # 添加虚拟串口选项，便于在没有硬件时测试
    debug_ports = ["DEBUG_COM1", "DEBUG_COM2", "DEBUG_COM3"]
    
    # 合并实际串口和虚拟串口
    all_ports = real_ports + debug_ports
    return all_ports

@app.post("/api/connect")
async def connect_serial(request: Request, username: str = Depends(get_current_user)):
    """连接串口"""
    global serial_connection, is_connected, use_simulated_data
    
    try:
        data = await request.json()
        port = data.get("port")
        baudrate = data.get("baudrate", 115200)
        
        if not port:
            return {"status": "error", "message": "未指定串口"}
        
        # 关闭已有连接
        if serial_connection and serial_connection.is_open:
            serial_connection.close()
        
        # 检查是否为调试串口
        if port.startswith("DEBUG_"):
            print(f"连接到虚拟调试串口: {port}")
            is_connected = True
            use_simulated_data = True  # 使用模拟数据
            return {"status": "success", "port": port, "baudrate": baudrate, "mode": "debug"}
        
        # 创建新连接
        serial_connection = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        
        is_connected = True
        use_simulated_data = False  # 切换到实际数据
        
        print(f"成功连接到串口!!{port}，波特率: {baudrate}")
        return {"status": "success", "port": port, "baudrate": baudrate}
    except Exception as e:
        print(f"连接串口失败: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/disconnect")
async def disconnect_serial(username: str = Depends(get_current_user)):
    """断开串口连接"""
    global serial_connection, is_connected, use_simulated_data
    try:
        if serial_connection and serial_connection.is_open:
            serial_connection.close()
        is_connected = False
        use_simulated_data = True  # 切换回模拟数据
        print("已断开串口连接，切换回模拟数据")
        return {"status": "success"}
    except Exception as e:
        print(f"断开串口连接失败: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/status")
async def get_status(username: str = Depends(get_current_user)):
    """获取当前连接状态和数据源信息"""
    port_info = None
    if serial_connection:
        try:
            port_info = {
                "port": serial_connection.port,
                "baudrate": serial_connection.baudrate,
                "is_open": serial_connection.is_open
            }
        except:
            pass
    
    return {
        "is_connected": is_connected,
        "using_simulated_data": use_simulated_data,
        "port_info": port_info
    }

# 串口连接和数据处理
async def read_serial_data():
    """从串口读取数据并处理"""
    global serial_connection, is_connected, serial_data_buffer, use_simulated_data
    num=0
    print("------开始监听串口连接状态------")
    t=0
    while True:
        num+=1
        print(f"第{num}次尝试读取串口数据")
        print(f"串口连接状态为{is_connected}")
        try:
            if not is_connected or serial_connection is None or not serial_connection.is_open:
                print("------1------")
                await asyncio.sleep(0.5)
                continue
                
            # 检查是否有数据可读
            if serial_connection.in_waiting > 0:

                print("------2------")
                # 读取一行数据 (假设数据格式为: "时间戳,寸,关,尺\n")
                line = serial_connection.read(15).decode('utf-8').strip()
                print("------3------")
                print(line)
                '''
                if not line:
                    print("------4------")
                    await asyncio.sleep(0.01)
                    continue'''
                
                try:
                    # 解析数据
                    # 假设传入数据格式: "timestamp,cun_value,guan_value,chi_value"
                    print("------5------")
                    parts = line.split(',')
                    print("------6------")
                    if len(parts) >= 3:  # 确保数据格式正确
                        print("------7------")
                        cun_value = float(parts[0])
                        guan_value = float(parts[1])
                        chi_value = float(parts[2])
                        t+=0.001
                        timestamp=t
                        print(f"存部数据{cun_value}")
                        print(f"关部数据{guan_value}")
                        print(f"尺部数据{chi_value}")
                        print(f"时间戳数据{timestamp}")
                        
                        # 获取可选的脉率数据（如果硬件提供）
                        pulse_rate = float(parts[4]) if len(parts) > 4 else None
                        
                        # 应用数字滤波（如果需要）
                        b, a = create_notch_filter()
                        if len(serial_data_buffer['cun']) > 10:  # 确保有足够的数据进行滤波
                            cun_data = [d[1] for d in serial_data_buffer['cun'][-10:]] + [cun_value]
                            guan_data = [d[1] for d in serial_data_buffer['guan'][-10:]] + [guan_value]
                            chi_data = [d[1] for d in serial_data_buffer['chi'][-10:]] + [chi_value]
                            
                            filtered_cun = apply_filter(np.array(cun_data), b, a)[-1]
                            filtered_guan = apply_filter(np.array(guan_data), b, a)[-1]
                            filtered_chi = apply_filter(np.array(chi_data), b, a)[-1]
                        else:
                            filtered_cun = cun_value
                            filtered_guan = guan_value
                            filtered_chi = chi_value
                        
                        # 更新缓冲区
                        async with data_processing_lock:
                            serial_data_buffer['cun'].append((timestamp, filtered_cun))
                            serial_data_buffer['guan'].append((timestamp, filtered_guan))
                            serial_data_buffer['chi'].append((timestamp, filtered_chi))
                            
                            # 限制缓冲区大小
                            if len(serial_data_buffer['cun']) > serial_buffer_max_size:
                                serial_data_buffer['cun'] = serial_data_buffer['cun'][-serial_buffer_max_size:]
                                serial_data_buffer['guan'] = serial_data_buffer['guan'][-serial_buffer_max_size:]
                                serial_data_buffer['chi'] = serial_data_buffer['chi'][-serial_buffer_max_size:]
                            
                            # 设置使用实际数据
                            use_simulated_data = False
                        
                        # 向客户端发送最新数据
                        message = {
                            'cun': filtered_cun,
                            'guan': filtered_guan,
                            'chi': filtered_chi,
                            'timestamp': timestamp,
                            'pulse_rate': pulse_rate if pulse_rate is not None else round(60 * 1.2),
                            'sampling_rate': fs,
                            'source': 'hardware'
                        }
                        
                        connections = active_connections.copy()
                        for connection in connections:
                            try:
                                await connection.send_text(json.dumps(message))
                            except Exception as e:
                                if connection in active_connections:
                                    active_connections.remove(connection)
                                print(f"发送串口数据到客户端失败: {e}")
                                
                except Exception as e:
                    print(f"解析串口数据错误: {e}")
            else:
                print("当前无数据可读！")
            await asyncio.sleep(0.01)  # 小的延迟，避免CPU过度使用
                
        except Exception as e:
            print(f"读取串口数据错误: {e}")
            await asyncio.sleep(1)
            
            # 如果连接丢失，尝试自动重新连接
            if is_connected and serial_connection and not serial_connection.is_open:
                try:
                    serial_connection.open()
                except:
                    is_connected = False
                    use_simulated_data = True

if __name__ == "__main__":
    try:
        port = find_available_port()
        if port is None:
            print("错误：无法找到可用端口")
            exit(1)
        print(f"服务器将在 http://127.0.0.1:{port} 上启动")
        uvicorn.run(app, host="127.0.0.1", port=port)
    except Exception as e:
        print(f"启动服务器时发生错误: {e}")
        exit(1) 