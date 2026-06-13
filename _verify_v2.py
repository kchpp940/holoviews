#!/usr/bin/env python
"""验证 ArtifactManager 三项收紧改动：
1. USER_OUTPUT 只解除登记，不销毁内容/文件
2. backend handler source 保护
3. mirror 类不再继承 dict，无本地状态
"""

from __future__ import print_function

import os
import sys
import tempfile

from holoviews.plotting.artifact_manager import (
    ArtifactCategory, ArtifactKind, CleanupPolicy,
    artifact_manager,
)
from holoviews.plotting.renderer import Renderer, _PlotRegistryMirror
from holoviews.plotting.mpl.renderer import MPLRenderer, _BboxCacheMirror


def test1_user_output_only_deregister():
    """USER_OUTPUT 只解除登记，绝不 unlink 文件或清空内容"""
    print("=" * 70)
    print("[1/3] USER_OUTPUT 释放语义测试")
    print("-" * 70)

    artifact_manager.release_all(include_user_output=True)
    artifact_manager.cache_clear()

    # --- 测试 FILE_OUTPUT: 绝不 unlink ---
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(b"PNG_CONTENT")
    tmp.close()
    file_path = tmp.name

    assert os.path.exists(file_path), f"测试文件应存在: {file_path}"

    art_file = artifact_manager.register_output_file(
        file_path, format="png", refs={"test": "1"}
    )

    # 检查分类
    assert art_file.kind == ArtifactKind.FILE_OUTPUT
    assert art_file.category == ArtifactCategory.USER_OUTPUT

    # 普通 release_all 不应动它
    cnt = artifact_manager.release_all()
    assert cnt == 0, f"普通 release_all 不应释放 USER_OUTPUT，释放了 {cnt} 个"
    assert os.path.exists(file_path), f"普通 release_all 不应删除文件"
    assert not art_file.released, f"USER_OUTPUT 不应被 release_all 释放"

    # force release_all 也只能解除登记，不能删除文件
    cnt = artifact_manager.release_all(include_user_output=True)
    assert cnt == 1, f"force release_all 应释放 1 个 USER_OUTPUT，实际 {cnt}"
    assert art_file.released, f"force 后应标记 released"
    assert art_file.path == file_path, "path 引用仍应保留"
    assert art_file.obj is None, "obj 引用应已 drop"
    assert os.path.exists(file_path), "force release_all 也不能删除用户文件！"

    # 直接调用 art.release() 也不能删文件
    art_file2 = artifact_manager.register_output_file(file_path, format="png")
    art_file2.release()
    assert os.path.exists(file_path), "art.release() 也不能删除用户文件！"

    print("  ✓ FILE_OUTPUT: 无论如何都不 unlink 用户文件")

    # --- 测试 DATA_OUTPUT: 只 drop 引用，不修改内容 ---
    data = bytearray(b"ORIGINAL_DATA")  # mutable, 可以检查是否被修改
    art_data = artifact_manager.register_output_data(data, format="bytes")
    assert art_data.category == ArtifactCategory.USER_OUTPUT

    art_data.release()
    assert art_data.obj is None, "obj 引用应已 drop"
    assert data == bytearray(b"ORIGINAL_DATA"), "data 内容不能被修改！"

    print("  ✓ DATA_OUTPUT: 只 drop 引用，不修改/清空数据")

    # --- 测试 MIME_OUTPUT: 只 drop 引用，不修改 ---
    mime = {"text/html": "<p>hello</p>", "image/png": b"PNG"}
    art_mime = artifact_manager.register_output_mime(mime)
    assert art_mime.category == ArtifactCategory.USER_OUTPUT

    art_mime.release()
    assert art_mime.obj is None
    assert mime == {"text/html": "<p>hello</p>", "image/png": b"PNG"}, "MIME 内容不能被修改！"

    print("  ✓ MIME_OUTPUT: 只 drop 引用，不修改/清空内容")

    # 清理测试文件
    os.unlink(file_path)
    print("  ✓ 全部 USER_OUTPUT 测试通过")


def test2_backend_source_protection():
    """backend handler 只清理 source != user 的对象"""
    print()
    print("=" * 70)
    print("[2/3] Backend handler source 保护测试")
    print("-" * 70)

    artifact_manager.release_all(include_user_output=True)

    # 测试: source=user 的对象不被清理
    class FakeDoc:
        def __init__(self):
            self.root_count = 3
            self.cleared = False
        @property
        def roots(self):
            return [object()] * self.root_count
        def remove_root(self, r):
            self.root_count -= 1
        def clear(self):
            self.cleared = True
            self.root_count = 0

    doc = FakeDoc()

    # source=renderer (默认) — 应该被清理
    art_renderer = artifact_manager.register_external_object(
        ArtifactKind.BOKEH_DOCUMENT, doc, source="renderer",
    )
    art_renderer.release()
    assert doc.cleared, "source=renderer 的文档应被 clear()"
    assert art_renderer.obj is None

    # source=user — 不应该被清理，只 drop 引用
    doc2 = FakeDoc()
    art_user = artifact_manager.register_external_object(
        ArtifactKind.BOKEH_DOCUMENT, doc2, source="user",
    )
    art_user.release()
    assert not doc2.cleared, "source=user 的文档不能被 clear()！"
    assert doc2.root_count == 3, "source=user 的文档 remove_root 不能被调用！"
    assert art_user.obj is None, "但引用应该被 drop"

    print("  ✓ BOKEH_DOCUMENT: source=user 保护有效")

    # 测试 MPL_FIGURE source 保护
    class FakeFig:
        def __init__(self):
            self.closed = False
            self.axes_cleared = 0
        @property
        def axes(self):
            class FakeAx:
                def cla(self): pass
                def clear(self): pass
            return [FakeAx(), FakeAx()]
        def clf(self):
            self.axes_cleared += 1
        @property
        def number(self):
            return None

    # 注意: plt.close 在这个环境里不能实际测试，但我们可以测试
    # 非 user 的对象应该走到 handler，user 的应该跳过
    fig_user = FakeFig()
    art_user_fig = artifact_manager.register_external_object(
        ArtifactKind.MPL_FIGURE, fig_user, source="user",
    )
    art_user_fig.release()
    assert fig_user.axes_cleared == 0, "source=user 的 figure 不能被 clf！"
    assert art_user_fig.obj is None

    fig_renderer = FakeFig()
    art_renderer_fig = artifact_manager.register_external_object(
        ArtifactKind.MPL_FIGURE, fig_renderer, source="renderer",
    )
    art_renderer_fig.release()
    assert fig_renderer.axes_cleared >= 1, "source=renderer 的 figure 应该被 clf"
    assert art_renderer_fig.obj is None

    print("  ✓ MPL_FIGURE: source=user 保护有效")

    # 验证 source 校验
    try:
        artifact_manager.register_external_object(
            ArtifactKind.MPL_FIGURE, FakeFig(), source="invalid"
        )
        assert False, "source='invalid' 应该抛出 ValueError"
    except ValueError as e:
        print(f"  ✓ 非法 source 值被正确拒绝: {e}")

    # 验证 kind 校验
    try:
        artifact_manager.register_external_object(
            ArtifactKind.CACHE_ENTRY, "not-an-object", source="renderer"
        )
        assert False, "非 EXTERNAL_OBJECT kind 应该抛出 TypeError"
    except TypeError as e:
        print(f"  ✓ 非 EXTERNAL_OBJECT kind 被正确拒绝: {e}")

    print("  ✓ 全部 backend source 保护测试通过")


def test3_mirror_no_local_state():
    """mirror 类不继承 dict，没有本地存储，纯代理"""
    print()
    print("=" * 70)
    print("[3/3] Mirror 类无本地状态测试")
    print("-" * 70)

    # 清理
    artifact_manager.release_all(include_user_output=True)
    artifact_manager.cache_clear()

    from collections.abc import MutableMapping

    # 检查继承关系
    assert not issubclass(_PlotRegistryMirror, dict), (
        "_PlotRegistryMirror 不能继承 dict（会有第二份存储）"
    )
    assert issubclass(_PlotRegistryMirror, MutableMapping), (
        "_PlotRegistryMirror 应该是 MutableMapping"
    )
    print("  ✓ _PlotRegistryMirror 继承 MutableMapping，不继承 dict")

    assert not issubclass(_BboxCacheMirror, dict), (
        "_BboxCacheMirror 不能继承 dict（会有第二份存储）"
    )
    assert issubclass(_BboxCacheMirror, MutableMapping), (
        "_BboxCacheMirror 应该是 MutableMapping"
    )
    print("  ✓ _BboxCacheMirror 继承 MutableMapping，不继承 dict")

    # 检查实例没有 dict 存储
    plot_mirror = _PlotRegistryMirror()
    assert not hasattr(plot_mirror, "__dict__") or len(vars(plot_mirror)) == 0, (
        "_PlotRegistryMirror 实例不应有实例属性"
    )
    print("  ✓ _PlotRegistryMirror 实例无本地状态")

    bbox_mirror = _BboxCacheMirror()
    bbox_vars = vars(bbox_mirror)
    # 只允许有类级别的常量
    for k in bbox_vars.keys():
        if k not in ("_SENTINEL", "_CACHE_PREFIX"):
            assert False, f"_BboxCacheMirror 有意外的实例属性: {k}"
    print("  ✓ _BboxCacheMirror 实例无本地状态（只有类常量）")

    # 测试镜像操作确实同步到 artifact_manager
    class FakePlot:
        def cleanup(self): pass

    # Renderer._plots 同步
    fake = FakePlot()
    Renderer._plots["plot-1"] = fake
    assert artifact_manager.get_plot("plot-1") is fake
    assert "plot-1" in Renderer._plots
    assert Renderer._plots["plot-1"][0] is fake
    assert len(Renderer._plots) == 1
    assert list(Renderer._plots.keys()) == ["plot-1"]

    # 删除
    del Renderer._plots["plot-1"]
    assert artifact_manager.get_plot("plot-1") is None
    assert "plot-1" not in Renderer._plots
    assert len(Renderer._plots) == 0

    print("  ✓ _PlotRegistryMirror 操作完全同步到 artifact_manager")

    # MPLRenderer.drawn 同步
    bbox_val = (0.1, 0.2, 5.0, 4.0)
    MPLRenderer.drawn[1234] = bbox_val
    cached = artifact_manager.cache_get(("mpl_bbox", 1234))
    assert cached == bbox_val, f"cache 值不匹配: {cached}"
    assert 1234 in MPLRenderer.drawn
    assert MPLRenderer.drawn[1234] == bbox_val
    assert len(MPLRenderer.drawn) == 1
    assert list(MPLRenderer.drawn.keys()) == [1234]

    # get with default
    assert MPLRenderer.drawn.get(9999, "def") == "def"

    # pop
    popped = MPLRenderer.drawn.pop(1234)
    assert popped == bbox_val
    assert 1234 not in MPLRenderer.drawn
    assert artifact_manager.cache_get(("mpl_bbox", 1234)) is None

    print("  ✓ _BboxCacheMirror 操作完全同步到 artifact_manager cache")

    print("  ✓ 全部 Mirror 无本地状态测试通过")


def main():
    try:
        test1_user_output_only_deregister()
        test2_backend_source_protection()
        test3_mirror_no_local_state()
        print()
        print("=" * 70)
        print("✓ 全部 3 大项验证通过！")
        print("=" * 70)
        return 0
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ 意外错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
