
'use strict';

const $ = (id) => document.getElementById(id);
const WIDTH = 32;
const HEIGHT = 24;
const STALE_MS = 4500;
const MAX_TREND = 100;

const PALETTES = {
  ironbow: [[0,[11,12,32]],[0.18,[59,36,114]],[0.42,[163,30,85]],[0.64,[232,83,45]],[0.84,[255,183,72]],[1,[255,249,212]]],
  inferno: [[0,[0,0,5]],[0.2,[55,10,89]],[0.4,[137,29,86]],[0.6,[210,70,49]],[0.8,[250,143,28]],[1,[252,255,164]]],
  grayscale: [[0,[9,11,19]],[1,[252,253,255]]]
};

const thermalCanvas = $('thermalCanvas');
const thermalContext = thermalCanvas.getContext('2d', {alpha:false});
const miniature = document.createElement('canvas');
miniature.width = WIDTH;
miniature.height = HEIGHT;
const miniatureContext = miniature.getContext('2d');
const trendCanvas = $('trendCanvas');
const trendContext = trendCanvas.getContext('2d');

const state = {
  socket: null,
  frame: null,
  lastFrameReceivedAt: 0,
  times: [],
  trend: [],
  palette: 'ironbow',
  rangeLow: 20,
  rangeHigh: 100,
  paused: false,
  connected: false,
  reconnectMs: 800
};

function validThermal(value) {
  // The supplied MLX90640 driver marks broken/outlier pixels as -273.15°C.
  return typeof value==='number' && Number.isFinite(value) && value > -200;
}

function tempText(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '--.-';
}

function paletteColor(t) {
  const stops = PALETTES[state.palette];
  t = Math.max(0, Math.min(1, t));
  let i = 0;
  while (i + 1 < stops.length && t > stops[i+1][0]) i++;
  if (i === stops.length - 1) return stops[i][1];
  const [t0,c0] = stops[i];
  const [t1,c1] = stops[i+1];
  const k = (t-t0)/(t1-t0);
  return [0,1,2].map(j => Math.round(c0[j]+k*(c1[j]-c0[j])));
}

function updateColorbar() {
  const gradient = PALETTES[state.palette].map(([p,rgb])=>`rgb(${rgb.join(',')}) ${Math.round(p*100)}%`).join(',');
  $('colorbar').style.background = `linear-gradient(to right, ${gradient})`;
  $('legendLow').textContent = `${state.rangeLow} °C`;
  $('legendHigh').textContent = `${state.rangeHigh} °C`;
}

function paintFrame(frame) {
  if (!frame || !Array.isArray(frame.pixels) || frame.pixels.length !== WIDTH*HEIGHT) return;
  const data = miniatureContext.createImageData(WIDTH,HEIGHT);
  const delta = state.rangeHigh - state.rangeLow;
  for (let i=0; i<frame.pixels.length; i++) {
    const [r,g,b] = validThermal(frame.pixels[i])
      ? paletteColor((frame.pixels[i]-state.rangeLow)/delta)
      : [36, 45, 58]; // neutral missing/invalid sensor pixel
    const k = i*4;
    data.data[k]=r; data.data[k+1]=g; data.data[k+2]=b; data.data[k+3]=255;
  }
  miniatureContext.putImageData(data,0,0);
  thermalContext.imageSmoothingEnabled = true;
  thermalContext.imageSmoothingQuality = 'high';
  thermalContext.drawImage(miniature,0,0,thermalCanvas.width,thermalCanvas.height);
}

function resizeTrend() {
  const rect = trendCanvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const pixelRatio = Math.min(window.devicePixelRatio || 1,2);
  trendCanvas.width = Math.round(rect.width*pixelRatio);
  trendCanvas.height = Math.round(rect.height*pixelRatio);
  trendContext.setTransform(pixelRatio,0,0,pixelRatio,0,0);
  paintTrend();
}

function paintTrend() {
  const rect = trendCanvas.getBoundingClientRect();
  const w=rect.width, h=rect.height;
  if (!w || !h) return;
  trendContext.clearRect(0,0,w,h);
  const left=40, right=w-13, top=10, bottom=h-23;
  const vals=state.trend.map(p=>p.value);
  const baselineMin = state.rangeLow;
  const baselineMax = state.rangeHigh;
  let minimum = vals.length ? Math.min(baselineMin,...vals) : baselineMin;
  let maximum = vals.length ? Math.max(baselineMax,...vals) : baselineMax;
  const pad = Math.max(5,(maximum-minimum)*0.08);
  minimum -= pad; maximum += pad;
  const yPos = value => bottom-((value-minimum)/(maximum-minimum))*(bottom-top);
  trendContext.lineWidth=1;
  trendContext.font='10px ui-monospace, Consolas, monospace';
  trendContext.textAlign='right';
  for(let i=0;i<=4;i++){
    const y=top+(bottom-top)*i/4;
    const tick=maximum-i*(maximum-minimum)/4;
    trendContext.strokeStyle='#293649';
    trendContext.beginPath();trendContext.moveTo(left,y);trendContext.lineTo(right,y);trendContext.stroke();
    trendContext.fillStyle='#7487a1';
    trendContext.fillText(`${tick.toFixed(0)}°`,left-8,y+3);
  }
  trendContext.fillStyle='#71839d';
  trendContext.textAlign='left';trendContext.fillText('EARLIER',left,bottom+17);
  trendContext.textAlign='right';trendContext.fillText('NOW',right,bottom+17);
  if (vals.length===0){
    trendContext.textAlign='center';trendContext.fillStyle='#7f90a8';
    trendContext.font='12px ui-sans-serif, system-ui';
    trendContext.fillText('Live trend begins when thermal frames arrive',(left+right)/2,(top+bottom)/2);
    return;
  }
  const xPos = idx=> left+idx/(MAX_TREND-1)*(right-left);
  const startIdx = MAX_TREND-vals.length;
  const coords = vals.map((value,i)=>[xPos(startIdx+i),yPos(value)]);
  trendContext.beginPath();trendContext.moveTo(coords[0][0],bottom);
  coords.forEach(([x,y])=>trendContext.lineTo(x,y));
  trendContext.lineTo(coords[coords.length-1][0],bottom);trendContext.closePath();
  const fill=trendContext.createLinearGradient(0,top,0,bottom);
  fill.addColorStop(0,'rgba(244,151,87,.20)');fill.addColorStop(1,'rgba(244,151,87,0)');
  trendContext.fillStyle=fill;trendContext.fill();
  trendContext.beginPath();
  coords.forEach(([x,y],i)=>i?trendContext.lineTo(x,y):trendContext.moveTo(x,y));
  trendContext.strokeStyle='#ffb175';trendContext.lineWidth=2.1;
  trendContext.lineJoin='round';trendContext.stroke();
  const [x,y]=coords[coords.length-1];
  trendContext.beginPath();trendContext.arc(x,y,3.5,0,2*Math.PI);trendContext.fillStyle='#ffc48f';trendContext.fill();
}

function formatTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.valueOf()) ? '—' : date.toLocaleTimeString([], {hour12:false});
}

function ingestFrame(msg) {
  if (!Array.isArray(msg.pixels) || msg.pixels.length !== WIDTH*HEIGHT) return;
  if (!msg.pixels.every(v => typeof v==='number' && Number.isFinite(v))) return;
  const now=Date.now();
  state.frame=msg;
  state.lastFrameReceivedAt=now;
  state.times.push(now);
  state.times=state.times.filter(t=>now-t<=4000).slice(-50);
  const valid = msg.pixels.filter(validThermal);
  if (valid.length === 0) return;
  state.trend.push({time:now, value:msg.max_c ?? Math.max(...valid)});
  if(state.trend.length>MAX_TREND)state.trend.shift();
  $('maxTemp').textContent=tempText(msg.max_c??Math.max(...valid));
  $('minTemp').textContent=tempText(msg.min_c??Math.min(...valid));
  $('meanTemp').textContent=tempText(msg.mean_c??valid.reduce((a,b)=>a+b,0)/valid.length);
  $('sequenceText').textContent=`FRAME #${String(msg.sequence||0).padStart(6,'0')}`;
  $('totalFrames').textContent=String(msg.sequence||0).padStart(6,'0');
  $('validPixels').textContent=`${valid.length} / 768 valid pixels`;
  $('sensorTemp').textContent=msg.sensor_temperature_c==null?'—':`${tempText(msg.sensor_temperature_c)} °C`;
  $('frameTimestamp').textContent=formatTime(msg.received_at);
  const simulated = msg.source==='simulator';
  $('sourceBadge').textContent=simulated?'SIMULATED DATA':'HARDWARE FEED';
  $('sourceBadge').className=`source-badge ${simulated?'demo':'hardware'}`;
  $('demoWatermark').hidden=!simulated;
  $('emptyState').hidden=true;
  $('cameraFoot').textContent=`MLX90640 · ${WIDTH} × ${HEIGHT} · ${simulated?'synthetic demonstration':'incoming thermal readings'}`;
  if (!state.paused)paintFrame(msg);
  paintTrend();
  updateHealth();
}

function ingestTelemetry(msg) {
  $('reportedState').textContent=msg.state || '—';
  $('reportedState').className=`reported-state ${String(msg.state || '').toLowerCase()}`;
  $('ambientReading').textContent=msg.ambient_c==null?'—':`${tempText(msg.ambient_c)} °C`;
  $('reportedSuppression').textContent=msg.suppression_active?'ACTIVE (reported)':'Inactive (reported)';
  $('telemetryTimestamp').textContent=formatTime(msg.received_at);
}

function updateHealth(){
  const now=Date.now();
  const active=state.lastFrameReceivedAt>0 && now-state.lastFrameReceivedAt<STALE_MS;
  $('cameraStatus').className=`mini-status ${active?'live':'waiting'}`;
  $('cameraDot').className=`diag-status ${active?'green':'amber'}`;
  $('feedStatus').className=`feed-badge ${active?'live':''}`;
  $('feedStatus').innerHTML=`<span class="badge-dot"></span> ${active?(state.paused?'VIEW PAUSED':'STREAMING'):'STANDBY'}`;
  if(state.lastFrameReceivedAt){
    const seconds=((now-state.lastFrameReceivedAt)/1000).toFixed(1);
    $('lastFrame').textContent=active?`${seconds}s ago`:`No recent frames · ${seconds}s ago`;
  }
  state.times=state.times.filter(t=>now-t<=4000);
  const fps = active && state.times.length>1
    ? (state.times.length-1)/((state.times[state.times.length-1]-state.times[0])/1000)
    : 0;
  $('frameRate').textContent=Number.isFinite(fps)?fps.toFixed(1):'0.0';
  $('frameStatus').textContent=active?'Receiving frames':'Waiting for frames';
}

function setConnection(connected){
  state.connected=connected;
  $('serverPill').className=`server-pill ${connected?'connected':'disconnected'}`;
  $('serverStatus').textContent=connected?'Server connected':'Server disconnected';
  $('socketLabel').textContent=connected?'Connected · receiving enabled':'Disconnected · retrying';
  $('socketDot').className=`diag-status ${connected?'green':'amber'}`;
}

function connect(){
  const protocol=window.location.protocol==='https:'?'wss:':'ws:';
  const socket=new WebSocket(`${protocol}//${window.location.host}/ws/thermal`);
  state.socket=socket;
  socket.addEventListener('open',()=>{setConnection(true);state.reconnectMs=800;});
  socket.addEventListener('message',event=>{
    try {const data=JSON.parse(event.data);if(data.type==='frame')ingestFrame(data);
      else if(data.type==='telemetry')ingestTelemetry(data);}catch(err){console.warn('Bad frame payload',err);}
  });
  socket.addEventListener('close',()=>{
    if(state.socket!==socket)return;
    setConnection(false);
    const delay=state.reconnectMs;
    state.reconnectMs=Math.min(10000,Math.round(state.reconnectMs*1.5));
    setTimeout(connect,delay);
  });
  socket.addEventListener('error',()=>socket.close());
}

function validRange(){
  const low=Number($('rangeMin').value), high=Number($('rangeMax').value);
  if(!Number.isFinite(low)||!Number.isFinite(high)||low>=high||low< -40||high>350){
    $('rangeMin').value=state.rangeLow;
    $('rangeMax').value=state.rangeHigh;
    return;
  }
  state.rangeLow=low;state.rangeHigh=high;
  updateColorbar();
  if(state.frame&&!state.paused)paintFrame(state.frame);
  paintTrend();
}

$('palette').addEventListener('change',event=>{
  state.palette=event.target.value;
  updateColorbar();
  if(state.frame&&!state.paused)paintFrame(state.frame);
});
$('rangeMin').addEventListener('change',validRange);
$('rangeMax').addEventListener('change',validRange);
$('pauseBtn').addEventListener('click',()=>{
  state.paused=!state.paused;
  $('pauseBtn').textContent=state.paused?'Resume display':'Pause display';
  $('pauseBtn').setAttribute('aria-pressed',String(state.paused));
  if(!state.paused && state.frame)paintFrame(state.frame);
  updateHealth();
});

thermalCanvas.addEventListener('mousemove',event=>{
  if(!state.frame)return;
  const rect=thermalCanvas.getBoundingClientRect();
  const x=Math.max(0,Math.min(WIDTH-1,Math.floor((event.clientX-rect.left)/rect.width*WIDTH)));
  const y=Math.max(0,Math.min(HEIGHT-1,Math.floor((event.clientY-rect.top)/rect.height*HEIGHT)));
  const value=state.frame.pixels[y*WIDTH+x];
  $('hoverValue').textContent=`X:${String(x).padStart(2,'0')}  Y:${String(y).padStart(2,'0')}  ${validThermal(value)?tempText(value)+' °C':'INVALID SENSOR PIXEL'}`;
});
thermalCanvas.addEventListener('mouseleave',()=>{$('hoverValue').textContent='MOVE CURSOR TO INSPECT PIXELS';});

function displayDate(){
  $('currentDate').textContent=new Date().toLocaleDateString(undefined,{day:'2-digit',month:'short',year:'numeric'}).toUpperCase();
}
window.addEventListener('resize',resizeTrend);
setInterval(()=>{updateHealth();displayDate();},500);
displayDate();updateColorbar();resizeTrend();connect();
