#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_blutter_only.py —— 为指定 Dart 版本编译 dartvm + blutter 可执行（只编译，不分析）

用法（必须在 blutter 源码 checkout 目录内运行，cwd = blutter/）:
    python3 ../scripts/build_blutter_only.py <dart_version> [os] [arch]
    例:  python3 ../scripts/build_blutter_only.py 3.8.1 android arm64

逻辑（复刻 blutter.py 的 find_compat_macro + cmake_blutter，但【不 import blutter.py】，
因为 blutter.py 顶层直接执行 argparse，import 会触发解析失败）:
  1. 调 dartvm_fetch_build.py <ver> <os> <arch> 编译对应版本 dartvm
     （生成 blutter/packages/include/dartvm<ver>/ 供 find_compat_macro 读取）
  2. 按 DartLibInfo 计算 name_suffix / blutter_name（与 BlutterInput.__init__ 一致）
  3. cmake -GNinja 编译 blutter 本体（链接该版本 dartvm）并 install 到 blutter/bin/

产物: blutter/bin/blutter_<lib_name><suffix> + blutter/packages/
"""
import mmap
import os
import subprocess
import sys


def find_compat_macro(dart_version, no_analysis=False, blutter_dir=None):
    """复刻 blutter.py find_compat_macro：按 dartvm 头文件内容生成兼容宏。
    依赖 dartvm_fetch_build.py 已把头文件拷到 packages/include/dartvm<ver>/"""
    if blutter_dir is None:
        blutter_dir = os.getcwd()  # 调用方保证 cwd = blutter 源码根
    pkg_inc = os.path.join(blutter_dir, 'packages', 'include')
    macros = []
    include_path = os.path.join(pkg_inc, 'dartvm' + dart_version)
    vm_path = os.path.join(include_path, 'vm')
    with open(os.path.join(vm_path, 'class_id.h'), 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if mm.find(b'V(LinkedHashMap)') != -1:
            macros.append('-DOLD_MAP_SET_NAME=1')
            if mm.find(b'V(ImmutableLinkedHashMap)') == -1:
                macros.append('-DOLD_MAP_NO_IMMUTABLE=1')
        if mm.find(b' kLastInternalOnlyCid ') == -1:
            macros.append('-DNO_LAST_INTERNAL_ONLY_CID=1')
        if mm.find(b'V(TypeRef)') != -1:
            macros.append('-DHAS_TYPE_REF=1')
        if dart_version.startswith('3.') and mm.find(b'V(RecordType)') != -1:
            macros.append('-DHAS_RECORD_TYPE=1')
    with open(os.path.join(vm_path, 'class_table.h'), 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if mm.find(b'class SharedClassTable {') != -1:
            macros.append('-DHAS_SHARED_CLASS_TABLE=1')
    with open(os.path.join(vm_path, 'stub_code_list.h'), 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if mm.find(b'V(InitLateStaticField)') == -1:
            macros.append('-DNO_INIT_LATE_STATIC_FIELD=1')
    with open(os.path.join(vm_path, 'object_store.h'), 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if mm.find(b'build_generic_method_extractor_code)') == -1:
            macros.append('-DNO_METHOD_EXTRACTOR_STUB=1')
    with open(os.path.join(vm_path, 'object.h'), 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if mm.find(b'AsTruncatedInt64Value()') == -1:
            macros.append('-DUNIFORM_INTEGER_ACCESS=1')
    if no_analysis:
        macros.append('-DNO_CODE_ANALYSIS=1')
    return macros


def main():
    if len(sys.argv) < 2:
        print("usage: build_blutter_only.py <dart_version> [os] [arch]", file=sys.stderr)
        sys.exit(1)
    ver = sys.argv[1]
    os_name = sys.argv[2] if len(sys.argv) > 2 else 'android'
    arch = sys.argv[3] if len(sys.argv) > 3 else 'arm64'

    blutter_dir = os.getcwd()  # 调用方保证 cwd = blutter 源码根
    if not os.path.isfile(os.path.join(blutter_dir, 'dartvm_fetch_build.py')):
        print(f"[build_blutter_only] 错误: cwd 不是 blutter 源码根: {blutter_dir}", file=sys.stderr)
        sys.exit(1)

    # 1) 编译 dartvm（生成 packages/include/dartvm<ver>/）
    print(f"[build_blutter_only] 编译 dartvm {ver}_{os_name}_{arch} ...")
    subprocess.run([sys.executable, 'dartvm_fetch_build.py', ver, os_name, arch],
                   cwd=blutter_dir, check=True)

    # 2) name_suffix / blutter_name（与 BlutterInput.__init__ 一致）
    sys.path.insert(0, blutter_dir)
    from dartvm_fetch_build import DartLibInfo
    info = DartLibInfo(ver, os_name, arch)
    no_analysis = False
    name_suffix = ''
    if not info.has_compressed_ptrs:
        name_suffix += '_no-compressed-ptrs'
    if no_analysis:
        name_suffix += '_no-analysis'
    lib_name = info.lib_name
    blutter_name = f'blutter_{lib_name}{name_suffix}'

    # 3) 兼容宏
    macros = find_compat_macro(ver, no_analysis, blutter_dir)
    print(f"[build_blutter_only] lib={lib_name} suffix='{name_suffix}' macros={macros}")

    # 4) cmake 编译 blutter 本体（复刻 cmake_blutter）
    builddir = os.path.join(blutter_dir, 'build', blutter_name)
    subprocess.run(['cmake', '-GNinja', '-B', builddir,
                    f'-DDARTLIB={lib_name}', f'-DNAME_SUFFIX={name_suffix}',
                    '-DCMAKE_BUILD_TYPE=Release', '--log-level=NOTICE'] + macros,
                   cwd=os.path.join(blutter_dir, 'blutter'), check=True)
    subprocess.run(['ninja'], cwd=builddir, check=True)
    subprocess.run(['cmake', '--install', '.'], cwd=builddir, check=True)

    bin_file = os.path.join(blutter_dir, 'bin', blutter_name)
    print(f"[build_blutter_only] OK: {bin_file}")
    print(f"[build_blutter_only] 产物: blutter/bin/ + blutter/packages/")


if __name__ == '__main__':
    main()
