import React from 'react';
import { Layout, Menu, Typography } from 'antd';
import { LineChart } from '@ant-design/plots';
import './App.css';

const { Header, Content, Footer } = Layout;
const { Title } = Typography;

function App() {
    const [chartData, setChartData] = React.useState({
        cun: [],
        guan: [],
        chi: []
    });

    React.useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws');

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            setChartData((prevData => ({
                cun: [...prevData.cun, { value: data.cun, time: data.timestamp }],
                guan: [...prevData.guan, { value: data.guan, time: data.timestamp }],
                chi: [...prevData.chi, { value: data.chi, time: data.timestamp }]
            })));
        };

        return () => {
            ws.close();
        };
    }, []);

    const config = {
        height: 200,
        xField: 'time',
        yField: 'value',
        smooth: true,
        animation: false,
        xAxis: {
            type: 'time',
            boundaryGap: 0,
            title: {
                text: '时间 (秒)'
            },
            nice: true,
            min: 0,  // 设置一个固定的最小值，例如 0 秒
            max: 10  // 设置一个固定的最大值，例如 10 秒
        },
        yAxis: {
            title: {
                text: '脉搏强度'
            }
        }
    };

    return (
        <Layout className="layout">
            <Header>
                <div className="logo" />
                <Menu theme="dark" mode="horizontal" defaultSelectedKeys={['1']}>
                    <Menu.Item key="1">实时监测</Menu.Item>
                    <Menu.Item key="2">数据分析</Menu.Item>
                    <Menu.Item key="3">历史记录</Menu.Item>
                </Menu>
            </Header>
            <Content style={{ padding: '0 50px' }}>
                <div className="site-layout-content">
                    <Title level={2}>寸关尺部脉搏实时监测</Title>

                    <div className="chart-container">
                        <Title level={4}>寸</Title>
                        <LineChart {...config} data={chartData.cun} />
                    </div>

                    <div className="chart-container">
                        <Title level={4}>关部数据</Title>
                        <LineChart {...config} data={chartData.guan} />
                    </div>

                    <div className="chart-container">
                        <Title level={4}>尺部数据</Title>
                        <LineChart {...config} data={chartData.chi} />
                    </div>
                </div>
            </Content>
            <Footer style={{ textAlign: 'center' }}>
                寸关尺部脉搏监测系统 ©2024
            </Footer>
        </Layout>
    );
}

export default App;