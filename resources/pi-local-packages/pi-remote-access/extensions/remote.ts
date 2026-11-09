import { networkInterfaces } from "node:os";
import { resolveAgentDir } from "../lib/agent-dir.ts";
import { listReachableAddresses, type Address, type NetworkInterfaces } from "../lib/net.ts";
import type { CommandContext, ExtensionApi } from "../lib/pi-api.ts";
import { canConnect, detectPort } from "../lib/probe.ts";
import { renderQrBlock } from "../lib/qr.ts";
import { allowedHostsEnv, mergeAllowedHosts, readRemoteSettings, writeRemoteSettings } from "../lib/remote-settings.ts";
import { tailscaleCandidates, tailscaleGuiCandidates } from "../lib/tailscale-binary.ts";
import { describeStatus, isUsable, parseTailscaleStatus, statusFromAddresses, type TailscaleStatus } from "../lib/tailscale.ts";
import { PasswordVault, PASSWORD_REFERENCE } from "../lib/password-vault.ts";

// Derived from pi-seep-ext at 2742f417; original source remains in upstream/.
const MENU_LAN = "🏠 局域网（同一 Wi-Fi）";
const MENU_TAILSCALE = "🌍 Tailscale（随时随地）";
const MENU_PASSWORD = "🔑 登录密码（状态 / 生成 / 关闭）";
const MENU_CHECK = "🩺 自检（绑定 / 端口 / 可达性）";
const MENU_QR = "▦ 二维码（开启 / 关闭）";

export interface RemoteRuntime {
  env: NodeJS.ProcessEnv;
  networkInterfaces: typeof networkInterfaces;
  canConnect: typeof canConnect;
  detectPort: typeof detectPort;
  tailscaleCandidates: typeof tailscaleCandidates;
  tailscaleGuiCandidates: typeof tailscaleGuiCandidates;
  renderQrBlock: typeof renderQrBlock;
}

export default function remoteExtension(pi: ExtensionApi): void { registerRemote(pi); }

/** Tests supply a fresh environment object and mocks, never mutate process.env. */
export function registerRemote(pi: ExtensionApi, overrides: Partial<RemoteRuntime> = {}): void {
  const runtime: RemoteRuntime = {
    env: process.env, networkInterfaces, canConnect, detectPort,
    tailscaleCandidates, tailscaleGuiCandidates, renderQrBlock, ...overrides,
  };
  const env = runtime.env;
  const agentDir = resolveAgentDir(env);
  const vault = new PasswordVault(env);
  const sensitive = new Set<string>();
  if (env.PI_WEB_PASSWORD) sensitive.add(env.PI_WEB_PASSWORD);
  let forceQr = false;
  let cliPath: string | null | undefined;

  // Defense in depth for reports that contain external hostnames or CLI fields.
  // Never log filesystem/CLI errors: their content is outside our control.
  const safe = (text: string): string => {
    if (env.PI_WEB_PASSWORD) sensitive.add(env.PI_WEB_PASSWORD);
    let result = text;
    for (const value of [...sensitive].sort((a, b) => b.length - a.length)) result = result.split(value).join("[已隐藏]");
    return result;
  };
  const notify = (ctx: CommandContext, text: string, type: "info" | "warning" | "error" = "info"): void => ctx.ui.notify(safe(text), type);
  const post = async (content: string): Promise<void> => {
    await pi.sendMessage({ customType: "remote", content: safe(content), display: true });
  };
  const restorePassword = (): void => {
    if (env.PI_WEB_PASSWORD) return;
    const value = vault.readEnabled();
    if (value) { sensitive.add(value); env.PI_WEB_PASSWORD = value; }
  };
  restorePassword();
  const stored = readRemoteSettings(agentDir); // Ignores legacy password; never migrates it.
  if (stored.allowedHosts.length) {
    env.PI_WEB_ALLOWED_HOSTS = allowedHostsEnv([...(env.PI_WEB_ALLOWED_HOSTS ?? "").split(","), ...stored.allowedHosts]);
  }

  const port = (): number => runtime.detectPort(process.argv, env);
  const addresses = (): Address[] => listReachableAddresses(runtime.networkInterfaces() as NetworkInterfaces);
  const allowedHosts = (): string[] => [env.PI_WEB_HOSTNAME, ...(env.PI_WEB_ALLOWED_HOSTS?.split(",") ?? [])]
    .map(v => v?.trim()).filter((v): v is string => Boolean(v) && v !== "0.0.0.0");
  const passwordAdvice = (): string => env.PI_WEB_PASSWORD
    ? "密码已开启（打开后输一次）" : "⚠ 无密码：同一网络内任何设备都能进（`/remote password` 可加）";
  const credentialLocation = (): string => `凭据仓引用：${PASSWORD_REFERENCE}\n本机路径：${vault.paths.password}`;

  async function resolveTailscale(): Promise<{ path: string; status: TailscaleStatus } | null> {
    if (cliPath === null) return null;
    for (const candidate of runtime.tailscaleCandidates({ env })) {
      if (cliPath && candidate.path !== cliPath) continue;
      try {
        // This is the only subprocess operation in the recovered extension.
        const result = await pi.exec(candidate.path, ["status", "--json"], { timeout: 8000 });
        if (result.killed || result.code !== 0) continue;
        const status = parseTailscaleStatus(result.stdout);
        if (status) { cliPath = candidate.path; return { path: candidate.path, status }; }
      } catch { /* Try another candidate; never echo stdout/stderr/errors. */ }
    }
    if (!cliPath) cliPath = null;
    return null;
  }

  async function connectionBlock(heading: string, url: string, extra: string[], ctx: CommandContext): Promise<string> {
    // Redact before optional encoding too: a QR must never encode a password.
    const safeUrl = safe(url);
    const lines = [heading, safeUrl, ...extra.filter(Boolean)];
    if (forceQr || ctx.mode === "tui") {
      let qr: string | null = null;
      try { qr = await runtime.renderQrBlock(safeUrl); } catch { /* Optional encoder failure. */ }
      lines.push("", qr || "（二维码需要可选依赖 qrcode-generator，未安装也能用上面的网址）");
    }
    return lines.join("\n");
  }

  async function showLan(ctx: CommandContext): Promise<void> {
    const currentPort = port();
    const candidates = addresses().filter(a => a.kind !== "tailscale");
    const probed = await Promise.all(candidates.map(async a => ({ ...a, reachable: await runtime.canConnect(a.address, currentPort) })));
    const reachable = probed.filter(a => a.reachable);
    const preferred = reachable.find(a => a.kind === "lan") ?? reachable[0];
    if (!preferred) {
      await post([
        "手机连不上：未探测到可达的局域网地址",
        `当前绑定 ${env.PI_WEB_HOSTNAME?.trim() || "127.0.0.1"} · 端口 ${currentPort}`,
        "请检查服务绑定和网络；需要远程访问时，用 PI_WEB_HOSTNAME=0.0.0.0 启动 pi-web。",
      ].join("\n"));
      return;
    }
    const saved = writeRemoteSettings({ lastMode: "lan" }, agentDir).saved;
    const extra: string[] = [];
    if (preferred.kind !== "lan") extra.push("⚠ 这是虚拟网卡，手机可能连不上");
    const other = reachable.find(a => a.address !== preferred.address && a.kind === "lan");
    if (other) extra.push(`备用地址 ${other.address}:${currentPort}`);
    if (!saved) extra.push("⚠ 普通配置未保存（旧密码字段或无效/不可写配置需另行处理）");
    extra.push(passwordAdvice());
    await post(await connectionBlock("手机打开（同一 Wi-Fi）", `http://${preferred.address}:${currentPort}`, extra, ctx));
  }

  async function showTailscale(ctx: CommandContext): Promise<void> {
    const currentPort = port();
    const found = await resolveTailscale();
    const status = found?.status ?? statusFromAddresses(addresses());
    if (!status) {
      const gui = runtime.tailscaleGuiCandidates({ env });
      await post([
        "没检测到 Tailscale：CLI 和网卡均无可用状态。",
        "请在本机 Tailscale 客户端登录；CLI 不在 PATH 时可配置 TAILSCALE_PATH 后重启 pi-web。",
        gui[0] ? `本机客户端：${gui[0]}` : "",
      ].filter(Boolean).join("\n"));
      return;
    }
    if (!isUsable(status)) {
      const detail = describeStatus(status);
      await post([detail.line, detail.advice, "请在本机 Tailscale 客户端完成连接后重试 /remote tailscale。"].filter(Boolean).join("\n"));
      return;
    }
    const extra: string[] = [];
    if (!(await runtime.canConnect(status.ips[0], currentPort))) extra.push("⚠ 探测不通：请检查服务绑定和网络");
    if (status.dnsName) {
      const allowed = allowedHosts();
      let enabled = allowed.includes(status.dnsName);
      if (!enabled && await ctx.ui.confirm("也启用域名访问？", safe(`${status.dnsName}\n将此域名加入 pi-web 的允许列表，保存后立即生效。`))) {
        const next = mergeAllowedHosts(allowed, status.dnsName);
        if (writeRemoteSettings({ allowedHosts: next }, agentDir).saved) {
          env.PI_WEB_ALLOWED_HOSTS = allowedHostsEnv(next);
          enabled = true;
        } else extra.push("⚠ 域名未启用：普通配置写入失败");
      }
      if (enabled) extra.unshift(`域名 http://${status.dnsName}:${currentPort}`);
    }
    if (status.source === "interface") extra.push("（没找到 Tailscale CLI，状态是从网卡读的）");
    if (!writeRemoteSettings({ lastMode: "tailscale" }, agentDir).saved) extra.push("⚠ 上次模式未保存：普通配置写入失败");
    extra.push(passwordAdvice());
    await post(await connectionBlock("手机打开（手机需开着 Tailscale）", `http://${status.ips[0]}:${currentPort}`, extra, ctx));
  }

  async function managePassword(ctx: CommandContext): Promise<void> {
    const options = ["密码状态", "生成一个新密码（保存后立即生效）", "关闭密码（同网络内谁都能进）"];
    const choice = await ctx.ui.select("登录密码（状态 / 生成 / 关闭）", options);
    if (choice === options[0]) {
      notify(ctx, `密码${env.PI_WEB_PASSWORD ? "已开启" : "未开启"}\n${credentialLocation()}`);
    } else if (choice === options[1]) {
      const result = vault.generate();
      if (!result.saved) { notify(ctx, "密码未更改：凭据仓写入失败。", "error"); return; }
      sensitive.add(result.value);
      env.PI_WEB_PASSWORD = result.value;
      notify(ctx, `新密码已保存并立即生效\n${credentialLocation()}`);
    } else if (choice === options[2]) {
      if (!(await ctx.ui.confirm("关闭密码？", "关闭后，能连通这台机器的人都可以操作 agent。关闭状态会持久保存，重启后不会恢复凭据仓密码。"))) return;
      if (!vault.disable()) { notify(ctx, "密码未关闭：关闭状态写入失败。", "error"); return; }
      if (env.PI_WEB_PASSWORD) sensitive.add(env.PI_WEB_PASSWORD);
      delete env.PI_WEB_PASSWORD;
      notify(ctx, "密码已关闭，关闭状态已保存。");
    }
  }

  async function selfCheck(): Promise<void> {
    const currentPort = port();
    const all = addresses();
    const probed = await Promise.all(all.map(async a => ({ ...a, reachable: await runtime.canConnect(a.address, currentPort) })));
    const found = await resolveTailscale();
    const ts = describeStatus(found?.status ?? statusFromAddresses(all));
    const lan = probed.find(a => a.reachable && a.kind === "lan");
    const allowed = allowedHosts();
    await post([
      "自检",
      `绑定 ${env.PI_WEB_HOSTNAME?.trim() || "127.0.0.1"} · 端口 ${currentPort} · 密码 ${env.PI_WEB_PASSWORD ? "已开启" : "未设置"} · 白名单 ${allowed.length ? allowed.join(",") : "无"}`,
      `${ts.line}${found ? ` · CLI ${found.path}` : ""}`,
      `地址 ${probed.map(a => `${a.address} ${a.reachable ? "✅" : "❌"}(${a.kind})`).join(" · ") || "（没找到可用地址）"}`,
      lan ? `手机可用 http://${lan.address}:${currentPort}` : "局域网地址都不通：请检查服务绑定和网络。",
      ts.advice ? `提示 ${ts.advice}` : "",
    ].filter(Boolean).join("\n"));
  }

  function toggleQr(ctx: CommandContext): void {
    forceQr = !forceQr;
    notify(ctx, forceQr ? "二维码已开启（网页行高可能影响扫描；终端正常）" : "二维码已关闭，只显示网址");
  }

  pi.registerCommand("remote", {
    description: "手机访问：局域网 / Tailscale / 密码状态 / 自检 / 二维码",
    handler: async (args, ctx) => {
      const arg = args.trim().toLowerCase();
      if (arg === "lan" || arg === "局域网") return showLan(ctx);
      if (["ts", "tailscale", "公网"].includes(arg)) return showTailscale(ctx);
      if (["password", "pw", "密码"].includes(arg)) return managePassword(ctx);
      if (arg === "check" || arg === "自检") return selfCheck();
      if (arg === "qr") return toggleQr(ctx);
      if (arg && arg !== "menu") { notify(ctx, "用法：/remote [lan | tailscale | password | check | qr]"); return; }
      const last = readRemoteSettings(agentDir).lastMode;
      const preferred = last === "tailscale" ? MENU_TAILSCALE : last === "lan" ? MENU_LAN : null;
      const menu = [MENU_LAN, MENU_TAILSCALE, MENU_PASSWORD, MENU_CHECK, MENU_QR];
      const choice = await ctx.ui.select("让手机连上", preferred ? [preferred, ...menu.filter(v => v !== preferred)] : menu);
      if (choice === MENU_LAN) return showLan(ctx);
      if (choice === MENU_TAILSCALE) return showTailscale(ctx);
      if (choice === MENU_PASSWORD) return managePassword(ctx);
      if (choice === MENU_CHECK) return selfCheck();
      if (choice === MENU_QR) return toggleQr(ctx);
    },
  });

  pi.on("session_start", (_event, ctx) => {
    restorePassword();
    if (ctx.hasUI) ctx.ui.setStatus("command:/remote", "📱 远程访问");
  });
}
