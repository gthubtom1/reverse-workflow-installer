"""Official stable metadata resolution. No third party Python dependencies."""
import json
import re
import urllib.error
import urllib.request


class InstallError(Exception):
    pass


def http_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "reverse-workflow-installer/0.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise InstallError(f"官方来源不存在或尚未发布 (HTTP 404): {url}") from exc
        raise InstallError(f"元数据请求失败 HTTP {exc.code}: {url}") from exc
    except (OSError, ValueError) as exc:
        raise InstallError(f"无法读取官方元数据: {url} ({type(exc).__name__})") from exc


def stable(version):
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", version))


def resolve(manifest, fetch=http_json):
    rea = fetch(manifest["rea"]["metadata"])
    version = rea.get("version", "")
    if rea.get("name") != "rea-agents" or not stable(version):
        raise InstallError("rea-agents latest 未指向可识别的稳定版；拒绝回退或安装预发布版")
    if not rea.get("dist", {}).get("integrity") or not rea.get("engines", {}).get("node"):
        raise InstallError("REA 元数据缺 dist.integrity 或 engines.node")
    spec = fetch(manifest["spec_kit"]["metadata"])
    candidates = []
    for ver, files in spec.get("releases", {}).items():
        if stable(ver) and files and any(not f.get("yanked", False) for f in files):
            candidates.append(ver)
    if spec.get("info", {}).get("name", "").replace("_", "-") != "specify-cli" or not candidates:
        raise InstallError("specify-cli 未找到非撤回的稳定发行版")
    specver = max(candidates, key=lambda v: tuple(map(int, v.split("."))))
    files = spec["releases"][specver]
    api = manifest["reverse"]["api"]
    try:
        release = fetch(api + "/releases/latest")
    except InstallError as exc:
        if "HTTP 404" not in str(exc):
            raise
        release = None
    if release:
        if release.get("draft") or release.get("prerelease"):
            raise InstallError("reverse latest 不是正式 release")
        ref = release["tag_name"]
        # The commits endpoint peels both annotated and lightweight tags.
        from urllib.parse import quote
        commit = fetch(api + "/commits/" + quote(ref, safe=""))["sha"]
    else:
        ref = "main"
        commit = fetch(api + "/commits/main")["sha"]
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise InstallError("reverse commit 身份无效")
    return {
        "rea": {"version": version, "integrity": rea["dist"]["integrity"], "node_engine": rea["engines"]["node"], "repository": manifest["rea"]["repository"]},
        "spec_kit": {"version": specver, "repository": manifest["spec_kit"]["repository"], "artifacts": [{"filename": f["filename"], "sha256": f.get("digests", {}).get("sha256"), "requires_python": f.get("requires_python")} for f in files if not f.get("yanked", False)]},
        "reverse": {"ref": ref, "commit": commit, "repository": manifest["reverse"]["repository"]},
    }
