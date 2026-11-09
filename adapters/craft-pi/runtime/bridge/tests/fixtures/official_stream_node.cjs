// Synthetic official streaming shape; Node built-ins only, no provider/MCP/network.
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const agent = process.env.PI_CODING_AGENT_DIR;
const args = process.argv.slice(2);
const sessions = args[args.indexOf('--session-dir') + 1];
const file = path.join(sessions, 'dynamic-stream.jsonl');
const id = 'synthetic-dynamic-session';
const scenario = fs.readFileSync(path.join(agent, 'scenario'), 'utf8');
let provider, model, thinking;
const emit = record => process.stdout.write(JSON.stringify(record) + '\n');
readline.createInterface({ input: process.stdin }).on('line', line => {
  const request = JSON.parse(line);
  const response = data => emit({ type: 'response', id: request.id, command: request.type, success: true, data });
  fs.appendFileSync(path.join(agent, 'commands.jsonl'), request.type + '\n');
  switch (request.type) {
    case 'set_model': provider = request.provider; model = request.modelId; response({ id: model, provider }); break;
    case 'set_thinking_level': thinking = request.level; response({}); break;
    case 'get_state': {
      const state = { model: { id: model, provider }, thinkingLevel: thinking, isStreaming: false,
        isCompacting: false, pendingMessageCount: 0, sessionId: id, sessionFile: file };
      if (scenario === 'dynamic-state-missing-thinking') delete state.thinkingLevel;
      if (scenario === 'dynamic-state-wrong-thinking') state.thinkingLevel = 'low';
      response(state);
      break;
    }
    case 'prompt': {
      fs.writeFileSync(file, JSON.stringify({ type: 'session', version: 3, id, cwd: process.cwd() }) + '\n');
      response({ disposition: 'started' });
      emit({ type: 'agent_start' });
      const secret = process.env.CRAFT_BRIDGE_ALLOWED_TEST_KEY;
      const body = JSON.stringify({ provider: secret, model: secret, thinkingLevel: secret });
      const partial = { role: 'assistant', provider, model, api: 'fixture', content: [], stopReason: 'stop', timestamp: 123 };
      // Official agent-loop adds requested thinkingLevel only to response.result().
      emit({ type: 'message_start', message: { ...partial } });
      emit({ type: 'message_update', message: { ...partial, content: [{ type: 'text', text: body }] },
        assistantMessageEvent: { type: 'text_delta', delta: body } });
      emit({ type: 'tool_execution_start', toolCallId: 'safe-tool-call', toolName: 'mcp__fixture__read', args: { provider: secret } });
      emit({ type: 'tool_execution_end', toolCallId: 'safe-tool-call', toolName: 'mcp__fixture__read',
        result: { content: [{ type: 'text', text: body }] }, isError: false });
      const message = { ...partial, thinkingLevel: thinking, content: [{ type: 'text', text: body }],
        errorMessage: secret, usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: { total: 0 } } };
      if (scenario === 'dynamic-no-final-thinking') delete message.thinkingLevel;
      if (scenario === 'dynamic-final-wrong-thinking') message.thinkingLevel = 'low';
      if (scenario === 'dynamic-provider-wrong-thinking') message.providerThinkingLevel = 'low';
      if (scenario === 'dynamic-unknown-response') message.responseModel = 'untrusted-' + secret + '-physical';
      emit({ type: 'message_end', message });
      emit({ type: 'turn_end', message });
      emit({ type: 'agent_end', messages: [message], willRetry: false });
      emit({ type: 'agent_settled', aborted: false });
      break;
    }
    case 'clear_queue': response({}); break;
    case 'abort': response({}); break;
    default: response({});
  }
});
