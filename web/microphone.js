import {t} from './i18n.js';
// Explicit recording → transcription → optional send. Cancellation invalidates every await.
export class MicrophoneInput {
  constructor({onStart, onTranscript, onBusy}) {
    Object.assign(this, {onStart, onTranscript, onBusy});
    this.button = document.getElementById('microphone');
    this.cancelButton = document.getElementById('cancel-recording');
    this.status = document.getElementById('microphone-status');
    this.state = 'idle'; this.epoch = 0; this.ready = false;
    this.button.onclick = () => this.state === 'recording' ? this.finish() : this.start();
    this.cancelButton.onclick = () => this.cancel();
    window.addEventListener('pagehide', () => this.cancel());
    window.addEventListener('keydown', e => { if (e.key === 'Escape' && this.state !== 'idle') this.cancel(); });
    window.avatarMicrophone = this;
  }

  setAvailable(ready) {
    this.ready = ready;
    const supported = !!navigator.mediaDevices?.getUserMedia && !!window.MediaRecorder && !!window.AudioContext;
    this.button.disabled = ['requesting', 'transcribing'].includes(this.state) || (this.state === 'idle' && (!ready || !supported));
    if (this.state === 'idle' && !supported) this.status.textContent = t("麦克风需要 HTTPS 或 localhost 访问");
    else if (this.state === 'idle' && !ready) this.status.textContent = t("语音识别服务准备中");
  }

  stateTo(state, message) {
    this.state = state;
    this.status.textContent = message;
    this.button.textContent = state === 'recording' ? t("■ 结束并识别") : state === 'transcribing' ? t("识别中…") : t("● 语音输入");
    this.button.classList.toggle('recording', state === 'recording');
    this.button.disabled = ['requesting', 'transcribing'].includes(state) || (state === 'idle' && !this.ready);
    this.cancelButton.hidden = state === 'idle';
    this.onBusy(state !== 'idle');
  }

  async start() {
    if (this.state !== 'idle' || !this.ready) return;
    const epoch = ++this.epoch;
    this.onStart();
    this.stateTo('requesting', t("正在请求麦克风权限…"));
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
      if (epoch !== this.epoch) { stream.getTracks().forEach(t => t.stop()); return; }
      this.stream = stream;
      this.chunks = [];
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type));
      this.recorder = new MediaRecorder(stream, mimeType ? {mimeType} : {});
      this.recordingStopped = new Promise(resolve => { this.recorder.onstop = resolve; });
      this.recorder.ondataavailable = ({data}) => { if (epoch === this.epoch && data.size) this.chunks.push(data); };
      this.recorder.onerror = () => {
        if (epoch !== this.epoch) return;
        this.cancel(); this.status.textContent = t("录音设备中断，请重试");
      };
      this.recorder.start();
      for (const track of stream.getAudioTracks()) track.onended = () => {
        if (epoch === this.epoch && this.state === 'recording') this.finish();
      };
      this.started = performance.now();
      this.stateTo('recording', t("正在聆听 · 0 秒"));
      this.timer = setInterval(() => {
        const seconds = (performance.now() - this.started) / 1000;
        this.status.textContent = t("正在聆听 · {0} / 30 秒",Math.floor(seconds));
        if (seconds >= 29.5) this.finish();
      }, 200);
    } catch (error) {
      this.lastError={name:error.name,message:error.message};
      if (epoch !== this.epoch) return;
      this.cleanup();
      const denied = ['NotAllowedError', 'PermissionDeniedError'].includes(error.name);
      this.stateTo('idle', denied ? t("麦克风权限未开启，可在浏览器地址栏允许后重试") : t("无法使用麦克风，请检查设备后重试"));
    }
  }

  cleanup() {
    clearInterval(this.timer); this.timer = null;
    this.stream?.getTracks().forEach(t => t.stop()); this.stream = null;
    if (this.recorder) {
      this.recorder.onerror = null;
      if (this.recorder.state !== 'inactive') this.recorder.stop();
      this.recorder = null;
    }
    this.context?.close().catch(() => {}); this.context = null;
  }

  cancel() {
    ++this.epoch;
    this.abort?.abort(); this.abort = null;
    this.cleanup(); this.chunks = [];
    this.stateTo('idle', t("录音已取消"));
  }

  async finish() {
    if (this.state !== 'recording') return;
    const epoch = this.epoch, recorder = this.recorder;
    const stopped = this.recordingStopped;
    const elapsed = (performance.now() - this.started) / 1000;
    this.stateTo('transcribing', t("正在识别…"));
    this.cleanup();
    try {
      await stopped;
      if (epoch !== this.epoch) return;
      if (elapsed < .2) throw Error(t("录音太短，请说完一句话后再结束"));
      const encoded = await new Blob(this.chunks, {type: recorder.mimeType}).arrayBuffer();
      this.chunks = [];
      if (epoch !== this.epoch) return;
      // The browser decodes Opus/AAC and resamples to 16kHz, including Safari's MP4 recording.
      const context = new AudioContext({sampleRate: 16000});
      this.context = context;
      let decoded;
      try { decoded = await context.decodeAudioData(encoded); }
      finally { if (this.context === context) { this.context = null; await context.close(); } }
      if (epoch !== this.epoch) return;
      const count = Math.min(480000, decoded.length);
      const channels = Array.from({length: decoded.numberOfChannels}, (_, i) => decoded.getChannelData(i));
      const pcm = new Uint8Array(count * 2), view = new DataView(pcm.buffer);
      for (let i = 0; i < count; i++) {
        const value = Math.max(-1, Math.min(1, channels.reduce((n, c) => n + c[i], 0) / channels.length));
        view.setInt16(i*2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
      }
      let binary = '';
      for (let i = 0; i < pcm.length; i += 8192) binary += String.fromCharCode(...pcm.subarray(i,i+8192));
      this.abort = new AbortController();
      const response = await fetch('/api/transcribe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({pcm_base64:btoa(binary),sample_rate:16000}),signal:this.abort.signal});
      const result = await response.json();
      if (epoch !== this.epoch) return;
      if (!response.ok) throw Error(typeof result.detail === 'string' ? t(result.detail) : t("语音识别失败，请重试"));
      this.abort = null;
      this.stateTo('idle', result.text ? t("识别完成") : t("没有听清语音，请靠近麦克风重试"));
      if (result.text) this.onTranscript(result.text);
    } catch (error) {
      if (epoch === this.epoch) this.stateTo('idle', error.name === 'AbortError' ? t("已取消") : error.message);
    } finally {
      if (epoch === this.epoch) { this.abort = null; this.chunks = []; }
    }
  }
}
