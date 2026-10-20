/* Exercise the actual built bundle, with a temporary localhost preview process. */
const { spawn } = require('node:child_process');
const path = require('node:path');
const root = path.join(__dirname,'..');
const base = 'http://127.0.0.1:3010';
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
  // Never reuse an unknown process on the test port.
  if (await fetch(base,{signal:AbortSignal.timeout(1000)}).then(()=>true,()=>false)) throw new Error('Production test port 3010 is already in use');
  const server = spawn(process.execPath,[path.join(root,'ui/node_modules/vite/bin/vite.js'),'preview','--host','127.0.0.1','--port','3010','--strictPort'],{cwd:path.join(root,'ui'),windowsHide:true,stdio:['ignore','pipe','pipe']});
  let logs=''; server.stdout.on('data',chunk=>{logs+=chunk});server.stderr.on('data',chunk=>{logs+=chunk});
  try {
    let ready=false;
    for (let i=0;i<40;i++) {
      if (server.exitCode !== null) throw new Error('Preview exited: '+logs);
      ready=await fetch(base+'/api/health',{signal:AbortSignal.timeout(2000)}).then(r=>r.json()).then(body=>body.status==='ok',()=>false);
      if (ready) break;
      await sleep(250);
    }
    if (!ready) throw new Error('Production preview API was not ready: '+logs);
    const test=spawn(process.execPath,[path.join(__dirname,'test_ui.cjs')],{cwd:root,windowsHide:true,env:{...process.env,DIANCAN_UI_URL:base},stdio:'inherit'});
    const code=await new Promise((resolve,reject)=>{test.on('error',reject);test.on('exit',resolve)});
    if (code!==0) throw new Error('Production browser regression failed with exit code '+code);
    console.log('Built-bundle regression passed; temporary preview stopped.');
  } finally {
    server.kill();
    if (server.exitCode===null) await new Promise(resolve=>server.once('exit',resolve));
  }
})().catch(error=>{console.error(error.message);process.exitCode=1});
