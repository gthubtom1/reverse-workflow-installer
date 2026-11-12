"""Official stable metadata resolution. No third party Python dependencies."""
import json
import os
import re
import urllib.error
import urllib.request


class InstallError(Exception):
    pass


def http_json(url):
    headers = {"User-Agent": "reverse-workflow-installer/0.1", "Accept": "application/json"}
    if "api.github.com/" in url:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
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


COMPONENTS = ("rea", "spec_kit", "reverse", "shell_guard", "craft")


def resolve(manifest, fetch=http_json, components=None, spec_kit_version=None, rea_version=None):
    """Resolve requested components; existing installs may reuse receipt pins unless upgraded explicitly."""
    requested = [key for key in COMPONENTS if key not in ("shell_guard", "craft")] if components is None else [str(key) for key in components]
    for key in requested:
        if key not in COMPONENTS:
            raise InstallError(f"未知组件: {key}")
    if spec_kit_version is not None:
        if "spec_kit" not in requested:
            raise InstallError("--spec-kit-version 需要选择 spec-kit 组件")
        if not isinstance(spec_kit_version, str) or not stable(spec_kit_version):
            raise InstallError("--spec-kit-version 必须是精确稳定版本（例如 1.3.1）")
    if rea_version is not None:
        if "rea" not in requested:
            raise InstallError("--rea-version 需要选择 rea 组件")
        if not isinstance(rea_version, str) or not stable(rea_version):
            raise InstallError("REA 版本必须是精确稳定版本")
    if "craft" in requested:
        raise InstallError("Craft remote artifacts unsupported until compatible verified release assets are published; use --craft-bundle")
    result = {}
    if "rea" in requested:
        metadata_url = manifest["rea"]["metadata"]
        if rea_version is not None:
            metadata_url = metadata_url.rsplit("/", 1)[0] + "/" + rea_version
        rea = fetch(metadata_url)
        version = rea.get("version", "")
        if rea_version is not None and version != rea_version:
            raise InstallError("REA 元数据版本与冻结版本不一致")
        if rea.get("name") != "rea-agents" or not stable(version):
            raise InstallError("rea-agents 元数据未指向可识别的稳定版；拒绝回退或安装预发布版")
        if not rea.get("dist", {}).get("integrity") or not rea.get("engines", {}).get("node"):
            raise InstallError("REA 元数据缺 dist.integrity 或 engines.node")
        result["rea"] = {"version": version, "integrity": rea["dist"]["integrity"], "node_engine": rea["engines"]["node"], "repository": manifest["rea"]["repository"]}
    if "spec_kit" in requested:
        result["spec_kit"] = _resolve_spec_kit(manifest, fetch, spec_kit_version)
    if "reverse" in requested:
        result["reverse"] = _resolve_reverse(manifest, fetch)
    if "shell_guard" in requested:
        from urllib.parse import quote
        entry = manifest["shell_guard"]
        resolved = fetch(entry["api"] + "/commits/" + quote(entry["release_ref"], safe=""))
        commit = resolved.get("sha")
        repository_tree = resolved.get("commit", {}).get("tree", {}).get("sha")
        if not re.fullmatch(r"[a-f0-9]{40}", str(repository_tree)):
            raise InstallError("shell-guard release 缺少冻结 Git tree")
        if not re.fullmatch(r"[a-f0-9]{40}", str(commit)) or (entry.get("commit") is not None and commit != entry["commit"]):
            raise InstallError("shell-guard release commit 与固定清单不符；拒绝移动 tag 或回退 main")
        result["shell_guard"] = {**entry, "commit": commit, "repository_tree": repository_tree, "ref": entry["release_ref"], "mode": "clone-frozen-commit"}
    return result


def _resolve_spec_kit(manifest, fetch, version=None):
    spec = fetch(manifest["spec_kit"]["metadata"])
    candidates = []
    for ver, files in spec.get("releases", {}).items():
        if stable(ver) and files and any(not f.get("yanked", False) for f in files):
            candidates.append(ver)
    if spec.get("info", {}).get("name", "").replace("_", "-") != "specify-cli" or not candidates:
        raise InstallError("specify-cli 未找到非撤回的稳定发行版")
    if version is not None and version not in candidates:
        raise InstallError(f"指定的 specify-cli 版本 {version} 不存在、已撤回或没有发行文件")
    specver = version if version is not None else max(candidates, key=lambda v: tuple(map(int, v.split("."))))
    files = [f for f in spec["releases"][specver] if not f.get("yanked", False)]
    if version is not None and any(not re.fullmatch(r"[a-f0-9]{64}", str(f.get("digests", {}).get("sha256", ""))) for f in files):
        raise InstallError("指定的 specify-cli 发行文件缺少有效 SHA-256")
    result = {"version": specver, "repository": manifest["spec_kit"]["repository"], "artifacts": [{"filename": f["filename"], "sha256": f.get("digests", {}).get("sha256"), "requires_python": f.get("requires_python")} for f in files]}
    if version is not None:
        result["version_selection"] = "explicit-pypi-stable-release"
    return result


def _resolve_reverse(manifest, fetch):
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
    return {"ref": ref, "commit": commit, "repository": manifest["reverse"]["repository"]}
