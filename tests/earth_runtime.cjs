/* Execute the shipped Earth code with controlled layer promises and visibility. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../web/earth/earth.js'), 'utf8');
function boot() {
  const callbacks = {}, providers = [], buttons = ['holo','natural','street'].map(mode => ({dataset:{mode},setAttribute(){}}));
  const nodes = {};
  const document = {hidden:false, getElementById(id){return nodes[id] ||= {};},
    querySelectorAll(){return buttons;}, addEventListener(name, fn){callbacks[name]=fn;}};
  class Event { constructor(){this.listeners=[];} addEventListener(fn){this.listeners.push(fn);} emit(...args){this.listeners.forEach(fn=>fn(...args));} }
  let viewer;
  class Viewer { constructor(){viewer=this; this.scene={globe:{tileLoadProgressEvent:new Event()},
    screenSpaceCameraController:{},postProcessStages:{add(value){return value;}}, requestRender(){},
    postRender:new Event(),renderError:new Event(),mode:3};
    this.imageryLayers={remove(){},addImageryProvider(provider){return {provider};}};
    this.camera={flyTo(){},setView(){},changed:new Event()};this.resize=()=>{}; } }
  class Provider {constructor(){providers.push(this);this.errorEvent=new Event();this.resolve=null;}
    requestImage(){return new Promise(resolve=>this.resolve=resolve);} }
  const Cesium={Ion:{},Viewer,EllipsoidTerrainProvider:class{},Cartesian2:class{},
    Cartesian3:{fromDegrees(...args){return args;}},Color:{fromCssColorString(){return {};},WHITE:{}},
    PostProcessStage:class {constructor(options){Object.assign(this,options);}},
    DiscardMissingTileImagePolicy:class{},UrlTemplateImageryProvider:Provider,WebMercatorTilingScheme:class{},Credit:class{}};
  const window = {Cesium};
  vm.runInNewContext(source,{window,document,Cesium,Number,Math,Boolean,String});
  assert.equal(window.earthState.error,'');
  return {window,document,callbacks,providers,buttons,viewer};
}
test('Qt hidden state survives a document visibility event',()=>{
  const env=boot();env.window.fridayEarth.setActive(false);
  env.callbacks.visibilitychange();
  assert.equal(env.window.earthState.active,false);
  assert.equal(env.viewer.useDefaultRenderLoop,false);
});
test('document-hidden state bounds an explicit Qt show request',()=>{
  const env=boot();env.document.hidden=true;
  env.window.fridayEarth.setActive(true);
  assert.equal(env.window.earthState.active,false);
  env.document.hidden=false;env.callbacks.visibilitychange();
  assert.equal(env.window.earthState.active,true);
});
test('old same-mode layer replies and errors cannot alter the current layer',async()=>{
  const env=boot(), old=env.providers[0];
  env.buttons[1].onclick();env.buttons[0].onclick();
  const current=env.providers.at(-1);
  const reply=old.requestImage();old.resolve({});await reply;
  assert.equal(env.window.earthState.images,0);
  old.errorEvent.emit();assert.equal(env.window.earthState.error,'');
  const fresh=current.requestImage();current.resolve({});await fresh;
  assert.equal(env.window.earthState.images,1);
  current.errorEvent.emit();assert.notEqual(env.window.earthState.error,'');
});
