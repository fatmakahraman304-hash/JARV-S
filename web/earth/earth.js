/* Real WebGL globe, viewport-only imagery; no camera, geolocation or account. */
"use strict";
(() => {
  const readout = document.getElementById("readout");
  const state = window.earthState = {ready:false, rendered:false, tiles:0, images:0, mode:"holo", error:""};
  let viewer, mode = "holo", pending, desiredActive = !document.hidden;
  function fail(message) { state.error = message; readout.textContent = message + "\nÜstteki Normal harita düğmesini kullanabilirsiniz."; }
  window.fridayEarth = {
    goTo(point) {
      if (!point || ![point.lat,point.lon,point.height].every(Number.isFinite) || Math.abs(point.lat)>90 || Math.abs(point.lon)>180) return;
      pending = point;
      if (!viewer) return;
      viewer.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(point.lon,point.lat,Math.max(120,Math.min(24000000,point.height))),duration:1.35,orientation:{heading:0,pitch:-Math.PI/2,roll:0}});
    },
    setActive(active) {
      desiredActive = Boolean(active);
      state.active=desiredActive;
      if (viewer) { viewer.useDefaultRenderLoop = desiredActive; if (desiredActive) { viewer.resize(); viewer.scene.requestRender(); } }
    },
    capture() { if(viewer){viewer.scene.requestRender();viewer.scene.render();return viewer.canvas.toDataURL("image/png");}return null; },
    refresh() { if(viewer)viewer.scene.requestRender(); },
    centre() {
      if (!viewer) return null;
      const scene=viewer.scene, pixel=new Cesium.Cartesian2(scene.canvas.clientWidth/2,scene.canvas.clientHeight/2);
      const point=viewer.camera.pickEllipsoid(pixel,scene.globe.ellipsoid);
      if (!point) return null;
      const c=Cesium.Cartographic.fromCartesian(point);
      return {lat:Cesium.Math.toDegrees(c.latitude),lon:Cesium.Math.toDegrees(c.longitude)};
    }
  };
  try {
    if (!window.Cesium) { fail("Dünya motoru indirilemedi. İnternet bağlantısını kontrol edin."); return; }
    Cesium.Ion.defaultAccessToken = "";
    viewer = new Cesium.Viewer("globe", {baseLayer:false,baseLayerPicker:false,geocoder:false,
      terrainProvider:new Cesium.EllipsoidTerrainProvider(),animation:false,timeline:false,
      navigationHelpButton:false,homeButton:false,sceneModePicker:false,fullscreenButton:false,
      infoBox:false,selectionIndicator:false,requestRenderMode:true,maximumRenderTimeChange:Infinity,
      contextOptions:{webgl:{alpha:false,preserveDrawingBuffer:true}},skyBox:false});
    const scene=viewer.scene;
    viewer.targetFrameRate=30;
    viewer.resolutionScale=Math.min(1,1.5/(window.devicePixelRatio||1));
    scene.globe.maximumScreenSpaceError=2;
    scene.globe.tileCacheSize=100;
    scene.globe.enableLighting=false;
    scene.globe.baseColor=Cesium.Color.fromCssColorString("#063950");
    scene.backgroundColor=Cesium.Color.fromCssColorString("#030915");
    scene.screenSpaceCameraController.minimumZoomDistance=120;
    scene.screenSpaceCameraController.maximumZoomDistance=42000000;
    scene.globe.showGroundAtmosphere=true;
    // Screen-space cyan contours preserve the real projected geography.
    // This stage is disabled for natural imagery and street labels.
    const hologram=scene.postProcessStages.add(new Cesium.PostProcessStage({
      name:"friday-holographic-contours",
      fragmentShader:`uniform sampler2D colorTexture;
        in vec2 v_textureCoordinates;
        float lightAt(vec2 uv){return dot(texture(colorTexture,uv).rgb,vec3(.2126,.7152,.0722));}
        void main(){
          vec2 uv=v_textureCoordinates, px=1.0/vec2(textureSize(colorTexture,0));
          float light=lightAt(uv);
          float dx=lightAt(uv+vec2(px.x,0.))-lightAt(uv-vec2(px.x,0.));
          float dy=lightAt(uv+vec2(0.,px.y))-lightAt(uv-vec2(0.,px.y));
          float edge=clamp(length(vec2(dx,dy))*3.6,0.,1.);
          float body=smoothstep(.055,.60,light);
          vec3 color=vec3(.008,.020,.043)+body*vec3(.006,.057,.13);
          color+=edge*vec3(.025,.64,1.10);
          out_FragColor=vec4(color,1.);
        }`
    }));
    let layer;
    function setMode(next) {
      if (!["holo","natural","street"].includes(next)) return;
      mode=state.mode=next;
      hologram.enabled=next==="holo";
      state.images=0;
      if (layer) viewer.imageryLayers.remove(layer,true);
      const streets=next!=="natural";
      const service="https://services.arcgisonline.com/ArcGIS/rest/services/"+(streets?"World_Street_Map":"World_Imagery")+"/MapServer";
      // Some servers return HTTP 200 with a "Map data not yet available"
      // picture for levels without coverage. Discard it so Cesium keeps the
      // nearest valid ancestor image, rather than covering Earth in grey.
      const missing=new Cesium.DiscardMissingTileImagePolicy({
        missingImageUrl:service+"/tile/19/0/0",
        pixelsToCheck:[new Cesium.Cartesian2(0,0),new Cesium.Cartesian2(200,20),
          new Cesium.Cartesian2(20,200),new Cesium.Cartesian2(80,110),new Cesium.Cartesian2(160,130)]
      });
      const provider=new Cesium.UrlTemplateImageryProvider({
        url:streets?"https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}":"https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        maximumLevel:19,tileDiscardPolicy:missing,tilingScheme:new Cesium.WebMercatorTilingScheme(),
        credit:new Cesium.Credit(streets?'Tiles © Esri, HERE, Garmin, Intermap, increment P, GEBCO, USGS, FAO, NPS, NRCAN, and the GIS User Community':'Tiles © Esri — Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community',true)
      });
      const requestImage=provider.requestImage.bind(provider);
      provider.requestImage=(...args)=>{
        const request=requestImage(...args);
        return request && request.then(image=>{if(mode===next)state.images++;return image;});
      };
      provider.errorEvent.addEventListener(()=>mode===next&&fail("Harita görüntüleri alınamadı. Bağlantıyı veya başka bir görünümü deneyin."));
      layer=viewer.imageryLayers.addImageryProvider(provider);
      if(next==="holo") {layer.brightness=.78;layer.contrast=1.65;layer.saturation=0;layer.colorToAlpha=Cesium.Color.WHITE;layer.colorToAlphaThreshold=.16;}
      document.querySelectorAll("[data-mode]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.mode===next)));
      state.error="";
      scene.requestRender();
    }
    document.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>setMode(b.dataset.mode));
    document.getElementById("home").onclick=()=>viewer.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(28,22,21000000),duration:1.2});
    document.getElementById("in").onclick=()=>{viewer.camera.zoomIn(viewer.camera.positionCartographic.height*.48);scene.requestRender();};
    document.getElementById("out").onclick=()=>{viewer.camera.zoomOut(viewer.camera.positionCartographic.height*.70);scene.requestRender();};
    document.getElementById("dimension").onclick=()=>{if(scene.mode===Cesium.SceneMode.SCENE3D) scene.morphTo2D(1);else scene.morphTo3D(1);};
    scene.globe.tileLoadProgressEvent.addEventListener(count=>{state.tiles=count;if(!count)scene.requestRender();});
    scene.postRender.addEventListener(()=>{state.rendered=true;state.frame=(state.frame||0)+1;state.sceneMode=scene.mode;state.height=viewer.camera.positionCartographic.height;
      if(!state.error)readout.textContent=(mode==="natural"?"DOĞAL / UYDU":mode==="street"?"SOKAK HARİTASI":"HOLOGRAFİK DÜNYA")+" · "+(state.height/1000).toFixed(2)+" km";});
    scene.renderError.addEventListener(()=>fail("3D çizim durdu. Ekran kartı veya WebGL desteğini kontrol edin."));
    viewer.camera.changed.addEventListener(()=>{
      const c=viewer.camera.positionCartographic;
      if(!state.error)readout.textContent=`${mode==="natural"?"DOĞAL / UYDU":mode==="street"?"SOKAK HARİTASI":"HOLOGRAFİK DÜNYA"}\n${Cesium.Math.toDegrees(c.latitude).toFixed(4)}° · ${Cesium.Math.toDegrees(c.longitude).toFixed(4)}° · ${(c.height/1000).toFixed(2)} km`;
    });
    viewer.camera.percentageChanged=.015;
    setMode("holo");
    viewer.camera.setView({destination:Cesium.Cartesian3.fromDegrees(28,22,21000000)});
    state.ready=true;
    window.fridayEarth.setActive(desiredActive);
    if(pending)window.fridayEarth.goTo(pending);
    document.addEventListener("visibilitychange",()=>window.fridayEarth.setActive(!document.hidden));
  } catch(error) { fail("3D dünya başlatılamadı: " + String(error.message||error).slice(0,160)); }
})();
