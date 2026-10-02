import {t} from './i18n.js';
// Optional native Cubism renderer. Core is loaded separately under Live2D's license.
import * as PIXI from 'pixi.js';
import {Live2DModel, config} from 'pixi-live2d-display/cubism4';
import {actionPose} from './actions.js';
Live2DModel.registerTicker(PIXI.Ticker);
config.sound=false; // Speech always comes from our cancellable audio sample clock.

export class CubismStage {
  constructor(canvas,onStatus){
    this.canvas=canvas;this.onStatus=onStatus;this.generation=0;this.loaded=false;
    this.active=true;this.mode='listening';this.smooth={};this.look=[0,0];
    this.app=new PIXI.Application({view:canvas,backgroundAlpha:0,antialias:true,autoDensity:true,resolution:Math.min(devicePixelRatio,2),preserveDrawingBuffer:true});
    new ResizeObserver(()=>this.resize()).observe(canvas.parentElement);
    this.app.ticker.add(()=>this.render());
  }
  async load(character){
    const generation=++this.generation;this.loaded=false;this.character=character;
    this.frame=null;this.face=null;this.actionPreview=null;this.smooth={};
    this.model?.destroy({children:true,texture:true,baseTexture:true});this.model=null;
    const model=await Live2DModel.from(`/assets/${character.profile.character_id}/${character.profile.live2d_model}`,{autoUpdate:false,autoInteract:true});
    if(generation!==this.generation){model.destroy({children:true,texture:true,baseTexture:true});return;}
    this.model=model;this.app.stage.addChild(model);model.anchor.set(.5,.5);
    model.internalModel.on('beforeModelUpdate',()=>this.direct());
    const m=model.internalModel;
    this.sceneInfo={character:character.profile.character_id,renderer:'native-cubism',parameters:m.coreModel._model.parameters.ids,motions:Object.keys(m.motionManager.definitions),physics:!!m.physics};
    this.motionEvidence={speechFrames:0,maxMouth:0,maxJointDelta:0,maxBodyDelta:0,maxExpression:0,actionFrames:{}};
    this.loaded=true;this.resize();this.onStatus(t("准备好了"));
  }
  resize(){
    const {width,height}=this.canvas.parentElement.getBoundingClientRect();if(!width||!height)return;
    this.app.renderer.resize(width,height);
    if(!this.model)return;
    const m=this.model, internal=m.internalModel;
    const scale=Math.min(width/internal.width*.95,height/internal.height*.98)*(this.closeup?2.4:1);
    m.scale.set(scale);m.position.set(width*.5,height*.5+(this.closeup?height*.65:height*.02));
  }
  setPerformance(frame,face){this.frame=frame;this.face=face;}
  setMode(mode){this.mode=mode;if(mode!=='speaking'){this.frame=null;this.face=null;this.actionPreview=null;this.smooth={};}}
  previewAction(name){this.actionPreview={name,start:performance.now()/1000};}
  nativeMotion(group,index){this.model?.motion(group,index,3);}
  direct(){
    const core=this.model.internalModel.coreModel;
    const values=this.face?.values??{};
    const dt=Math.min(.1,this.app.ticker.deltaMS/1000);
    const get=(key)=>{const target=values[key]??0;return this.smooth[key]=(this.smooth[key]??0)+(target-(this.smooth[key]??0))*(1-Math.exp(-dt*25));};
    let cues=this.frame?.actions??[],seconds=this.frame?.action_time_s??0;
    if(this.actionPreview){seconds=performance.now()/1000-this.actionPreview.start;cues=[{name:this.actionPreview.name,start_s:0,duration_s:2,strength:.8}];if(seconds>=2)this.actionPreview=null;}
    const pose=actionPose(cues,seconds);this.actionState=pose;
    const jaw=get('jaw_open'),happy=get('happy'),sad=get('sad'),angry=get('angry'),soft=get('soft');
    const mapped=id=>this.character.profile.live2d_parameter_map?.[id]??id;
    const set=(id,value)=>core.setParameterValueById(mapped(id),value),add=(id,value)=>core.addParameterValueById(mapped(id),value);
    // Replace idle mouth curves so a silent avatar never mouths prerecorded speech.
    set('ParamMouthOpenY',jaw);set('ParamMouthForm',happy*.9+soft*.4-sad*.6-angry*.35);
    add('ParamAngleX',pose.headX*7);add('ParamAngleY',-pose.headY*8);
    add('ParamAngleZ',pose.tilt*140);add('ParamBodyAngleX',pose.bodyX*350);
    add('ParamBodyAngleY',pose.lean*100);add('ParamBodyAngleZ',pose.bodyTilt*160);
    add('ParamBrowLY',sad*-.35+angry*-.7);add('ParamBrowRY',sad*-.35+angry*-.7);
    add('ParamBrowLAngle',sad*-.6+angry*.75);add('ParamBrowRAngle',sad*-.6+angry*.75);
    set('ParamEyeLSmile',happy*.9+soft*.3);set('ParamEyeRSmile',happy*.9+soft*.3);
    this.model.y=this.app.screen.height*(.5+(this.closeup?.65:.02)+pose.bodyY);
    const e=this.motionEvidence;e.maxMouth=Math.max(e.maxMouth,jaw);e.maxJointDelta=Math.max(e.maxJointDelta,Math.abs(pose.headX)+Math.abs(pose.headY)+Math.abs(pose.tilt));e.maxBodyDelta=Math.max(e.maxBodyDelta,Math.abs(pose.bodyY)+Math.abs(pose.lean)+Math.abs(pose.bodyTilt));e.maxExpression=Math.max(e.maxExpression,happy,sad,angry,soft);
    if(this.frame)e.speechFrames++;for(const name of pose.active)e.actionFrames[name]=(e.actionFrames[name]??0)+1;
    this.parameterEvidence={jaw,emotion:Math.max(happy,sad,angry,soft),actions:pose.active};
  }
  render(){if(!this.active||!this.loaded)return;this.resize();this.model.update(Math.min(100,this.app.ticker.deltaMS));window.avatarRenderFps=this.app.ticker.FPS;}
}
