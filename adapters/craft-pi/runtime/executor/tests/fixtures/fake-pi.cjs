// OFFLINE TEST PEER ONLY. Exercises the actual bounded executor MCP subprocess.
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const flag = n => process.argv[process.argv.indexOf(n)+1];
const cwd = process.cwd();
const agent = process.env.PI_CODING_AGENT_DIR;
const resumed = process.argv.includes('--session');
const file = resumed ? flag('--session') : path.join(flag('--session-dir'), 'exact-fixture.jsonl');
const emit = x => process.stdout.write(JSON.stringify(x)+'\n');
let selected = {}, effort, mcp;
let serial = Promise.resolve();
readline.createInterface({input:process.stdin}).on('line', line => {
  serial = serial.then(async () => {
    const v = JSON.parse(line);
    const response = data => emit({type:'response',id:v.id,command:v.type,success:true,data});
    if (v.type === 'set_model') { selected = {provider:v.provider,id:v.modelId}; response({}); }
    else if (v.type === 'set_thinking_level') { effort = v.level; response({}); }
    else if (v.type === 'get_state') response({model:selected,thinkingLevel:effort,isStreaming:false,isCompacting:false,pendingMessageCount:0,sessionId:'offline-executor-session',sessionFile:file});
    else if (v.type === 'clear_queue') response({});
    else if (v.type === 'abort') { if(mcp) mcp.stdin.end(); emit({type:'agent_settled',aborted:true}); response({}); }
    else if (v.type === 'prompt') {
      if (!resumed) fs.writeFileSync(file,JSON.stringify({type:'session',version:3,id:'offline-executor-session',timestamp:'2026-11-09T00:00:00Z',cwd})+'\n');
      response({disposition:'started'}); emit({type:'agent_start'});
      emit({type:'message_update',assistantMessageEvent:{type:'text_delta',delta:'PUBLIC-RECEIPT-CONTENT-SENTINEL'}});
      fs.writeFileSync(path.join(agent,'fake-prompt-started'),'offline fixture');
      if(v.message?.includes('OFFLINE_HANG_FOR_CANCEL')) return;
      const config = JSON.parse(fs.readFileSync(path.join(agent,'mcp.json'),'utf8'));
      if (Object.keys(config.mcpServers).join() !== 'craft' || config.mcpServers.craft.exposure !== 'direct') throw Error('incorrect isolated MCP configuration');
      const server = config.mcpServers.craft;
      mcp=spawn(server.command,server.args,{stdio:['pipe','pipe','pipe'],env:process.env});
      let seq=0, pending=new Map(), stderr='';
      mcp.stderr.on('data', b=>stderr+=b);
      const mcpLines=readline.createInterface({input:mcp.stdout});
      mcpLines.on('line',line=>{ const x=JSON.parse(line); const p=pending.get(x.id); if(p) {pending.delete(x.id);p(x);} });
      const rpc = (method,params={}) => new Promise((resolve,reject)=>{
        const id=++seq; const timer=setTimeout(()=>reject(Error('MCP timeout '+method+' '+stderr)),8000);
        pending.set(id,x=>{clearTimeout(timer);resolve(x)});mcp.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');
      });
      await rpc('initialize',{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'offline-fixture',version:'1'}});
      mcp.stdin.write(JSON.stringify({jsonrpc:'2.0',method:'notifications/initialized'})+'\n');
      const list=await rpc('tools/list');
      const names=list.result.tools.map(x=>x.name).sort();
      const allowed=['build_checklist','build_command_run','build_file_edit','build_file_read','build_file_write','build_files_list'];
      if(JSON.stringify(names)!==JSON.stringify(allowed)) throw Error('MCP exposed extra/missing tools '+names);
      const invoke=async(name,args,denied=false)=>{
        const id='call-'+seq;
        emit({type:'tool_execution_start',toolCallId:id,toolName:'mcp__craft__'+name,args});
        const r=await rpc('tools/call',{name,arguments:args});
        const error=!!r.error||r.result?.isError===true;
        emit({type:'tool_execution_end',toolCallId:id,toolName:'mcp__craft__'+name,result:r.result??r.error,isError:error});
        if(error!==denied) throw Error('unexpected tool disposition '+name+JSON.stringify(r));
        return r;
      };
      // Exercise real call-time denials without emitting a forbidden Pi tool event.
      const denials=[];
      for(const [name,arguments_] of [['core_target_open',{}],['enable_toolset',{toolset:'all'}],['build_file_write',{path:'../escape.txt',content:'escape'}],['build_file_write',{path:'app/tasks.md',content:'authority'}],['build_command_run',{command:'unplanned-command',timeout_secs:5}]]) {
        const r=await rpc('tools/call',{name,arguments:arguments_});
        if(!r.error&&!r.result?.isError) throw Error('gate bypass '+name); denials.push({name,denied:true});
      }
      await invoke('build_files_list',{path:'app'});
      const source = resumed
        ? 'use std::io::{self,Read}; fn main(){let mut s=String::new();io::stdin().read_to_string(&mut s).unwrap();let name=s.trim();std::fs::write("state.txt",name).unwrap();let saved=std::fs::read_to_string("state.txt").unwrap();println!("saved: {}",saved);}'
        : 'fn main(){println!("saved: Ada");}';
      if(resumed) await invoke('build_file_edit',{path:'app/src/main.rs',old_text:'fn main(){println!("saved: Ada");}',new_text:source});
      else await invoke('build_file_write',{path:'app/src/main.rs',content:source});
      await invoke('build_file_read',{path:'app/src/main.rs'});
      await invoke('build_command_run',{command:JSON.parse(fs.readFileSync(path.join(cwd,'portable-fixture-command.json'),'utf8')).command,timeout_secs:30});
      fs.writeFileSync(path.join(agent,'fixture-gates.json'),JSON.stringify({names,denials,resumed}));
      mcp.stdin.end();
      await new Promise((resolve,reject)=>{ const timer=setTimeout(()=>{mcp.kill();reject(Error('MCP did not dispose'));},5000); mcp.on('exit',code=>{clearTimeout(timer);code===0?resolve():reject(Error('MCP exit '+code+' '+stderr))}); });
      const message={role:'assistant',content:[{type:'text',text:resumed?'Persistence fixed.':'Initial candidate.'}],api:'offline-test',provider:selected.provider,model:selected.id,thinkingLevel:effort,stopReason:'stop',timestamp:Date.now(),responseId:resumed?'fixture-turn-2':'fixture-turn-1',usage:{input:10,output:5,cacheRead:2,cacheWrite:0,totalTokens:17,cost:{total:0}}};
      emit({type:'message_end',message});emit({type:'message_end',message});
      emit({type:'agent_end'});emit({type:'agent_settled',aborted:false});
    } else response({});
  }).catch(e=>{process.stderr.write(String(e.stack)+'\n');process.exitCode=1;process.stdin.destroy();if(mcp)mcp.kill();});
}).on('close',()=>serial.then(()=>{if(mcp)mcp.stdin.end();}));
