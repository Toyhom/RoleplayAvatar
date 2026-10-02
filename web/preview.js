import {t} from './i18n.js';
// Original procedural characters for the CPU protocol preview.
import {actionPose} from '/static/actions.js';

export class PreviewStage {
  constructor(canvas,onStatus) {
    this.canvas=canvas;this.context=canvas.getContext('2d');this.onStatus=onStatus;
    this.generation=0;this.loaded=false;this.active=false;
    const tick=()=>{if(this.active&&this.loaded)this.render();requestAnimationFrame(tick);};
    requestAnimationFrame(tick);
  }
  async load(character) {
    this.character=character;this.frame=null;this.face=null;this.actionPreview=null;
    this.sceneInfo={character:character.profile.character_id,renderer:'diagnostic-canvas'};
    this.motionEvidence={speechFrames:0,maxMouth:0,maxJointDelta:0};
    this.loaded=true;
  }
  setMode(mode) {this.mode=mode;if(mode!=='speaking'){this.frame=null;this.face=null;this.actionPreview=null;}}
  setPerformance(frame,face) {this.frame=frame;this.face=face;}
  previewAction(name) {this.actionPreview={name,start:performance.now()/1000};}
  render() {
    const box=this.canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio,2);
    const w=Math.round(box.width*dpr),h=Math.round(box.height*dpr);
    if(!w||!h)return;
    if(this.canvas.width!==w||this.canvas.height!==h){this.canvas.width=w;this.canvas.height=h;}
    const ctx=this.context,t=performance.now()/1000,values=this.face?.values??{};
    let cues=this.frame?.actions??[],seconds=this.frame?.action_time_s??0;
    if(this.actionPreview){seconds=t-this.actionPreview.start;cues=[{name:this.actionPreview.name,start_s:0,duration_s:2,strength:.8}];if(seconds>=2)this.actionPreview=null;}
    const pose=actionPose(cues,seconds);this.actionState=pose;
    const mouth=Math.max(0,Math.min(1,values.jaw_open??0));
    const id=this.character.profile.character_id,robot=id.includes('robot'),dragon=id.includes('dragon');
    const color=robot?'#a7bfd2':dragon?'#a9c78e':'#d9b9a7';
    ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#edf3ec';ctx.fillRect(0,0,w,h);
    const scale=Math.min(w/420,h/420)*(this.closeup?1.1:.9);
    ctx.translate(w/2+pose.bodyX*w,h*.55+pose.bodyY*h);ctx.scale(scale,scale);
    const ellipse=(x,y,rx,ry,fill)=>{ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();};
    ellipse(0,125,105,12,'#d8e4d4');
    ctx.rotate(pose.bodyTilt);ellipse(0,64,75,70,color);
    ctx.translate(pose.headX*3,pose.headY*3+Math.sin(t*1.5)*2);ctx.rotate(pose.tilt);
    if(dragon){ellipse(-66,-65,18,42,'#719357');ellipse(66,-65,18,42,'#719357');}
    if(robot){ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(-87,-98,174,146,30);ctx.fill();ctx.fillStyle='#527486';ctx.fillRect(-3,-125,6,30);ellipse(0,-131,10,10,'#dcac65');}
    else ellipse(0,-30,88,83,color);
    const blink=Math.pow(Math.max(0,Math.cos(t*1.15)),52);
    ellipse(-30,-36,8,Math.max(1,11*(1-blink)),'#30483b');ellipse(30,-36,8,Math.max(1,11*(1-blink)),'#30483b');
    ellipse(-49,-6,14,6,'#cf9f91');ellipse(49,-6,14,6,'#cf9f91');
    ellipse(0,7,19+6*(values.happy??0),2+18*mouth,'#655044');
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.font='12px system-ui';ctx.fillStyle='#6e8375';ctx.textAlign='center';
    ctx.fillText(t("CPU preview · 回放示例"),box.width/2,box.height-20);
    if(this.frame)this.motionEvidence.speechFrames++;
    this.motionEvidence.maxMouth=Math.max(this.motionEvidence.maxMouth,mouth);
    this.motionEvidence.maxJointDelta=Math.max(this.motionEvidence.maxJointDelta,Math.abs(pose.headX)+Math.abs(pose.headY));
  }
}
