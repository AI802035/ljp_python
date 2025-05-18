# 寸关尺部脉搏实时监测与分析系统

本系统用于实时监测和分析寸关尺部脉搏数据，包括数据采集、显示和分析功能。

## 系统功能

- 多通道脉搏数据实时采集
- 数据实时显示和波形绘制
- 工频干扰消除
- 数据统计分析
- 历史数据查看

## 技术栈

- 后端：FastAPI
- 前端：React + Ant Design
- 数据处理：NumPy, SciPy
- 串口通信：pyserial
- 实时通信：WebSocket

## 安装和运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 运行后端服务：
```bash
uvicorn main:app --reload
```

3. 访问系统：
打开浏览器访问 http://localhost:8000

## 硬件要求

- STM32开发板
- 压电传感器
- 串口模块
- 屏蔽材料（锡箔纸等） 