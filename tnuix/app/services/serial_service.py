import serial
import serial.tools.list_ports
from typing import List, Optional, Dict, Tuple
import numpy as np
from scipy import signal
import asyncio
import json
import logging
from app.core.config import SAMPLING_RATE, NOTCH_FREQ, QUALITY_FACTOR, SERIAL_BUFFER_MAX_SIZE

class SerialService:
    def __init__(self,is_Simulated):
        self.connection: Optional[serial.Serial] = None
        self.is_connected: bool = False
        self.use_simulated_data: bool = is_Simulated#这里使用模拟数据改成false
        self.data_buffer: Dict[str, List[Tuple[float, float]]] = {
            'cun': [],
            'guan': [],
            'chi': []
        }
        self.data_lock = asyncio.Lock()

    def getDataFromSerialPort(self):
        """持续读取串口数据"""
        logging.debug(f"自定义串口连接状态为{self.is_connected}")
        logging.debug(f"预定义串口连接状态为{self.connection.is_open}")
        while self.is_connected and self.connection.is_open:
            try:
                data = self.connection.readline().decode('utf-8').strip()
                if data:
                    logging.debug(f"接收到的数据: {data}")
                    processed_data = await self.process_serial_data(data)
                    if processed_data:
                        logging.debug(f"处理后的数据: {processed_data}")
            except Exception as e:
                logging.error(f"读取串口数据错误: {e}")
            await asyncio.sleep(0.1)  # 稍微等待一段时间，避免过于频繁地读取


    @staticmethod
    def get_available_ports() -> List[str]:
        """获取可用串口列表"""
        real_ports = [port.device for port in serial.tools.list_ports.comports()]
        debug_ports = ["DEBUG_COM1", "DEBUG_COM2", "DEBUG_COM3"]
        return real_ports + debug_ports

    def connect(self, port: str, baudrate: int = 115200) -> Dict:
        """连接串口"""
        try:
            if port.startswith("DEBUG_"):
                self.is_connected = True
                self.use_simulated_data = True
                return {"status": "success", "port": port, "baudrate": baudrate, "mode": "debug"}

            if self.connection and self.connection.is_open:
                self.connection.close()

            self.connection = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            
            self.is_connected = True
            self.use_simulated_data = False
            return {"status": "success", "port": port, "baudrate": baudrate}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def disconnect(self) -> Dict:
        """断开串口连接"""
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
            self.is_connected = False
            self.use_simulated_data = True
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict:
        """获取连接状态"""
        port_info = None
        if self.connection:
            try:
                port_info = {
                    "port": self.connection.port,
                    "baudrate": self.connection.baudrate,
                    "is_open": self.connection.is_open
                }
            except:
                pass
        
        return {
            "is_connected": self.is_connected,
            "using_simulated_data": self.use_simulated_data,
            "port_info": port_info
        }

    @staticmethod
    def create_notch_filter():
        """创建陷波滤波器"""
        b, a = signal.iirnotch(NOTCH_FREQ, QUALITY_FACTOR, SAMPLING_RATE)
        return b, a

    @staticmethod
    def apply_filter(data: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
        """应用滤波器"""
        return signal.filtfilt(b, a, data)

    async def process_serial_data(self, data: str) -> Optional[Dict]:
        """处理串口数据"""
        try:
            parts = data.split(',')
            if len(parts) >= 4:
                timestamp = float(parts[0])
                cun_value = float(parts[1])
                guan_value = float(parts[2])
                chi_value = float(parts[3])
                pulse_rate = float(parts[4]) if len(parts) > 4 else None

                # 应用滤波
                b, a = self.create_notch_filter()
                async with self.data_lock:
                    # 更新数据缓冲区并应用滤波
                    for position, value in [('cun', cun_value), ('guan', guan_value), ('chi', chi_value)]:
                        self.data_buffer[position].append((timestamp, value))
                        if len(self.data_buffer[position]) > SERIAL_BUFFER_MAX_SIZE:
                            self.data_buffer[position] = self.data_buffer[position][-SERIAL_BUFFER_MAX_SIZE:]

                    # 获取滤波后的最新值
                    if len(self.data_buffer['cun']) > 10:
                        filtered_values = {}
                        for position in ['cun', 'guan', 'chi']:
                            data = [d[1] for d in self.data_buffer[position][-10:]]
                            filtered_values[position] = self.apply_filter(np.array(data), b, a)[-1]
                    else:
                        filtered_values = {
                            'cun': cun_value,
                            'guan': guan_value,
                            'chi': chi_value
                        }

                return {
                    'cun': filtered_values['cun'],
                    'guan': filtered_values['guan'],
                    'chi': filtered_values['chi'],
                    'timestamp': timestamp,
                    'pulse_rate': pulse_rate if pulse_rate is not None else round(60 * 1.2),
                    'sampling_rate': SAMPLING_RATE,
                    'source': 'hardware'
                }
        except Exception as e:
            print(f"处理串口数据错误: {e}")
            return None

# 创建全局串口服务实例
serial_service = SerialService(is_Simulated=True)
