// Real Node CLI/argv/path fixture. Built-ins only; no Pi/provider/auth resources.
const fs = require('node:fs');
const path = require('node:path');
const args = process.argv.slice(2);
const arg = flag => args[args.indexOf(flag) + 1];
const agent = process.env.PI_CODING_AGENT_DIR;
const sessions = arg('--session-dir');
const file = args.includes('--session') ? arg('--session') : path.join(sessions, 'node-actual-session.jsonl');
const id = 'node-fixture-session-id';
let model = arg('--model');
let provider = arg('--provider');
let thinking = arg('--thinking');
fs.writeFileSync(path.join(agent, 'node-launch-proof.json'), JSON.stringify({
  entry: process.argv[1], cwd: process.cwd(), agent,
  sessionEnv: process.env.PI_CODING_AGENT_SESSION_DIR,
  sessionArg: sessions, resume: args.includes('--session') ? file : null,
  instructions: arg('--append-system-prompt')
}));
const emit = record => process.stdout.write(JSON.stringify(record) + '\n');
function command(record) {
  const response = data => emit({type:'response',id:record.id,command:record.type,success:true,data});
  switch(record.type) {
    case 'set_model': provider=record.provider; model=record.modelId; response({}); break;
    case 'set_thinking_level': thinking=record.level; response({}); break;
    case 'get_state': response({model:{id:model,provider},thinkingLevel:thinking,isStreaming:false,isCompacting:false,pendingMessageCount:0,sessionId:id,sessionFile:file}); break;
    case 'prompt': {
      if (!fs.existsSync(file)) fs.writeFileSync(file, JSON.stringify({type:'session',version:3,id,cwd:process.cwd(),timestamp:'2026-11-09T00:00:00Z'})+'\n');
      response({disposition:'started'});
      emit({type:'agent_start'});
      emit({type:'message_update',assistantMessageEvent:{type:'text_delta',delta:'real Node fixture'}});
      const message={role:'assistant',content:[{type:'text',text:'real Node fixture'}],api:'fixture',provider,model,thinkingLevel:thinking,stopReason:'stop',timestamp:123,usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{total:0}}};
      fs.appendFileSync(file,JSON.stringify({type:'message',id:'node-message',parentId:null,timestamp:'2026-11-09T00:00:00Z',message})+'\n');
      emit({type:'message_end',message});
      emit({type:'agent_end',messages:[message],willRetry:false});
      emit({type:'agent_settled',aborted:false}); break;
    }
    case 'clear_queue': response({steering:[],followUp:[]}); break;
    case 'abort': response({}); break;
    default: response({});
  }
}
let pending=Buffer.alloc(0);
process.stdin.on('data', chunk => {
  pending=Buffer.concat([pending,chunk]);
  let lf;
  while((lf=pending.indexOf(10))!==-1) {
    const line=pending.subarray(0,lf).toString('utf8'); pending=pending.subarray(lf+1);
    command(JSON.parse(line));
  }
});
