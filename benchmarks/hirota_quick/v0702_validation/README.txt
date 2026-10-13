V0702 接入既有广田湾灾害链：完整轨迹与接口等价验证

2026-10-13 实测通过：完整母场耗时 1021.30 秒；42564 个 GRD 和
2482 条完整测点文件全部与原归档逐字节相同。真正重新转换生成的
15 项 sECOM 物理输入全部逐字节相同；新 100 秒 sECOM 实跑耗时
134.52 秒，七个物理输出也全部逐字节相同。

最终是否通过，以本目录 SUMMARY.json 的 passed 及逐项 gates 为准。
这里的“完整”指实际重新计算 JAGURS 的 10861 秒轨迹、重新生成完整
10 米漫滩初态和边界。sECOM 实际重跑 100 秒；原 10440 秒漫滩结果
通过相同物理输入、相同可执行文件以及短程逐字节回归建立等价依据。
不要把它表述成重新完成了 3.5 小时的 sECOM 全程积分。

检查范围

1. 原物理输入、原三层完整网格、2482 个原测点、546 个源文件均保留。
   原 case.json 曾遗留 4302 个测点的过期字段；实际 stations.txt、
   原输入合同和输出一直是 2482。此次仅在新元数据中纠正该字段。
2. SD03 四个 raw 场每种 10504 个文件：359.9、360.1 秒，以及
   360..10861 秒每一秒，检查文件集合、全部变量和有限值。
   另检查三层共 546 个滤波后源帧及实际输出的 SD03 zmax/vmax。
   总计 42564 个 GRD；完整逐文件 SHA 保存在压缩明细。
3. 2482 个测点全部原生时序：每站 108611 个样本，从 0.1 秒至
   10861.1 秒。逐值检查水位/东西通量/向南通量、时间步和有限值。
   双精度舍入诊断另有很严格的固定绝对限：水位 1e-9 米，两个
   通量 1e-8 平方米/秒。这不能替代下游输入必须完全一致的门槛。
4. 源时钟必须正好为 4914 条记录，即三网格各 1638 步、182 帧；
   按本次日志重建的沿岸双精度床深，逐数组对照历史值。
5. 从本次母场真正重做原 10 米转换，包括半时间步、南北符号、
   干湿支路、坐标和速度重构，生成全部 360..10801 秒边界。
   比较 9 个核心输入和 6 个辅助 NetCDF，共 15 项物理输入。
   辅助文件并非都不使用：原程序会读取初始温盐、扩散和气象等
   文件，因此也必须检查。全部 NetCDF 要求逐字节相同。
6. 核心 9 项原输入还核对历史 execution.json 中已冻结的 SHA。
   辅助 6 个 NetCDF 没有当年的冻结 SHA，本次与保留的历史文件
   对照，报告明确区分这两种证据。case.json 含新路径和审计信息，
   不作为 Fortran 求解器物理输入比较。
7. 使用原 v1b sECOM 可执行文件，32 个 OpenMP 线程，实际重跑
   100 秒。先确认新旧短例所有 15 输入相同，且原短例除时长外
   来自成功全长例，再比较七个物理输出文件的 SHA。
   明确记录本次动态库 SHA 和运行期间未变化；历史执行没有记录
   动态库 SHA，因此不宣称已证明历史库文件逐字节相同。

主要证据文件

  SUMMARY.json                             最终逐项判定与验证范围
  full_parent_input_contract.json          完整输入与 546 帧 SHA
  full_parent_tsun.par                     本次全长实际参数
  full_parent_gridfile.dat                 本次网格配置
  full_parent_execution_contract.json      本次命令、MPI 和数学库环境
  full_parent_execution.json               完整母场退出码和实测耗时
  full_parent_fields_comparison.json       全场、源时钟、双精度床深
  full_field_comparison.jsonl.gz           所有 GRD 的逐文件 SHA/差异
  full_parent_gauge_comparison.json        全部原生测点时序比较
  full_gauge_comparison.jsonl.gz           每个测点的 SHA/完整性/差异
  child_reconstruction.json                实际执行的转换脚本 SHA
  child_physical_input_comparison.json     15 项输入与历史完成证据
  child_100s_runtime_contract.json         本次 sECOM 环境及库 SHA
  child_100s_execution_and_comparison.json  新 100 秒执行与七输出比较

重跑这个完整审计需要本地完整历史灾害链档案，包含原 10 米地形、
转换器、v1b sECOM 和历史参考结果；这些大档案不在本 JAGURS Git 仓库。
原档案中保留的绝对路径也需要有效。仓库的日常 HPC 快速验证仍使用
上一级独立、可下载的 hirota_quick 数据与 run.py，不依赖此档案。

在仓库根目录使用带 NumPy、SciPy、netCDF4、pyproj 的 Python，先
加载已测试的 MPI 环境并构建 build/gnu/jagurs，然后分阶段执行：

  python benchmarks/hirota_quick/v0702_validation/full_chain.py prepare
  python benchmarks/hirota_quick/v0702_validation/full_chain.py run-parent
  python benchmarks/hirota_quick/v0702_validation/full_chain.py compare-fields
  python benchmarks/hirota_quick/v0702_validation/full_chain.py compare-gauges
  python benchmarks/hirota_quick/v0702_validation/full_chain.py rebuild-child
  python benchmarks/hirota_quick/v0702_validation/full_chain.py compare-child
  python benchmarks/hirota_quick/v0702_validation/full_chain.py run-short-child
  python benchmarks/hirota_quick/v0702_validation/full_chain.py summarize

各阶段可加 --archive 指定完整档案根目录。已经生成的运行目录不会
覆盖；新的完整复现应使用新的仓库工作副本。母场成功完成之后，
compare-fields、compare-gauges、rebuild-child 可以并行运行。
计算与大体积中间文件位于 runs/，压缩比较明细和小报告提交到 Git。

科学解释仍沿用原方案：公开 Yamazaki 震源/Okada 规定形变输入，
没有重新启用 CGFDM；10 米 I 类 61 点原项目目标通过，20 米没有全部
通过。震源独立性、干前沿收敛、固定床地貌及 59 个 R 类点的限制
没有因为软件迁移而消失。历史观测分数沿用有证据的等价结果，
不是本次重新积分 10440 秒并重新评分获得的新观测验收。
