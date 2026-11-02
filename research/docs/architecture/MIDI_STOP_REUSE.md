# 停止后的成对声部复用与主机适配

KROSS 2 v1.2.4 · PCM 列表、零页写入与软件移植 · 2026-11-02

硬停后，原声部的列表节点已清空，配对类别和伙伴指针仍在。再次申请时，原函数会重复摘除那个空节点，写到地址 `0x4` 和 `0x0`。未映射零页的私有环境因此停止；允许这两处写入后，原起音能继续，模拟页的前两条向量指令却被清零。

主机适配把“摘除已为空的节点”处理为空操作。24 组真实音色检查中，适配结果与允许零页写入的原指令在声部、链表、控制状态和 TG I/O 上一致。它提供了可移植的容器行为；实机零页映射仍待核对。[后续连续验证](MIDI_STOP_REUSE_LIVE.md)已接通原 96 条 MIDI/踏板轨迹。

![最小复现、零页边界与主机适配](figures/stop-reuse-boundaries.png)

## 1 失败条件已经缩小

最小流程为：选择原 Program，发音符 48，执行停止，再发音符 67。两次音符之间没有换音、踏板、调制、推进或轮询。六个真实预置覆盖 A000、A061、C001、F042、GM 钢琴和 GM 鼓组；分别使用模式 0/3 与力度 1/64/100/127。

| 原调用或对照 | 用例 | 重新申请触及未映射零页 |
| --- | ---: | ---: |
| 不停止 | 48 | 0 |
| CC123 普通释放 | 48 | 0 |
| CC120 强停 | 48 | 24 |
| `2732A0` 音色强停 | 48 | 24 |
| `1F67C4` OSC 消息 4 | 48 | 24 |
| `1FDC2C` 列表强停 | 48 | 24 |
| `1FD53C` 逐槽强停 | 48 | 24 |

共 336 组，120 组复现。五层强停的结果一致，已排除换音和普通 MIDI 值处理是必要触发条件。列表层按原调用传入首个声部节点，空头节点只表示列表结束。

原状态顺序为：

1. `1FD53C` 停止 TG，归还候选槽并移除成员节点。
2. 声部标志归零、成员节点前后指针归零；`+218` 的配对类别和 `+230` 的伙伴指针保留。
3. 再申请时，`1FC89C` 看到非零类别和伙伴，先调用 `1FC600`、`1FC738` 处理伙伴。
4. `272414` 按槽号定位成员节点，无条件执行 `next.prev=prev`、`prev.next=next`。当两链均为零，原写入地址依次为 `0x4`、`0x0`。

每次停止后都核对四条候选链的全部 32 个节点、前后对称关系、活动成员和空闲计数。这里的初始条件与失败位置均来自原指令；未补写链表或重置池来绕过失败。

## 2 零页实验改变了什么

两组独立探针保留原配对字段，只在私有模拟器映射可写的第零页，并用应用镜像前 4096 字节填充。A000 与 GM 钢琴均能完成再次起音，列表与计数仍一致；原指令在 `27242C/272430` 写入的零值改变了页首八字节，其他字节保持原值。

这解释了未映射夹具的直接阻断点。它没有证明实机使用同样的地址映射，也没有证明改写向量可接受。[早期向量检查](REPORT.md)中的低地址页同样属于模拟器输入。此项没有执行异常入口、整机启动或硬件测试。

## 3 主机侧的空节点规则

主机无需模拟向量页。研究适配保留原索引、有效链表写入次序及返回寄存器，仅处理这个空节点条件：

```text
node = nodes[index]
next = node.next
prev = node.prev
if next == 0 and prev == 0:
    return node
next.prev = prev
prev.next = next
return node
```

一侧为空、另一侧非空仍视为无效链表，检查会报错。适配没有在硬停后预先清除配对类别或伙伴指针。

A000、C001 与 GM 钢琴分别使用两模式、四力度，共 24 组。一侧执行完整原起音指令并允许私有零页写入；另一侧在零页未映射环境中使用这个摘除适配。两侧原声部构造、选样、分配、控制初始化和 TG 启动均继续执行。

比较范围沿用完整夹具：32 个声部、所有池与节点、六个 OSC、三个音色/Part/控制缓冲、16 通道、鼓键控制、相关工作区与 PRNG，以及 TG 读写顺序。24 组的全部受测状态和 I/O 一致，活动立体声两侧的伙伴引用保持对称。

复用检查另保留副侧 `+200` 的原值。原 `75D0` 分支复制主侧共享控制，不改写此字段；旧冷启动检查将它视为零，仅适用于当时的初始池。新检查核对字段保留、主侧增益、完整采样来源、共享控制和 TG 寄存器，未清零副侧数据。

另有六组因果探针，分别只清类别、只清伙伴或同时清两者；均能继续申请。其全部改动字节单列，未作为原固件行为或产品修复使用。主机适配的验证结果单独保存，避免把这两类实验混为一项。

## 4 先前通过的轨迹也有覆盖边界

[上一轮关音检查](MIDI_ALL_OFF.md)中，16 条 C001 → A061 轨迹完成了两次新起音。这仍不足以证明整个空闲池都可复用。

追加的两条原轨迹先复用槽 2、3。第三个音符 69 取得旧配对槽时，也触及空节点写入；两条都在该处停止。先前的成功没有覆盖到这次分配次序，旧结果及失败现场均保留。

当前已得到可用于软件音源的空节点适配及有界等价证据。后续已在[96 条持续轨迹](MIDI_STOP_REUSE_LIVE.md)中接回 MIDI、踏板、双 OSC 和正常刷新；耗尽抢占与更广组合、原应用零页映射、生命周期和实际声音仍未完成核对。产品代码和固件字节保持原值。

## 复现与证据

```text
python3 research/tools/firmware_stop_reuse.py --verify-arm
python3 research/tools/firmware_stop_reuse_figures.py
```

- [完整矩阵、零页写入与适配对照](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-check.json)
- [用例摘要 CSV](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-summary.csv)、[图形核验](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-figure-check.json)
- 原指令：[配对重置](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-pair-reset.arm.txt)、[硬停](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-hard-stop.arm.txt)、[成员移除](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-member-remove.arm.txt)、[摘除原语](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-node-unlink.arm.txt)、[副侧控制复制](../../derived/firmware/KROSS2_V124/architecture/stage04/stop-reuse-secondary-copy.arm.txt)
- [检查脚本](../../tools/firmware_stop_reuse.py)、[主机摘除适配](../../tools/firmware_stop_reuse_port.py)、[配图脚本](../../tools/firmware_stop_reuse_figures.py)
