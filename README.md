# blutter-build

用 GitHub Actions CI 编译 blutter（Dart AOT 逆向工具）并分析目标 APK 的 libapp.so。

## 原理

blutter（https://github.com/worawit/blutter）分析 libapp.so 前需要**针对目标 Dart 版本编译 Dart VM + blutter 本体**（会 clone dart-lang/sdk 并编译，重活）。在本地 macOS 上这条链路被 brew 升级 cmake 卡死；Linux CI runner 上 apt 一条命令装齐依赖，编译顺畅。

## 目录结构

```
targets/
  <target_name>/lib/arm64-v8a/
    libapp.so        # 目标 APK 的 Dart AOT 快照
    libflutter.so    # Flutter 引擎(用于 Dart 版本检测)
.github/workflows/build-blutter.yml
```

## 使用

1. 新增目标：`targets/<名称>/lib/arm64-v8a/` 下放 libapp.so + libflutter.so（本机路径提取见下）
2. 在 `.github/workflows/build-blutter.yml` 的 matrix.target 里加 `<名称>`
3. push 或 Actions 页手动触发
4. 完成自动产出 artifact：
   - `blutter-out-<target>` — 分析结果：`pp.txt`（对象池）、`objs.txt`（对象 dump）、`asm/`（带符号汇编）、`blutter_frida.js`（Frida hook 模板）
   - `blutter-bin-<target>` — 编译好的 dartvm + blutter 可执行（下次同版本可复用）

## 本地提取 .so

```bash
# 从已安装包(需 root)或 APK 提取
zipinfo -l 原版.apk 'lib/arm64-v8a/*.so' | grep -E "libapp|libflutter"
unzip -o 原版.apk -d /tmp/x 'lib/arm64-v8a/libapp.so' 'lib/arm64-v8a/libflutter.so'
```

## 注意

- 目标是私有 repo：不要加入未授权、含敏感信息的 APK。libapp.so 本身含 App 业务代码，仅限自有/授权分析。
- 首次跑会 clone dart-lang/sdk(3.6.2) 并编译 Dart VM，约 15-40 分钟，属正常。