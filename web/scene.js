import {t} from './i18n.js';
// The GLB import, skeleton retention and name-based control boundary follow the
// MIT-licensed DLP3D character loader. This adapter adds capability-based control,
// explicit roots and safe no-face/no-eye behavior for non-humanoid assets.
import { Engine, Scene, ArcRotateCamera, Vector3, Color3, Color4, HemisphericLight,
  DirectionalLight, MeshBuilder, StandardMaterial, TransformNode, Quaternion,
  SceneLoader, ShadowGenerator } from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import {actionPose} from './actions.js';

export class AvatarStage {
  constructor(canvas, onStatus) {
    this.engine = new Engine(canvas, true, {preserveDrawingBuffer: true, stencil: true});
    this.scene = new Scene(this.engine);
    this.scene.useRightHandedSystem = true;
    this.scene.clearColor = new Color4(0.945, 0.965, 0.925, 1);
    this.camera = new ArcRotateCamera('camera', -Math.PI/2, 1.23, 5, new Vector3(0,1.05,0), this.scene);
    this.camera.attachControl(canvas, true);
    this.camera.lowerRadiusLimit = 2.4; this.camera.upperRadiusLimit = 8;
    this.camera.lowerBetaLimit = .4; this.camera.upperBetaLimit = Math.PI/2-.05;
    this.camera.wheelPrecision = 65; this.camera.panningSensibility = 0;
    const ambient = new HemisphericLight('ambient', new Vector3(0,1,0), this.scene);
    ambient.intensity = .8; ambient.groundColor = new Color3(.21,.28,.30);
    const key = new DirectionalLight('key', new Vector3(-.5,-1,.5), this.scene);
    key.position = new Vector3(3,6,-4); key.intensity = .8;
    this.shadow = new ShadowGenerator(512, key);
    this.shadow.useBlurExponentialShadowMap = true; this.shadow.blurKernel = 8;
    const ground = MeshBuilder.CreateDisc('platform', {radius: 2.1, tessellation: 80}, this.scene);
    ground.rotation.x = Math.PI/2; ground.position.y = -.018; ground.receiveShadows = true;
    const material = new StandardMaterial('platformMaterial', this.scene);
    material.diffuseColor = new Color3(.82,.88,.75); material.specularColor = new Color3(.05,.05,.05);
    material.backFaceCulling = false; ground.material = material;
    const ring = MeshBuilder.CreateTorus('ring',{diameter:4.05,thickness:.012,tessellation:100},this.scene);
    ring.position.y = -.006;
    const glow = new StandardMaterial('ringMaterial', this.scene);
    glow.emissiveColor = new Color3(.44,.64,.37); glow.diffuseColor = new Color3(.44,.64,.37);
    ring.material = glow;
    this.onStatus=onStatus;this.generation=0;this.nodes=new Map();this.rest=new Map();this.morphs=new Map();
    this.frame=null;this.face=null;this.mode='listening';this.loaded=false;
    this.scene.onBeforeRenderObservable.add(()=>this.animate());
    this.engine.runRenderLoop(()=>this.scene.render());
    window.addEventListener('resize',()=>this.engine.resize());
    new ResizeObserver(()=>this.engine.resize()).observe(canvas);
  }

  async load(character) {
    const generation=++this.generation;
    this.loaded=false;this.onStatus(t("正在加载角色…"));
    this.frame=null;this.face=null;
    if(this.container)this.container.dispose();
    if(this.anchor)this.anchor.dispose();
    const container=await SceneLoader.LoadAssetContainerAsync(`/assets/${character.profile.character_id}/`, 'model.glb', this.scene);
    if(generation!==this.generation){container.dispose();return;}
    container.addAllToScene();this.container=container;this.character=character;
    this.anchor=new TransformNode('characterAnchor',this.scene);
    const top=[...container.meshes,...container.transformNodes].filter(n=>!n.parent);
    for(const node of top)node.parent=this.anchor;
    this.nodes=new Map([...container.transformNodes,...container.meshes].map(n=>[n.name,n]));
    this.rest=new Map();this.morphs=new Map();
    for(const mesh of container.meshes){
      mesh.isPickable=false;
      if(mesh.getTotalVertices()>0)this.shadow.addShadowCaster(mesh);
      const manager=mesh.morphTargetManager;
      if(manager)for(let i=0;i<manager.numTargets;i++){
        const target=manager.getTarget(i);
        if(!this.morphs.has(target.name))this.morphs.set(target.name,[]);
        this.morphs.get(target.name).push(target);
      }
    }
    // Asset-native idle for the authored creatures. DLP3D humanoid entry pose is
    // sampled and held; speech/head overlays have explicit joint ownership.
    this.nativeGroup=null;this.actionPreview=null;this.nativePreview=null;
    const idle=container.animationGroups.find(g=>g.name.toLowerCase()==='idle');this.idleGroup=idle;
    if(idle)idle.start(true);
    else if(container.animationGroups.length){
      const pose=container.animationGroups[0];pose.start(false);pose.goToFrame(pose.to);pose.pause();
    }
    for(const [name,node] of this.nodes){
      if(!node.rotationQuaternion)node.rotationQuaternion=Quaternion.FromEulerVector(node.rotation);
      this.rest.set(name,node.rotationQuaternion.clone());
    }
    for(const mesh of container.meshes)mesh.computeWorldMatrix(true);
    let minimum=new Vector3(Infinity,Infinity,Infinity), maximum=new Vector3(-Infinity,-Infinity,-Infinity);
    for(const mesh of container.meshes){
      if(!mesh.getTotalVertices())continue;
      const bounds=mesh.getBoundingInfo().boundingBox;
      minimum=Vector3.Minimize(minimum,bounds.minimumWorld);maximum=Vector3.Maximize(maximum,bounds.maximumWorld);
    }
    const height=maximum.y-minimum.y;
    const scale=character.profile.display_height_m/height;
    this.anchor.scaling.setAll(scale);
    this.anchor.position.set(-(minimum.x+maximum.x)*.5*scale,-minimum.y*scale,-(minimum.z+maximum.z)*.5*scale);
    this.anchor.rotation.y=character.profile.display_rotation_y_deg*Math.PI/180;
    this.camera.alpha=-Math.PI/2;this.camera.beta=1.2;this.camera.radius=4.9;
    this.camera.target.set(0,1.05,0);
    this.loaded=true;this.onStatus(t("准备好了"));
    this.sceneInfo={character:character.profile.character_id,meshes:container.meshes.length,
      skeletons:container.skeletons.length,bones:container.skeletons.reduce((n,s)=>n+s.bones.length,0),
      animations:container.animationGroups.map(g=>g.name),morphNames:[...this.morphs.keys()],height,scale};
    this.motionEvidence={speechFrames:0,maxJointDelta:0,maxMouth:0,maxBodyDelta:0,actionFrames:{},nativeFrames:{}};
  }

  setPerformance(frame,face){this.frame=frame;this.face=face;}
  setMode(mode){this.mode=mode;if(mode!=='speaking'){this.frame=null;this.face=null;this.actionPreview=null;this.nativePreview=null;}}
  previewAction(name){this.actionPreview={name,start:performance.now()/1000};}
  nativeMotion(name){this.nativePreview={name,start:performance.now()/1000};}
  playNative(name,phase){
    const group=this.container.animationGroups.find(g=>g.name===name);
    if(group!==this.nativeGroup){this.nativeGroup?.stop();this.idleGroup?.stop();this.nativeGroup=group;
      if(group){group.start(false);group.pause();}else this.idleGroup?.start(true);
    }
    if(group){group.goToFrame(group.from+(group.to-group.from)*Math.max(0,Math.min(1,phase)));this.motionEvidence.nativeFrames[name]=(this.motionEvidence.nativeFrames[name]??0)+1;}
  }

  animate(){
    if(!this.loaded)return;
    const dt=Math.min(.1,this.engine.getDeltaTime()/1000),t=performance.now()/1000;
    let cues=this.frame?.actions??[],seconds=this.frame?.action_time_s??0;
    if(this.actionPreview){seconds=t-this.actionPreview.start;cues=[{name:this.actionPreview.name,start_s:0,duration_s:2,strength:.8}];if(seconds>=2)this.actionPreview=null;}
    const pose=actionPose(cues,seconds);this.actionState=pose;
    const cue=cues.find(c=>pose.active.includes(c.name)&&this.character.profile.native_animation_map?.[c.name]);
    let native=cue?this.character.profile.native_animation_map[cue.name]:null,phase=cue?(seconds-cue.start_s)/cue.duration_s:0;
    if(this.nativePreview){const group=this.container.animationGroups.find(g=>g.name===this.nativePreview.name);const duration=group?(group.to-group.from)/(group.targetedAnimations[0]?.animation.framePerSecond??30):1;phase=(t-this.nativePreview.start)/Math.max(.4,duration);if(phase<1)native=this.nativePreview.name;else this.nativePreview=null;}
    if(this.character.profile.native_animation_map&&Object.keys(this.character.profile.native_animation_map).length)this.playNative(native,phase);
    this.anchor.rotation.z=pose.bodyTilt+pose.tilt*.25;this.anchor.rotation.x=pose.lean;
    for(const name of pose.active)this.motionEvidence.actionFrames[name]=(this.motionEvidence.actionFrames[name]??0)+1;
    this.motionEvidence.maxBodyDelta=Math.max(this.motionEvidence.maxBodyDelta,Math.abs(pose.lean)+Math.abs(pose.bodyTilt));
    const desired=this.frame?.rotations_delta_xyzw??{};
    for(const joint of this.character.rig_map.joints){
      if(!['expression','speech'].includes(joint.owner))continue;
      const node=this.nodes.get(joint.name),rest=this.rest.get(joint.name);
      if(!node||!rest)continue;
      let delta=desired[joint.name]?Quaternion.FromArray(desired[joint.name]):Quaternion.Identity();
      if(!desired[joint.name]&&joint.semantic==='head'){
        const amplitude=this.mode==='thinking'?.02:.007;
        delta=Quaternion.RotationAxis(new Vector3(...joint.local_axis),amplitude*Math.sin(t*1.1));
      }
      const target=rest.multiply(delta).normalize();
      Quaternion.SlerpToRef(node.rotationQuaternion,target,1-Math.exp(-dt*(joint.owner==='speech'?28:9)),node.rotationQuaternion);
      if(this.frame)this.motionEvidence.maxJointDelta=Math.max(this.motionEvidence.maxJointDelta,1-Math.abs(Quaternion.Dot(node.rotationQuaternion,rest)));
    }
    const blink=Math.pow(Math.max(0,Math.cos(t*1.35)),38);
    for(const channel of this.character.face_map.channels){
      if(!(channel.renderers??['3d']).includes('3d'))continue;
      const targetValue=channel.source==='blink'?blink:(this.face?.values?.[channel.target]??this.face?.values?.[channel.source]??0);
      for(const morph of this.morphs.get(channel.target)??[]){
        const value=Math.max(channel.minimum,Math.min(channel.maximum,targetValue));
        morph.influence+=(value-morph.influence)*(1-Math.exp(-dt*25));
        if(this.face&&channel.source==='jaw_open')this.motionEvidence.maxMouth=Math.max(this.motionEvidence.maxMouth,morph.influence);
      }
    }
    window.avatarRenderFps=this.engine.getFps();
    if(this.frame)this.motionEvidence.speechFrames++;
  }
}
