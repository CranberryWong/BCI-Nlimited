export const tabs = [
  { id: 'inputs', label: '输入', description: '确认信号来源、辅助传感器与外部服务的故障保护。' },
  { id: 'policy', label: '映射策略', description: '将输入映射为音乐意图；BCI 为主，辅助输入只做调制。' },
  { id: 'form', label: '曲式', description: '设计乐段顺序、情绪变化预算与允许的转场。' },
  { id: 'tonal', label: '调性', description: '整场演出使用一个默认主音和一个基础调式，情绪变化不直接切换调式。' },
  { id: 'motif', label: '动机', description: '设计初始音乐材料、固定锚点及各乐段的变形方式。' },
  { id: 'melody', label: '旋律', description: '确认模型条件、转录与流式护栏；此页不会启动模型。' },
  { id: 'harmony', label: '和声', description: '按曲式角色编辑和弦路线，配置候选模型与二声部对位。' },
  { id: 'orchestration', label: '配器', description: '各声部独立设置密度和力度，共享节拍与细分。' },
  { id: 'outputs', label: '输出', description: '集中确认 MIDI 通道、OSC 目标、音频与日志设置。' },
];
export const defaults: Record<string, any> = {
  inputs: { strategy: 'adaptive_performance', bci: { source_id: 'bci.primary', stale_after_seconds: 5, neutral_return_seconds: 10, minimum_confidence: .45 }, time: { enabled: true, source_id: 'system.clock' }, weather: { enabled: false, source_id: 'weather.open_meteo', provider: 'open_meteo', latitude: null, longitude: null, timezone: 'auto', refresh_seconds: 600, timeout_seconds: 1.5, failures_before_open: 3, circuit_open_seconds: 600, cache_ttl_seconds: 1800 }, sensors: { stale_after_seconds: 5, accepted_sources: { heart_rate: ['sensor.heart_rate'], motion: ['sensor.motion'], light: ['sensor.light'], posture: ['sensor.posture'] } }, simulator: { interval_seconds: .5 }, osc: { enabled: true, host: '0.0.0.0', port: 8002 } },
  policy: { update_hz: 10, weights: { energy: { bci_arousal: .70, heart_rate: .15, motion: .10, circadian: .05 }, pulse: { bci_arousal: .60, cadence: .25, heart_rate: .15 }, brightness: { bci_valence: .75, daylight: .15, weather: .10 }, spatial_width: { motion: .35, posture_expansion: .35, baseline: .30 } }, smoothing: { attack_seconds: 2, release_seconds: 6, deadband: .03 }, confidence: { freeze_motif_below: .45, full_variation_above: .75 }, limits: { auxiliary_max_contribution: .30 } },
  form: { template: 'adaptive_rondo', beats_per_bar: 4, phrase_bars: 2, minimum_phrases_per_section: 2, maximum_phrases_per_section: 4, emotion_change_budget: 3, slow_window_seconds: 16, fast_window_seconds: 4, transition_confidence: .60, sections: [{ id: 'intro', role: 'intro' }, { id: 'A1', role: 'identity' }, { id: 'B', role: 'contrast' }, { id: 'A2', role: 'return' }, { id: 'C', role: 'development' }, { id: 'climax', role: 'climax' }, { id: 'A3', role: 'return' }, { id: 'coda', role: 'coda' }], transitions: { intro: ['A1'], A1: ['A1', 'B'], B: ['B', 'A2'], A2: ['A2', 'C'], C: ['C', 'climax'], climax: ['A3'], A3: ['A3', 'coda'], coda: [] } },
  tonal: { default_root: 'C', base_scale: 'gong', scale_constraint: 'strict', scales: { gong: [0, 2, 4, 7, 9], shang: [0, 2, 5, 7, 10], jue: [0, 3, 5, 8, 10], zhi: [0, 2, 5, 7, 9], yu: [0, 3, 5, 7, 10], major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] } },
  motif: { bars: 2, beats_per_bar: 4, base_pitch: 60, allowed_subdivisions: [.25, .5, 1], density_thresholds: { medium_above: .45, fast_above: .78 }, valence_thresholds: { low_below: .38, high_above: .62 }, contours: { low_valence: 'descending', neutral: 'wave', high_valence: 'ascending' }, anchors: { beats: [0, 4, 7], immutable: true }, transform_by_form: { intro: 'simplify', identity: 'identity', contrast: 'transpose', development: 'invert', climax: 'compress', return: 'recall', coda: 'cadence' }, transform_settings: { simplify_stride: 2, transpose_scale_steps: 1, compression_ratio: .5, cadence_duration_beats: 2 } },
  melody: { provider: 'magenta_rt2', model: 'mrt2_small', worker_url: 'ws://127.0.0.1:8766/v1/stream', frame_hz: 25, prompt_template: '{mood} {energy} solo marimba improvisation, single clear notes, {articulation} articulation', transcription: { pitch_range: [48, 96], stable_frames: 2, minimum_note_ms: 80 }, guardrails: { scale_snap: true, strong_beat_chord_snap: true, octave_suppression: true, soft_grid: '1/16', snap_tolerance_ms: 45 }, fallback: 'motif_rule_continuation', audio: { enabled: true, gain: .20 } },
  harmony: { provider: 'rule', notochord: { enabled: false, timeout_seconds: .20, roles: ['harmony', 'bass', 'inner_voice'] }, progressions: { identity: ['I', 'IV', 'V', 'I'], contrast: ['vi', 'IV', 'ii', 'V'], development: ['ii', 'V', 'iii', 'vi'], climax: ['IV', 'V', 'V', 'I'], return: ['I', 'IV', 'V', 'I'], coda: ['IV', 'I', 'I', 'I'] }, counterpoint: { enabled: true, maximum_voices: 2, forms: ['contrast', 'development'], entry_delay_beats: 2, interval_semitones: 7, allow_inversion: true, reject_parallel_fifths: true, reject_parallel_octaves: true } },
  orchestration: { roles: { marimba: { enabled: true, base_density: .75, base_velocity: 82 }, snare: { enabled: true, base_density: .30, base_velocity: 72, note: 38 }, cymbal: { enabled: true, base_density: .18, base_velocity: 65, note: 49 }, kick: { enabled: true, base_density: .28, base_velocity: 78, note: 36 }, bass: { enabled: true, base_density: .35, base_velocity: 68 }, pad: { enabled: true, base_density: .20, base_velocity: 48 }, fx: { enabled: true, base_density: .10, base_velocity: 42 } }, independent_patterns: true, shared_subdivisions: ['1/4', '1/8', '1/16'], stems: { enabled: true, root: 'music_library/stems', crossfade_seconds: 4, default_gain: .15 } },
  outputs: { mode: 'both', midi: { enabled: true, port_contains: 'IAC', channels: { marimba: 1, harmony: 2, bass: 3, pad: 5, fx: 6, kick: 10, snare: 10, cymbal: 11 } }, osc: { enabled: true, targets: [{ id: 'touchdesigner', host: '127.0.0.1', port: 9000, enabled: true }], state_hz: 30 }, audio: { enabled: true, sample_rate: 48000, output_device: null, master_gain: .65 }, logging: { ring_size: 500, persist_jsonl: true } },
};
const glossary: Record<string, string> = {
  strategy:'自动演出策略|统一使用 BCI 主导的自适应策略，不提供用户模式切换。', bci:'BCI 核心输入|效价、唤醒度与张力的主要来源。', time:'本机时间|以本地时间提供昼夜基线。', weather:'天气|公共天气服务辅助调制，不应阻塞音乐时钟。', sensors:'辅助传感器|登记心率、运动、光线与体态信号。', simulator:'信号模拟器|无真实设备时产生测试信号。', source_id:'来源标识|用于识别输入数据来源，必须与发送方一致。', enabled:'启用|决定此分组功能是否参与运行；本原型中不会启动任何服务。', stale_after_seconds:'信号保留时长（秒）|超过此时间未收到数据后视为陈旧；BCI 开始回归中性。', neutral_return_seconds:'回归中性时长（秒）|BCI 失联保留期结束后，缓慢回归中性状态所需时间。', minimum_confidence:'最低置信度|0–1，低于阈值时减少变化并保持动机。', provider:'提供器|选择此模块的信号或生成来源。仅展示当前规划的提供器。', latitude:'纬度（°）|−90 到 90；留空代表尚未指定演出位置，不使用 IP 定位。', longitude:'经度（°）|−180 到 180；启用天气前需要同时指定经纬度。', timezone:'时区|auto 使用服务根据坐标确定的时区，也可输入 Asia/Shanghai 等 IANA 时区。', refresh_seconds:'刷新间隔（秒）|天气后台查询的间隔；默认 600 秒。', timeout_seconds:'超时上限（秒）|超过时限放弃本次请求，使用缓存或规则回退。', failures_before_open:'熔断失败次数|连续失败达到此次数后，暂时停止外部请求。', circuit_open_seconds:'熔断冷却（秒）|暂停请求的时长；结束后允许重试。', cache_ttl_seconds:'缓存有效期（秒）|最后有效天气值的最长使用时间，过期视为缺失。', accepted_sources:'接收来源清单|每类传感器允许的来源标识，可增加多个设备。', heart_rate:'心率|心率输入来源或其在当前映射中的权重。', motion:'运动|运动周期对脉冲的影响比例。', light:'光线|光照传感器的来源标识。', posture:'体态|体态输入来源；内核不依赖 Kinect SDK。', interval_seconds:'采样间隔（秒）|模拟器相邻采样间的时间。', osc:'OSC 网络|输入页为监听地址；输出页为发送目标，二者职责不同。', host:'IP / 主机地址|输入监听 0.0.0.0 表示所有网卡；输出 127.0.0.1 表示本机。', port:'端口|1–65535，须与发送或接收软件配置一致。', update_hz:'策略更新频率（Hz）|每秒计算音乐意图的次数，不是音乐速度。', weights:'输入权重|每组权重用于同一个音乐维度，建议总和为 1。', energy:'能量|决定音乐活跃程度的输入比例。', pulse:'脉冲|决定节奏脉冲的输入比例。', brightness:'明亮度|决定明亮程度的输入比例。', spatial_width:'空间宽度|决定空间展开程度的输入比例。', bci_arousal:'BCI 唤醒度权重|0–1；保持 BCI 的核心情绪主导地位。', bci_valence:'BCI 效价权重|0–1；正负情绪主要由 BCI 决定。', circadian:'昼夜基线权重|时间提供的缓慢能量调制比例。', cadence:'运动步频权重|运动周期对脉冲的影响比例。', daylight:'日照权重|昼夜信息对明亮度的影响比例。', posture_expansion:'体态展开权重|身体展开程度对空间宽度的影响比例。', baseline:'固定基线权重|不随即时传感器变化的稳定成分。', smoothing:'平滑|控制音乐参数响应速度，避免抖动。', attack_seconds:'上升响应（秒）|数值增大时的平滑时间。', release_seconds:'下降响应（秒）|数值减小时的平滑时间。', deadband:'变化死区|小于此幅度的变化忽略，避免频繁调整。', confidence:'置信度策略|低质量信号应降低变化，而不是增加随机性。', freeze_motif_below:'保持动机阈值|置信度低于此值时保留当前动机。', full_variation_above:'完整变形阈值|置信度高于此值时允许完整变化幅度。', limits:'辅助调制限制|防止辅助输入覆盖 BCI 的核心判断。', auxiliary_max_contribution:'辅助贡献上限|0–1；辅助传感器总体影响的限制。', template:'曲式模板|当前原型采用自适应回旋结构。', beats_per_bar:'每小节拍数|一小节包含多少拍，需与动机设置协调。', phrase_bars:'每乐句小节数|用于确定乐句边界，转场在边界执行。', minimum_phrases_per_section:'每段最少乐句|避免情绪波动造成过快切段。', emotion_change_budget:'情绪变化预算|一场演出允许的重要情绪变化次数。', slow_window_seconds:'慢时间窗（秒）|用于稳定的结构与情绪判断。', fast_window_seconds:'快时间窗（秒）|用于短时响应，不直接造成频繁结构切换。', transition_confidence:'转场置信度|信号达到此阈值才允许情绪驱动的转场。', sections:'乐段顺序|按从上到下的次序规划演出；可增删和移动。乐段标识必须唯一。', transitions:'允许转场|每个起点可到达的乐段标识；包含自身表示可停留，空列表表示结束。修改乐段标识后需同步检查这里。', id:'唯一标识|乐段或目标的名称；同一列表内不可重复。', role:'曲式角色|决定乐段用途及对应的动机变形、和声路线。', default_root:'默认主音|整场演出的调性中心；第一版演出过程中保持不变。', base_scale:'基础调式|整场演出的基本音高语法；情绪变化不会直接切换它。', scale_constraint:'调内约束强度|控制模型转录后的音高修正程度；第一阶段建议使用严格调内。', scales:'高级音阶定义|定义每种基础调式所包含的相对音级。正常使用只需选择基础调式，无需修改这里。', bars:'动机小节数|初始音乐材料的长度，第一版为 1–2 小节。', base_pitch:'动机中心音（MIDI）|动机音高的中心，60 为中央 C。', allowed_subdivisions:'允许时值（拍）|0.25 为四分之一拍，0.5 为半拍，1 为一拍。', contours:'情绪旋律轮廓|根据效价选择上行、下行或波浪型。', low_valence:'低效价|偏消极情绪时的轮廓。', neutral:'中性|情绪居中时的轮廓。', high_valence:'高效价|偏积极情绪时的轮廓。', anchors:'主题锚点|需要保持可辨识性的动机位置。', beats:'锚点位置（拍）|从第 0 拍开始计数，应落在动机总拍数内。', immutable:'固定锚点|开启后主题锚点不参与自由变形。', transform_by_form:'乐段变形|不同曲式角色对应的动机发展操作。', model:'模型|当前规划使用本地 MRT2 small。', worker_url:'模型进程地址|版本化 WebSocket 地址；正式运行只允许 localhost / 127.0.0.1。', frame_hz:'模型帧率（Hz）|MRT2 模型固定以 25 Hz 工作，不是任意性能调节项。', prompt_template:'提示词模板|允许使用 {mood}、{energy}、{articulation}、{form}；应用配置时会拒绝未知或损坏的变量。', transcription:'音频转 MIDI|这里的音域、稳定帧数和最短音长会直接传入实时转录器。', pitch_range:'转录音域（MIDI）|同时限制模型音高检测与最终 MIDI 输出范围。', stable_frames:'稳定帧数|音高连续稳定多少个 40ms 帧后确认；增大更稳定但增加延迟。', minimum_note_ms:'最短音长（毫秒）|保证活动音符至少持续此时长，同时抑制过快的同音重触发。', guardrails:'流式护栏|转录后进行有限修正，不生成多候选或回滚。', scale_snap:'音阶校正|将非调式音校正到允许音阶。', strong_beat_chord_snap:'强拍和弦校正|强拍优先使用当前和弦的实际大、小或减三和弦音。', octave_suppression:'异常八度抑制|抑制转录产生的异常八度跳变。', soft_grid:'软吸附网格|按所选 1/4、1/8 或 1/16 网格吸附；距离较远的旋律保持原始时点。', snap_tolerance_ms:'吸附容差（毫秒）|距离网格不超过此时长时才校正。', fallback:'故障续演策略|模型失效后从当前动机位置由规则继续演奏。', audio:'音频总线|旋律页是模型原声，输出页是统一音频设备。', gain:'模型原声增益|0–1；仅影响 MRT2 原始音频，不改变 MIDI 力度。', notochord:'Notochord 候选|只为和声、低音和内声部提供候选，失败回退规则。', roles:'声部|每个声部有独立职责与设置。', progressions:'和弦路线|从左到右依次演奏，允许重复和弦；以罗马数字表示相对级数。', counterpoint:'二声部对位|初版模仿、移位和反向，不等同完整赋格。', maximum_voices:'最大声部数|第一版仅支持二声部。', forms:'启用乐段角色|仅在选定角色使用对位。', entry_delay_beats:'模仿进入延迟（拍）|第二声部相对第一声部的时间偏移。', interval_semitones:'模仿移位（半音）|第二声部相对主题的音高位移，可为负值。', allow_inversion:'允许反向|将主题的上行与下行方向对调。', reject_parallel_fifths:'检查平行五度|排除基本的平行纯五度走向。', reject_parallel_octaves:'检查平行八度|排除基本的平行八度走向。', base_density:'基础密度|0–1；越高越活跃，不代表每个旋律音都触发伴奏。', base_velocity:'基础力度（MIDI）|1–127，越高通常越响。', note:'打击乐音符（MIDI）|对应音源或真实乐器的触发音高，需与接收端映射一致。', independent_patterns:'独立声部型态|各声部共享时钟但不逐音跟随马林巴旋律。', shared_subdivisions:'共享细分|各声部共同允许的节拍网格。', stems:'背景素材|策展背景音频的循环与交叉淡化设置。', root:'素材目录|背景 Stem 所在的本地目录；本原型不会读取文件。', crossfade_seconds:'交叉淡化（秒）|背景素材切换时旧声淡出、新声淡入的时长。', default_gain:'背景默认增益|0–1；避免背景遮盖核心旋律。', mode:'输出组合|MIDI、OSC 或两者并行；音频另由音频开关控制。', midi:'MIDI 乐器输出|统一端口和按声部路由的通道。', port_contains:'MIDI 端口匹配|按名称片段匹配端口，例如 IAC；本原型不会扫描设备。', channels:'声部通道|1–16；同通道声部共享接收端设置，需确认设备映射。', targets:'OSC 目标列表|可增加多个接收端；TouchDesigner 默认本机端口 9000。', state_hz:'状态推送频率（Hz）|OSC 状态消息频率，不改变音乐速度。', sample_rate:'采样率（Hz）|音频输出采样率，应与设备兼容。', output_device:'音频设备名称|留空使用系统默认；本原型不扫描或连接设备。', master_gain:'主输出增益|0–1；统一音频总音量，不控制真实 MIDI 乐器音量。', logging:'日志|统一控制台缓冲与 Session 持久记录。', ring_size:'控制台缓冲条数|保留的最近事件数量，避免界面无限增长。', persist_jsonl:'保存事件日志|按行保存统一事件，供回放和排查使用。',
};
export const names: Record<string,string> = { gong:'宫',shang:'商',jue:'角',zhi:'徵',yu:'羽',major:'大调',minor:'自然小调',strict:'严格调内',ornamental:'允许短暂装饰音',chromatic:'自由半音',intro:'引子',identity:'主题',contrast:'对比',development:'发展',climax:'高潮',return:'回归',coda:'尾声',marimba:'马林巴',snare:'小军鼓',cymbal:'镲',kick:'大鼓',bass:'低音',pad:'铺底',fx:'效果声',harmony:'和声',inner_voice:'内声部',ascending:'上行',descending:'下行',wave:'波浪',simplify:'简化',transpose:'移位',invert:'反向',compress:'压缩',recall:'再现',cadence:'终止',adaptive_performance:'自适应演出',adaptive_rondo:'自适应回旋',magenta_rt2:'Magenta MRT2',rule:'规则和声',both:'MIDI + OSC',midi:'仅 MIDI',osc:'仅 OSC',open_meteo:'Open-Meteo',motif_rule_continuation:'规则动机续演' };
export function info(path: string): { label: string; help: string } {
  const key = path.split('.').at(-1)!;
  const harmonyHelp: Record<string, [string, string]> = {
    notochord: ['Notochord 候选', '按所选声部分别为 Pad 配置、低音与内声部提供受和弦约束的候选；失败时回退规则结果。'],
    roles: ['声部', '选择允许 Notochord 辅助的目标：和声对应 Pad 配置，低音对应 Bass，内声部对应每小节的和弦内音。'],
    progressions: ['和弦路线', '从左到右逐小节演奏；大写为大三和弦，小写为小三和弦，° 为减三和弦。'],
    counterpoint: ['二声部对位', '将主题延迟、移位或反向后形成第二旋律声部。'],
    maximum_voices: ['最大声部数', '1 表示关闭附加声部，2 表示主题加一条对位声部。'],
    forms: ['启用乐段角色', '仅在选定角色使用对位。'],
    entry_delay_beats: ['模仿进入延迟（拍）', '第二声部相对第一声部的时间偏移。'],
    interval_semitones: ['模仿移位（半音）', '正数向上移位，负数向下移位。'],
    allow_inversion: ['允许反向', '开启后在发展乐段将主题的上行与下行方向对调。'],
    reject_parallel_fifths: ['检查平行五度', '检测两个声部同向移动形成的连续纯五度，并调整第二声部。'],
    reject_parallel_octaves: ['检查平行八度', '检测两个声部同向移动形成的连续同度或八度，并调整第二声部。'],
  };
  if (path.startsWith('harmony.') && harmonyHelp[key]) return { label: harmonyHelp[key][0], help: harmonyHelp[key][1] };
  if (key === 'motion') return { label: '运动', help: '运动输入来源或其在当前映射中的权重。' };
  const motifHelp: Record<string, [string, string]> = {
    allowed_subdivisions: ['允许时值（拍）', '低、中、高密度分别使用列表中的最大、中间和最小值；0.25 拍为十六分音符，0.5 拍为八分音符，1 拍为四分音符。'],
    density_thresholds: ['密度阈值', '决定何时从较慢时值切换到中速、快速时值。'],
    medium_above: ['中密度起点', '音乐密度达到此值时使用允许时值的中间档。'],
    fast_above: ['高密度起点', '音乐密度达到此值时使用允许时值的最小档。'],
    valence_thresholds: ['效价阈值', '将效价分成低、中、高三个区域。'],
    low_below: ['低效价上限', '效价小于等于此值时使用低效价轮廓。'],
    high_above: ['高效价下限', '效价大于等于此值时使用高效价轮廓。'],
    contours: ['情绪旋律轮廓', '根据效价阈值选择这里配置的上行、下行或波浪型。'],
    low_valence: ['低效价', '效价小于等于低效价阈值时实际使用的轮廓。'],
    neutral: ['中性', '效价位于两个阈值之间时实际使用的轮廓。'],
    high_valence: ['高效价', '效价大于等于高效价阈值时实际使用的轮廓。'],
    anchors: ['主题锚点', '需要保持动机身份的节拍位置。'],
    immutable: ['固定锚点', '开启后锚点在简化、移位、反向和压缩中保持不变；尾声将最后一个音收束到主音，属于结构性例外。'],
    transform_by_form: ['乐段变形', '读取曲式当前角色，并实际执行对应的动机发展操作。'],
    transform_settings: ['变形参数', '控制简化、移位、压缩和终止的实际幅度。'],
    simplify_stride: ['简化间隔', '每隔多少个音保留一个，锚点始终保留。'],
    transpose_scale_steps: ['移位音级数', '可变音符沿当前调式移动多少个音级。'],
    compression_ratio: ['压缩比例', '缩短可变音符时值并加入发展音；越小越密集。'],
    cadence_duration_beats: ['终止音长度（拍）', '尾声最后一个音收束到当前调性主音后的目标持续拍数。'],
  };
  if (path.startsWith('motif.') && motifHelp[key]) return { label: motifHelp[key][0], help: motifHelp[key][1] };
  if (key === 'maximum_phrases_per_section') return { label: '每段最多乐句', help: '情绪稳定或置信度不足时可以继续停留；达到此数量后仍会进入下一段，保证完整遍历曲式。' };
  if (/\.(melody_range|pitch_range)\.\d+$/.test(path)) return { label: key === '0' ? '最低音（MIDI）' : '最高音（MIDI）', help: 'MIDI 60 为中央 C；最低音不得高于最高音。' };
  if (/^\d+$/.test(key)) return { label: `第 ${Number(key)+1} 项`, help: info(path.split('.').slice(0,-1).join('.')).help };
  const entry = glossary[key]?.split('|');
  return { label: entry?.[0] || names[key] || key, help: entry?.[1] || (path.includes('.scales.') ? '相对主音的半音偏移（0–11），按音高顺序排列。' : path.includes('.transitions.') ? '选择允许到达的乐段；自身表示停留，空列表表示结束。' : path.includes('.channels.') ? '此声部的 MIDI 通道，范围 1–16。' : path.includes('.progressions.') ? '按顺序设置此乐段的和弦，允许重复。' : '此角色的局部配置，仅保存在界面草稿中。') };
}
export function choices(path: string): (string | number)[] | undefined {
  const p = path.replace(/\.\d+$/, ''); const k = p.split('.').at(-1)!;
  if (p.startsWith('harmony.progressions.')) return ['I','ii','iii','IV','V','vi','vii°'];
  if (p.startsWith('motif.contours.')) return ['ascending','descending','wave'];
  if (p.startsWith('motif.transform_by_form.')) return ['simplify','identity','transpose','invert','compress','recall','cadence'];
  if (k === 'role' || p === 'harmony.counterpoint.forms') return ['intro','identity','contrast','development','climax','return','coda'];
  if (k === 'default_root' || k === 'allowed_roots') return ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  if (k.endsWith('_scale')) return ['gong','shang','jue','zhi','yu','major','minor'];
  if (k === 'scale_constraint') return ['strict','ornamental','chromatic'];
  if (k === 'soft_grid' || k === 'shared_subdivisions') return ['1/4','1/8','1/16'];
  if (k === 'allowed_subdivisions') return [.25,.5,1];
  if (p === 'harmony.notochord.roles') return ['harmony','bass','inner_voice'];
  const fixed: Record<string,(string|number)[]> = { strategy:['adaptive_performance'],template:['adaptive_rondo'],model:['mrt2_small'],fallback:['motif_rule_continuation'],mode:['midi','osc','both'],sample_rate:[44100,48000,96000] };
  if (k === 'provider') return p.startsWith('inputs') ? ['open_meteo'] : p.startsWith('melody') ? ['magenta_rt2'] : ['rule'];
  return fixed[k];
}
export function bounds(path: string) {
  const key = path.split('.').at(-1)!;
  if (key === 'minimum_phrases_per_section') return { min:2,max:4,step:1 };
  if (key === 'maximum_phrases_per_section') return { min:2,max:8,step:1 };
  if (key === 'latitude') return { min:-90,max:90,step:.01 };
  if (key === 'longitude') return { min:-180,max:180,step:.01 };
  if (key === 'frame_hz') return { min:25,max:25,step:1 };
  if (key === 'maximum_voices') return { min:1,max:2,step:1 };
  if (key === 'bars') return { min:1,max:2,step:1 };
  if (path.includes('.channels.')) return { min:1,max:16,step:1 };
  if (key === 'port') return { min:1,max:65535,step:1 };
  if (/pitch_range|melody_range/.test(path) || /base_pitch|^note$/.test(key)) return { min:0,max:127,step:1 };
  if (key === 'base_velocity') return { min:1,max:127,step:1 };
  if (key === 'simplify_stride') return { min:1,max:8,step:1 };
  if (key === 'transpose_scale_steps') return { min:-7,max:7,step:1 };
  if (key === 'cadence_duration_beats') return { min:.25,max:12,step:.25 };
  if (path.includes('.scales.')) return { min:0,max:11,step:1 };
  if (key === 'interval_semitones') return { min:-24,max:24,step:1 };
  if (/weights\.|thresholds|compression_ratio|confidence|density|gain|deadband|contribution|freeze_motif|full_variation/.test(path)) return { min:0,max:1,step:.01 };
  if (/seconds$/.test(key)) return { min:0,max:86400,step:.1 };
  return { min:0,max:100000,step:1 };
}
