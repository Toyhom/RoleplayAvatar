import {t} from './i18n.js';
import {actionLabels} from '/static/actions.js';
import { AvatarStage } from '/static/dist/scene.js';
import { PuppetStage } from '/static/puppet.js';
import { PreviewStage } from '/static/preview.js';

let cubismReady;
async function nativeRenderer(){
  cubismReady??=new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src='/vendor/cubism-core.js';
    script.onload=resolve;script.onerror=()=>{cubismReady=null;script.remove();reject(Error(t("请先安装官方 Cubism Core 示例依赖")));};document.head.append(script);
  }).then(()=>import('/static/dist/cubism.js'));
  return (await cubismReady).CubismStage;
}

// All renderers consume the same audio-clock frames; switching keeps playback alive.
export class PresentationStage {
  constructor(canvas, onStatus) {
    this.onStatus = onStatus;
    this.canvas3d = canvas;
    this.canvas2d = document.getElementById('portrait-scene');
    this.canvasCubism = document.getElementById('cubism-scene');
    this.canvasPreview = document.getElementById('preview-scene');
    this.views = {};
    this.loaded = false;
    this.mode = 'listening';
    this.kind = localStorage.getItem('avatar-view') ?? '2d';
    this.closeup = localStorage.getItem('avatar-closeup') !== 'false';
    this.preview = null;
    this.generation = 0;
    document.querySelectorAll('[data-view]').forEach(button => {
      button.onclick = () => this.switch(button.dataset.view).catch(error => onStatus(error.message));
    });
    document.querySelectorAll('[data-expression]').forEach(button => {
      button.onclick = () => {
        this.preview = button.dataset.expression === 'auto' ? null : button.dataset.expression;
        document.querySelectorAll('[data-expression]').forEach(x => x.classList.toggle('active', x === button));
        this.apply();
      };
    });
    document.getElementById('action-preview').onchange = event => {
      if(event.target.value)this.current?.previewAction(event.target.value);
      event.target.value='';
    };
    document.getElementById('frame-view').onclick = () => {
      this.closeup = !this.closeup;
      localStorage.setItem('avatar-closeup',String(this.closeup));
      this.frameView();
    };
    document.getElementById('native-motion').onchange=event=>{
      if(event.target.value){const [group,index]=JSON.parse(event.target.value);this.current?.nativeMotion?.(group,index);}
      event.target.value='';
    };
    window.avatarPresentation = this;
  }

  async load(character) {
    this.character = character;
    document.getElementById('character-type').textContent=character.profile.presentation_modes[0]==='3d'?t("3D 角色"):character.profile.renderer_2d==='cubism'?t("Live2D 角色"):t("2D 角色");
    const allowed = character.profile.presentation_modes ?? ['3d'];
    if (!allowed.includes(this.kind)) this.kind = allowed[0];
    await this.switch(this.kind);
  }

  async switch(kind) {
    if (!this.character) return;
    if (!(this.character.profile.presentation_modes ?? ['3d']).includes(kind)) {
      throw Error(t("这个角色尚未准备此模式"));
    }
    const generation = ++this.generation;
    this.loaded = false;
    this.current = null;
    window.dispatchEvent(new Event('avatar:presentation'));
    this.kind = kind;
    localStorage.setItem('avatar-view', kind);
    const renderer=this.character.profile.package_status==='template_only'?'preview':kind==='2d'&&this.character.profile.renderer_2d==='cubism'?'cubism':kind;
    this.canvas3d.hidden = renderer !== '3d';
    this.canvas2d.hidden = renderer !== '2d';
    this.canvasCubism.hidden = renderer !== 'cubism';
    this.canvasPreview.hidden = renderer !== 'preview';
    for (const view of Object.values(this.views)) {
      view.active = false;
      view.generation++; // Invalidate an outstanding load, including the other renderer.
      view.engine?.stopRenderLoop();
      view.app?.stop();
    }
    let view = this.views[renderer];
    if (!view) {
      const Renderer=renderer==='preview'?PreviewStage:renderer==='cubism'?await nativeRenderer():renderer==='3d'?AvatarStage:PuppetStage;
      if(generation!==this.generation)return;
      view=new Renderer(renderer==='preview'?this.canvasPreview:renderer==='cubism'?this.canvasCubism:renderer==='3d'?this.canvas3d:this.canvas2d,this.onStatus);
      this.views[renderer] = view;
    }
    view.active = true;
    view.app?.start();
    if (view.engine) {
      view.engine.resize();
      view.engine.stopRenderLoop();
      view.engine.runRenderLoop(() => view.scene.render());
    }
    try {
      if (!view.loaded || view.character?.profile.character_id !== this.character.profile.character_id) {
        await view.load(this.character);
      }
      if (generation !== this.generation) return;
      this.current = view;
      view.setMode(this.mode);
      this.loaded = true;
      window.avatarSceneInfo = { ...view.sceneInfo, mode: kind };
      window.avatarMotionEvidence = view.motionEvidence;
      document.querySelectorAll('[data-view]').forEach(button => {
        button.classList.toggle('active', button.dataset.view === kind);
        button.disabled = !(this.character.profile.presentation_modes ?? ['3d']).includes(button.dataset.view);
      });
      document.querySelector('.orbit-hint').textContent = renderer==='preview'?t("CPU 回放"):kind === '2d' ? t("移动鼠标 · 视线跟随") : t("拖动旋转 · 滚轮缩放");
      if(renderer==='preview')document.getElementById('character-type').textContent=t("回放示例");
      document.getElementById('action-preview').disabled=!view.previewAction;
      const motions=document.getElementById('native-motion');motions.replaceChildren(new Option(t("原生动作"),''));
      if(view.model?.internalModel){for(const [group,items] of Object.entries(view.model.internalModel.motionManager.definitions))items.forEach((_,i)=>motions.add(new Option(`${group} ${i+1}`,JSON.stringify([group,i]))));}
      else if(view.nativeMotion){for(const group of view.container.animationGroups)motions.add(new Option(group.name,JSON.stringify([group.name,0])));}
      motions.hidden=motions.options.length===1;
      this.frameView();
      this.apply();
      this.onStatus(t("准备好了"));
    } finally {
      if (generation === this.generation) window.dispatchEvent(new Event('avatar:presentation'));
    }
  }

  frameView() {
    document.getElementById('frame-view').textContent = this.closeup ? t("全身") : t("近景");
    document.getElementById('frame-view').classList.toggle('active', this.closeup);
    if (!this.current) return;
    this.current.closeup = this.closeup;
    this.current.resize?.();
    if (this.current.camera) {
      this.current.camera.radius = this.closeup ? 2.5 : 4.9;
      this.current.camera.beta = this.closeup ? 1.43 : 1.2;
      this.current.camera.target.y = this.closeup ? 1.62 : 1.05;
    }
  }

  setMode(mode) {
    this.mode = mode;
    this.current?.setMode(mode);
    if (mode !== 'speaking') { this.frame = null; this.face = null; }
    this.apply();
  }

  setPerformance(frame, face) { this.frame = frame; this.face = face; this.apply(); }

  apply() {
    if (!this.current) return;
    let frame = this.frame, face = this.face;
    if (this.preview) {
      const emotion = this.preview === 'mouth' ? 'neutral' : this.preview;
      const values = { ...(face?.values ?? {}), happy: 0, sad: 0, angry: 0, soft: 0 };
      if (this.preview === 'mouth') { values.jaw_open = .95; values.mouth_round = .15; }
      else values[emotion] = 1;
      face = { ...face, values, expression: emotion };
    }
    this.current.setPerformance(frame, face);
    const labels = { neutral: t("自然"), happy: t("开心"), soft: t("温柔"), sad: t("低落"), angry: t("生气") };
    document.getElementById('expression-state').textContent = this.preview ? t("表情预览") : (labels[face?.expression] ?? t("自动表演"));
    const active=this.current.actionState?.active??[];
    document.getElementById('action-state').textContent=active.map(x=>actionLabels[x]).join(' · ');
  }
}
