import {t} from './i18n.js';
import {actionLabels,emotionLabels} from '/static/actions.js';
import {MicrophoneInput} from '/static/microphone.js';
import {PresentationStage} from '/static/presentation.js';
const $=(id)=>document.getElementById(id);
const stage=new PresentationStage($('scene'),message=>{$('stage-status').textContent=message;});
let socket,context,currentTurn=null,nextTime=0,complete=false,muted=false,playing=false;
let sources=new Set(),scheduled=[],frames=[],faces=[],logs=[],count=0,characters=[],selected=null,assistantContent=null;
window.addEventListener('avatar:presentation',()=>{$('start').disabled=microphone.state!=='idle'||selecting||!serviceReady||!stage.loaded||socket?.readyState!==WebSocket.OPEN;});
let conversation=null,chatVersion=0,clientReady,lastActivity=Date.now(),initiativeChecking=false;
const hasContent=value=>Boolean(value?.has_content??value?.messages?.some(m=>m.role==='user'&&/[\p{L}\p{N}]/u.test(m.content)));
const touch=()=>{lastActivity=Date.now();};
for(const kind of ['keydown','pointerdown'])document.addEventListener(kind,touch);
const ensureClient=()=>clientReady??=chatRequest('/client',{method:'POST'});
const drafts=new Map();
let referenceAudio=null,serviceReady=false,mode='live',selectionVersion=0,selecting=false;
const debug=window.avatarDebug={events:[],firstAudioMs:null,startedAt:null,cancelledAt:null,playingSources:0,turn:null};

function stopAudio(label){
  currentTurn=null;debug.turn=null;
  for(const source of sources){try{source.stop();}catch{}}
  sources.clear();scheduled=[];frames=[];faces=[];nextTime=0;complete=false;playing=false;
  debug.playingSources=0;
  $('state').textContent=label;$('energy').value=0;$('motion').textContent='listen';$('cancel').disabled=true;
  stage.setMode('listening');
}
function finishIfDrained(){
  debug.playingSources=sources.size;
  if(complete&&sources.size===0){currentTurn=null;debug.turn=null;$('state').textContent=t("正在倾听");$('cancel').disabled=true;$('motion').textContent='idle';$('energy').value=0;stage.setMode('listening');playing=false;}
}
function play(event){
  if(debug.firstAudioMs===null)debug.firstAudioMs=performance.now()-debug.startedAt;
  const raw=Uint8Array.from(atob(event.data.pcm_base64),c=>c.charCodeAt(0));
  const buffer=context.createBuffer(1,event.data.sample_count,event.sample_rate);
  const view=new DataView(raw.buffer),channel=buffer.getChannelData(0);
  for(let i=0;i<channel.length;i++)channel[i]=view.getInt16(i*2,true)/32768;
  const source=context.createBufferSource(),gain=context.createGain();
  source.buffer=buffer;gain.gain.value=muted?0:1;source.connect(gain);gain.connect(context.destination);source.gainNode=gain;
  const start=Math.max(nextTime,context.currentTime+.04);nextTime=start+buffer.duration;
  scheduled.push({start,end:nextTime,offset:event.sample_offset,rate:event.sample_rate});
  sources.add(source);debug.playingSources=sources.size;
  source.onended=()=>{sources.delete(source);source.disconnect();gain.disconnect();finishIfDrained();};
  source.start(start);$('state').textContent=mode==='live'?t("正在说话"):t("接口回放");stage.setMode('speaking');playing=true;
}
function animate(){
  if(context&&currentTurn){
    const now=context.currentTime;
    while(scheduled.length>1&&scheduled[0].end<now)scheduled.shift();
    const block=scheduled.find(b=>b.start<=now&&now<=b.end);
    if(block){
      const sample=block.offset+(now-block.start)*block.rate;$('clock').textContent=`${(sample/block.rate).toFixed(3)} s`;
      while(frames.length>1&&frames[1].sample_offset<=sample)frames.shift();
      while(faces.length>1&&faces[1].sample_offset<=sample)faces.shift();
      const frame=frames.length&&frames[0].sample_offset<=sample?frames[0].data:null;
      const face=faces.length&&faces[0].sample_offset<=sample?faces[0].data:null;
      if(frame){$('energy').value=frame.dry_rms;$('motion').textContent=frame.motion_state;}
      stage.setPerformance(frame?{...frame,action_time_s:(frame.segment_time_s??0)+(sample-frames[0].sample_offset)/block.rate}:null,face);
    }else{stage.setPerformance(null,null);$('energy').value=0;}
  }
  requestAnimationFrame(animate);
}
function addMessage(role,text){
  const welcome=$('messages').querySelector('.welcome');if(welcome)welcome.remove();
  const message=document.createElement('div');message.className=`message ${role}`;
  if(role==='assistant'){const speaker=document.createElement('span');speaker.className='speaker';speaker.textContent=selected.profile.display_name;message.append(speaker);}
  const content=document.createElement('span');content.className='content';content.textContent=text;message.append(content);
  if(role==='assistant'&&!text)message.classList.add('waiting');
  $('messages').append(message);$('messages').scrollTop=$('messages').scrollHeight;return content;
}
function addPerformance(content, data){
  content.parentElement.classList.remove('waiting');
  const sentence=document.createElement('span');sentence.className='performance-sentence';
  const direction=document.createElement('span');direction.className='performance-direction';
  direction.textContent=`〔${emotionLabels[data.emotion]??t("自然")}${(data.actions??[]).map(c=>' · '+(actionLabels[c.name]??c.name)).join('')}〕`;
  sentence.append(direction,document.createTextNode(data.text));content.append(sentence);
}
async function chatRequest(path, options={}){
  const response=await fetch('/api/conversations'+path,options);
  if(!response.ok)throw Error(t("会话读取失败，请重试"));return response.json();
}
function interruptCurrent(){
  if(microphone.state!=='idle')microphone.cancel();
  if(conversation)drafts.set(conversation.id,$('prompt').value);
  const turn=currentTurn;stopAudio(t("正在倾听"));
  if(turn&&socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'cancel',turn_id:turn}));
}
function showConversation(value){
  conversation=value;$('suggestions').hidden=value.messages.length>0;touch();$('initiative-enabled').checked=Boolean(value.initiative?.enabled);$('export-conversation').href='/api/conversations/'+value.id+'/export';$('new-conversation').disabled=!hasContent(value);assistantContent=null;$('messages').replaceChildren();
  $('conversation-select').value=value.id;
  localStorage.setItem('avatar-conversation:'+value.character_id,value.id);
  $('prompt').value=drafts.get(value.id)??sessionStorage.getItem('avatar-language-draft')??'';sessionStorage.removeItem('avatar-language-draft');
  if(!value.messages.length){const welcome=document.createElement('div');welcome.className='welcome';welcome.textContent=t("新的对话，从这里开始。这个会话拥有独立的上下文。");$('messages').append(welcome);}
  for(const message of value.messages){
    if(message.role==='user'){addMessage('user',message.content);continue;}
    let content;
    for(const segment of message.segments??[]){content=addMessage('assistant','');addPerformance(content,segment);}
    if(!content)content=addMessage('assistant',message.content||t("回复未完成"));
    content.parentElement.classList.remove('waiting');
    if(message.status!=='complete'){const note=document.createElement('small');note.className='conversation-note';note.textContent=message.status==='failed'?t("回复未完成"):t("已打断");content.append(note);}
  }
  $('messages').scrollTop=$('messages').scrollHeight;
}
async function loadConversations(characterId, preferred){
  await ensureClient();
  const token=++chatVersion;
  let rows=await chatRequest('?character_id='+encodeURIComponent(characterId));
  if(!rows.length){const item=await chatRequest('',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({character_id:characterId})});rows=[item];}
  const id=rows.find(r=>r.id===(preferred??localStorage.getItem('avatar-conversation:'+characterId)))?.id??rows[0].id;
  const value=await chatRequest('/'+id);
  if(token!==chatVersion||selected?.profile.character_id!==characterId)return;
  $('conversation-select').replaceChildren(...rows.map(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=t(row.title);return option;}));
  showConversation(value);
}
async function switchConversation(id, fresh=false){
  if(!selected||selecting||(fresh&&!hasContent(conversation)))return;
  selecting=true;$('start').disabled=true;interruptCurrent();
  try{
    if(fresh){const row=await chatRequest('',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({character_id:selected.profile.character_id})});id=row.id;}
    await loadConversations(selected.profile.character_id,id);
  }catch(error){$('state').textContent=error.message;}
  finally{selecting=false;refreshServices();}
}
$('conversation-select').onchange=event=>switchConversation(event.target.value);
$('new-conversation').onclick=()=>switchConversation(null,true);
window.avatarConversations={current:()=>conversation,switch:switchConversation};

async function choose(id){
  interruptCurrent();chatVersion++;
  const selection=++selectionVersion;
  selecting=true;$('start').disabled=true;
  if(currentTurn&&socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'cancel',turn_id:currentTurn}));
  stopAudio(t("正在准备角色"));if(referenceAudio)referenceAudio.pause();
  try{
    const response=await fetch(`/api/characters/${id}`);
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const details=await response.json();
    if(selection!==selectionVersion)return;selected=details;
    localStorage.setItem('avatar-character',id);
    $('asset-credit').textContent=selected.provenance.kind==='external_asset'?(officialLive2D(selected)?t("© Live2D Inc. · 官方示例，使用条款见角色设定"):selected.profile.character_id==='sample_robot'?'RobotExpressive · Quaternius / Don McCurdy · CC0':t("导入资源 · 来源和使用条款见角色设定")):'';
    $('character-name').textContent=selected.profile.display_name;$('persona').textContent=selected.profile.persona;
    document.querySelectorAll('.character-card').forEach(c=>c.classList.toggle('active',c.dataset.id===id));
    await loadConversations(id);if(selection!==selectionVersion)return;
    await stage.load(selected);if(selection!==selectionVersion)return;$('state').textContent=t("正在倾听");
  }catch(error){
    if(selection===selectionVersion){stage.loaded=false;$('stage-status').textContent=t("角色加载失败");$('state').textContent=error.message;}
    throw error;
  }finally{
    if(selection===selectionVersion){selecting=false;$('start').disabled=!serviceReady||!stage.loaded||socket?.readyState!==WebSocket.OPEN;}
  }
}
async function send(initiative=null){
  if(initiative?.type)initiative=null;
  const text=initiative?.topic??$('prompt').value.trim();if(!/[\p{L}\p{N}]/u.test(text)||!selected||!conversation||selecting||microphone.state!=='idle'||!stage.loaded||socket?.readyState!==WebSocket.OPEN)return;
  $('start').disabled=true;
  try{
    context??=new AudioContext();await context.resume();if(referenceAudio)referenceAudio.pause();
    stopAudio(t("正在思考"));stage.setMode('thinking');
    currentTurn=crypto.randomUUID();debug.turn=currentTurn;debug.startedAt=performance.now();debug.firstAudioMs=null;
    $('cancel').disabled=false;
    if(!initiative){$('suggestions').hidden=true;addMessage('user',text);conversation.has_content=true;$('prompt').value='';touch();}
    assistantContent=addMessage('assistant','');
    socket.send(JSON.stringify({type:'speak',turn_id:currentTurn,character_id:selected.profile.character_id,conversation_id:conversation.id,text,emotion:$('emotion').value,source:initiative?'initiative':'user',initiative_ticket:initiative?.ticket??null}));
  }catch(error){stopAudio(t("无法启动声音：{0}",error.message));}
  finally{$('start').disabled=!serviceReady;}
}
$('start').onclick=send;
$('prompt').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send();}};
$('cancel').onclick=()=>{const turn=currentTurn;debug.cancelledAt=performance.now();stopAudio(t("已打断 · 正在倾听"));assistantContent?.parentElement.classList.remove('waiting');if(turn&&socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'cancel',turn_id:turn}));};
$('mute').onclick=()=>{muted=!muted;$('mute').title=muted?t('打开声音'):t('关闭声音');$('mute').textContent=muted?t("声音关"):t("声音开");for(const source of sources)source.gainNode.gain.value=muted?0:1;if(referenceAudio)referenceAudio.muted=muted;};
$('reference').onclick=()=>{if(!selected)return;if(referenceAudio)referenceAudio.pause();referenceAudio=new Audio(`/assets/${selected.profile.character_id}/reference.wav`);referenceAudio.muted=muted;referenceAudio.play().catch(()=>$('state').textContent=t("声线样音尚未就绪"));};
for(const button of $('suggestions').querySelectorAll('button'))button.onclick=()=>{$('prompt').value=button.textContent;send();};

async function refreshServices(){
  const services=await (await fetch('/api/services')).json();mode=services.mode;
  microphone.setAvailable(services.asr?.status==='ready');
  serviceReady=mode!=='live'||(services.llm.status==='ready'&&services.tts.status==='ready'&&['ready','disabled'].includes(services.audio_face?.status??'disabled'));
  $('runtime-info').textContent=mode==='live'?t("对话：{0} · 语音：{1} · 语音表情：{2}",services.llm.status,services.tts.status,services.audio_face?.status??"disabled"):t("CPU 接口回放模式（合成测试音）");
  if(socket?.readyState===WebSocket.OPEN)$('connection').textContent=serviceReady?t("已连接"):t("模型服务准备中");
  $('start').disabled=microphone.state!=='idle'||selecting||!serviceReady||!stage.loaded||socket?.readyState!==WebSocket.OPEN;
  $('conversation-select').disabled=selecting; $('new-conversation').disabled=selecting||!selected||!hasContent(conversation)||Boolean(currentTurn);
}

function officialLive2D(character){return character.provenance?.sources.some(s=>s.source==='https://github.com/Live2D/CubismWebSamples');}
function renderCards(){
  $('character-cards').replaceChildren();
  for(const c of [...characters].sort((a,b)=>Number(b.provenance?.kind==='external_asset')-Number(a.provenance?.kind==='external_asset'))){
    const button=document.createElement('button');button.className='character-card';button.dataset.id=c.profile.character_id;
    if(c.preview_url){const image=document.createElement('img');image.className='card-portrait';image.src=c.preview_url;image.alt='';image.onerror=()=>image.hidden=true;button.append(image);}
    const content=document.createElement('span'),title=document.createElement('span'),subtitle=document.createElement('span');
    title.className='card-title';title.textContent=c.profile.display_name;subtitle.className='card-subtitle';subtitle.textContent=c.provenance?.kind==='external_asset'?(officialLive2D(c)?t("官方 Live2D · 导入"):c.provenance.sources.some(s=>s.license==='CC0-1.0')?t("CC0 · 原生 3D"):t("资源导入")):c.provenance?.kind==='generated_asset'?t("图片生成 · 自动绑定"):t("协议示例 · 测试资源");
    content.append(title,subtitle);button.append(content);button.onclick=()=>choose(c.profile.character_id).catch(console.error);$('character-cards').append(button);
  }
}
async function refreshLibrary(id){
  characters=await (await fetch('/api/characters')).json();renderCards();
  if(id)await choose(id);else if(!selected&&selectionVersion===0&&characters.length)await choose(characters.find(c=>c.profile.character_id===localStorage.getItem('avatar-character'))?.profile.character_id??characters.find(c=>c.profile.character_id==='sample_haru')?.profile.character_id??characters[0].profile.character_id);
}
window.avatarStudio={refresh:refreshLibrary,selected:()=>selected};
window.addEventListener('avatar:librarychange',()=>refreshLibrary().catch(console.error));

const microphone = new MicrophoneInput({
  onStart: () => {
    if(currentTurn) $('cancel').click();
    if(referenceAudio) referenceAudio.pause();
    // Unlock reply playback in the microphone click gesture, before ASR awaits.
    context??=new AudioContext();context.resume().catch(()=>{});
  },
  onBusy: busy => { $('prompt').readOnly=busy; $('start').disabled=busy||!serviceReady||!stage.loaded; },
  onTranscript: text => {
    $('prompt').value=[$('prompt').value.trim(),text].filter(Boolean).join(' ');
    if($('voice-auto-send').checked)send();else $('prompt').focus();
  },
});

$('initiative-enabled').onchange=async()=>{
  if(!conversation)return;
  const value=$('initiative-enabled').checked,cid=conversation.id;
  try{
    context??=new AudioContext();await context.resume();
    const settings=await chatRequest('/'+cid+'/initiative',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({...conversation.initiative,enabled:value})});
    if(conversation?.id===cid){conversation.initiative=settings;touch();$('initiative-status').textContent=value?t("已开启 · 空闲时由角色判断是否开口"):t("主动聊天已关闭");}
  }catch(error){$('initiative-enabled').checked=!value;$('initiative-status').textContent=error.message;}
};
async function checkInitiative(){
  if(initiativeChecking||!conversation?.initiative?.enabled||!serviceReady||selecting||currentTurn||!stage.loaded||socket?.readyState!==WebSocket.OPEN)return;
  if(document.hidden||$('prompt').value.trim()||microphone.state!=='idle'||document.querySelector('dialog[open]'))return;
  const idle=(Date.now()-lastActivity)/1000;if(idle<(conversation.initiative.idle_seconds??35))return;
  const cid=conversation.id,version=lastActivity;initiativeChecking=true;
  try{
    $('initiative-status').textContent=t("角色正在想要不要开口…");
    const decision=await chatRequest('/'+cid+'/initiative/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idle_seconds:idle,visible:!document.hidden,typing:!!$('prompt').value.trim(),recording:microphone.state!=='idle',playing})});
    if(conversation?.id!==cid||lastActivity!==version||!conversation.initiative?.enabled||currentTurn||document.hidden||$('prompt').value.trim()||microphone.state!=='idle'||document.querySelector('dialog[open]'))return;
    $('initiative-status').textContent=decision.speak?t("角色想和你聊聊"):t("已开启 · 正在安静陪伴");
    if(decision.speak)await send(decision);
  }finally{initiativeChecking=false;}
}

async function initialize(){
  await ensureClient();
  const response=await fetch('/api/characters');if(!response.ok)throw new Error(`HTTP ${response.status}`);characters=await response.json();
  renderCards();
  await refreshServices();
  setInterval(()=>refreshServices().catch(()=>{serviceReady=false;$('start').disabled=true;}),5000);
  socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);
  socket.onopen=()=>{$('connection').textContent=serviceReady?t("已连接"):t("模型服务准备中");$('start').disabled=microphone.state!=='idle'||selecting||!serviceReady||!stage.loaded;};
  socket.onclose=()=>{stopAudio(t("连接已关闭，请刷新页面"));$('connection').textContent=t("已断开");$('start').disabled=true;};
  socket.onmessage=({data})=>{
    const event=JSON.parse(data);count++;logs.push(`${event.turn_id??'request'} #${event.sequence??'-'} ${event.type} @${event.sample_offset??0}`);if(logs.length>80)logs.shift();
    debug.events.push({type:event.type,turn:event.turn_id,offset:event.sample_offset,received:performance.now()});if(debug.events.length>5000)debug.events.splice(0,1000);
    $('events').textContent=logs.join('\n');$('counter').textContent=count;
    if(event.type==='request_error'){stopAudio(t("消息发送失败，请重试"));return;}if(event.turn_id!==currentTurn)return;
    if(event.type==='text'){if(assistantContent?.childNodes.length)assistantContent=addMessage('assistant','');addPerformance(assistantContent,event.data);$('messages').scrollTop=$('messages').scrollHeight;}
    if(event.type==='audio')play(event);if(event.type==='motion')frames.push(event);if(event.type==='face')faces.push(event);
    if(event.type==='turn_end'){touch();complete=true;finishIfDrained();if(conversation)chatRequest('?character_id='+selected.profile.character_id).then(rows=>{for(const row of rows){const option=[...$('conversation-select').options].find(o=>o.value===row.id);if(option)option.textContent=t(row.title);}}).catch(()=>{});}
    if(event.type==='cancelled')stopAudio(t("已打断 · 正在倾听"));
    if(event.type==='error'){stopAudio(t("回复暂时失败，请重试"));assistantContent.parentElement.classList.remove('waiting');assistantContent.classList.add('error-text');assistantContent.textContent+=t("（本轮生成失败）");}
  };
  setInterval(()=>checkInitiative().catch(()=>{$('initiative-status').textContent=t("主动判断暂时不可用，稍后重试");}),5000);
  if(characters.length){if(selectionVersion===0)await choose(characters.find(c=>c.profile.character_id===localStorage.getItem('avatar-character'))?.profile.character_id??characters.find(c=>c.profile.character_id==='sample_haru')?.profile.character_id??characters[0].profile.character_id);}else{$('stage-status').textContent=t("等待你的第一个角色");$('state').textContent=t("点击右上角「创建角色」");}requestAnimationFrame(animate);
}
initialize().catch(error=>{$('connection').textContent=t("初始化失败");$('state').textContent=error.message;console.error(error);});
