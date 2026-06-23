<template>
  <n-drawer :show="show" width="680" placement="left" @update:show="$emit('update:show', $event)">
    <n-drawer-content title="使用说明" closable>
      <article class="help-copy">
        <section>
          <h2>快速开始</h2>
          <ol>
            <li>调试演示时点击 <strong>Start Simulator</strong>，模拟器会继续每秒输出一次情绪信号。</li>
            <li>选择一首公版主题后点击 <strong>Start Generator</strong>。系统以八小节为完整乐句，按 Intro、Theme、Variation、Development、Climax、Return、Coda 演奏约 3–5 分钟。</li>
            <li>最近 16 秒 EEG 决定下一乐句的情绪结构；每秒信号同时连续控制力度、Pad 亮度、Bass 和鼓的强度。</li>
            <li>Notochord 只在 Variation、Development 和 Climax 的旋律空隙加入装饰音。模型缺失或超时时，主题、和声和播放仍会继续。</li>
            <li>真实采集前先放置模型文件，并配置 XDF 监听目录，再点击 <strong>Start Model</strong>。</li>
            <li>在 <strong>Tracks</strong> 中启用或编辑音轨，设置 MIDI 或 OSC 输出目标。</li>
            <li>在 <strong>Outputs</strong> 中选择音轨并点击 <strong>Test Output</strong>，检查外部设备是否收到测试音符。</li>
            <li>实验开始前点击 <strong>Start Recording</strong>，停止后可导出情绪曲线、音乐事件和 MIDI 文件。</li>
          </ol>
        </section>
        <section>
          <h2>界面区域</h2>
          <p>情绪监测区展示 Valence、Arousal、情绪标签和实时曲线。Tracks 用于配置不同乐器与生成规则。Music Events 展示引擎最近生成的事件。Music Config 用于调整全局参数、情绪参数和配置文件快照。</p>
        </section>
        <section>
          <h2>术语表</h2>
          <n-table :bordered="true" :single-line="false" size="small">
            <thead>
              <tr><th>英文术语</th><th>中文含义</th></tr>
            </thead>
            <tbody>
              <tr v-for="term in terms" :key="term.name">
                <td>{{ term.name }}</td>
                <td>{{ term.description }}</td>
              </tr>
            </tbody>
          </n-table>
        </section>
      </article>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { NDrawer, NDrawerContent, NTable } from 'naive-ui';

defineProps<{ show: boolean }>();
defineEmits(['update:show']);

const terms = [
  { name: 'Valence', description: '效价，表示情绪偏正向还是偏负向。' },
  { name: 'Arousal', description: '唤醒度，表示情绪激活程度或兴奋程度。' },
  { name: 'Confidence', description: '置信度，表示当前情绪判断的稳定程度。' },
  { name: 'Track', description: '音轨，一条独立的旋律、鼓、Pad、Bass 或控制输出通道。' },
  { name: 'Pitch Range', description: '音高范围，使用 MIDI 音高编号限制可生成的音区。' },
  { name: 'Velocity', description: '力度，MIDI 音符触发强度，通常影响音量与演奏触感。' },
  { name: 'BPM', description: '速度，每分钟拍数。' },
  { name: 'Density', description: '密度，决定单位时间内生成音符或节奏事件的多少。' },
  { name: 'Humanize', description: '人性化扰动，让时值和触发略有自然偏移。' },
  { name: 'Quantization', description: '量化，把事件吸附到拍点或细分节奏网格。' },
  { name: 'Root Note', description: '根音，调式或和弦构建的基准音。' },
  { name: 'Scale', description: '音阶，例如大调、小调、五声音阶。' },
  { name: 'MIDI', description: '乐器数字接口，用音符、控制器和通道消息驱动软硬件乐器。' },
  { name: 'OSC', description: '开放声音控制协议，常用于把实时参数发送给 Max/MSP 等系统。' },
  { name: 'Preset', description: '预设，当前音乐配置的一份可加载快照。' },
  { name: 'Session', description: '会话，一次录制过程及其情绪、事件和配置快照。' },
  { name: 'Theme Recognition', description: '主题辨识度，越高越多保留原主题音与强拍锚点。' },
  { name: 'Generation Freedom', description: '生成自由度，控制可变音与 Notochord 装饰量，不会改动主题锚点。' },
  { name: 'Max Melody Voices', description: '主题木琴轨的最大同时声部数；默认强拍二音，高潮、长音和终止处最多三音。' },
  { name: 'Voicing Density', description: '符合和声条件的主题拍点中，实际加入第二或第三个木琴声部的比例。' },
  { name: 'Notochord Revoice Rate', description: '允许 Notochord 重新选择的规则和声音比例，主题主音始终不变。' },
];
</script>

<style scoped>
.help-copy {
  display: grid;
  gap: 22px;
  line-height: 1.65;
}

h2,
p,
ol {
  margin: 0;
}

ol {
  padding-left: 22px;
}

th,
td {
  vertical-align: top;
}
</style>
