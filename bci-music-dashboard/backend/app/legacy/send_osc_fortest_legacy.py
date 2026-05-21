# 假OSC数据发射器 - 本地调试专用
# 每秒发送4个测试值，完全匹配你的接收端
from pythonosc import udp_client
import time
import random

# ===================== 配置（和你的接收端完全一致）=====================
SEND_IP = "127.0.0.1"       # 本地调试用本机IP，无需改局域网
SEND_PORT = 8000           # 端口和接收端一致
OSC_ADDRESS = "/eeg/valence_arousal"  # OSC地址完全匹配
# ======================================================================

# 初始化OSC客户端
client = udp_client.SimpleUDPClient(SEND_IP, SEND_PORT)
print(f"✅ 假OSC发射器启动，本地发送：{SEND_IP}:{SEND_PORT}")
print(f"📡 每秒发送：效价 | 唤醒度 | 积极置信度 | 消极置信度\n")

# 无限循环发送
try:
    while True:
        # 生成合理的测试数据（完全模拟真实程序的输出）
        valence = random.randint(1, 9)    # 效价：1-9随机整数
        arousal = random.randint(1, 9)    # 唤醒度：1-9随机整数
        prob0 = round(random.uniform(0.1, 0.9), 2)  # 积极置信度：0.1-0.9
        prob1 = round(1 - prob0, 2)       # 消极置信度：和prob0总和=1

        # 发送OSC数据
        client.send_message(OSC_ADDRESS, [valence, arousal, prob0, prob1])
        
        # 打印发送的内容（方便调试）
        print(f"已发送 → 效价：{valence} | 唤醒度：{arousal} | prob0：{prob0} | prob1：{prob1}")
        
        # 每秒发送一次
        time.sleep(1)

except KeyboardInterrupt:
    print("\n🛑 发射器已停止")