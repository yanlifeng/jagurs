广田湾 JAGURS 快速 HPC 回归
==========================

适用分支：hpc/hirota-v0702-fixed；基底为官方 JAGURS-D_V0702 加上本项目科学修复。
输入、参考结果和验收阈值继续使用冻结的 V0701 历史基线，没有用 V0702 重生成。
完整的正确性检查方法、固定容差和失败排查见同目录 CORRECTNESS_CHECK.txt。
升级的长时段母场及下游验证见仓库根目录 V0702_MIGRATION.txt。

目标：每次优化后，在真实广田湾计算负载上检查数值是否改变，并记录耗时。
默认 16 个 MPI 进程、4x4 分块、每进程 1 个 OpenMP 线程。
一次 run 命令包括输入核验、1800 秒真实案例、结果核验和独立解析波检查。
验收要求是数值通过，并且上述全部步骤实测总耗时小于 300 秒。
首次下载、编译和解包是一次性准备成本，单独记录，不包含在每次回归预算内。
5 分钟是本案例的验收目标；各版本、处理器和文件系统都要实测，不能直接保证。

保留了哪些真实工作量
--------------------
输入是之前跑通的广田湾父算例原始字节。只把 tend 从 10861 s 截到 1800 s，
以及把最后地图输出步相应截短；网格、地形、182 帧震源、dt、物理参数都保持。

网格     Nx x Ny       分辨率    局部时间步
SD01     761 x 801     27角秒     0.9 s
SD02     325 x 265      9角秒     0.3 s
SD03     517 x 445      3角秒     0.1 s

三层均为非线性；3 倍空间和时间嵌套；一向嵌套；Coriolis 开；吸收边界 20 格；
Kajiura 开；移动海底开；Manning 海洋 .025 / 陆地 .035；with_disp=0；
内部 REAL_DBLE 双精度，原生 GRD 输出单精度。
原 2482 个测点仍按 0.1 s 输出。SD03 从 360 s 起按 1 s 输出水位/速度/原生通量
等地图，也保留旧耦合所需的 359.9/360.1 s 两帧额外输出。

该例覆盖施源、传播、动量/连续方程、嵌套插值、干湿处理、MPI 边界交换、归约和
真实输出开销。完整网格及分块保留沿海/陆地引起的计算不均衡；缩短时间窗会让
施源阶段的耗时占比增大。比较 profile.json 的所有进程，而不只看 rank 0。
不要把父级 tstep 计时和其内部核函数重复相加；也不能相加不同区段的进程最大值。

历史参考在 1800 s 已有 877 个原始陆地节点变湿，SD03 最大瞬时 eta 约 18.19 m；仍处于
首波进入海岸阶段。完整洪峰及后续退水必须用长时段案例回归。它适合日常 HPC
开发，不替代完整历史观测拟合、10 m 下游漫滩或所有可选物理模块的验收。
with_disp=0，因此色散/Jacobi 不是此例热点，也未被这次测试验证。

第一次准备
----------
需要 Python 3.9 或更新版本、NumPy、netCDF4；GNU Fortran/C、GNU Make、MPI；NetCDF C/Fortran、
PROJ 和 FFTW 开发库。普通 GNU MPI + FFTW 构建没有特定 x86 指令集参数。
先载入平台上的编译器、MPI 和库模块；下面命令均在仓库根目录执行。

  git clone --branch hpc/hirota-v0702-fixed --single-branch git@github.com:yanlifeng/jagurs.git
  cd jagurs
  python3 -m pip install -r benchmarks/requirements.txt

通用 GNU MPI 构建（适用于安装在 /usr 的现代 PROJ 9；其他位置用相应参数指定）：

  python3 benchmarks/build_gnu.py --proj9

自定义库前缀示例：

  python3 benchmarks/build_gnu.py --fc mpif90 --netcdf /opt/netcdf --proj /opt/proj --fftw /opt/fftw --proj9

旧 PROJ 使用 proj_api.h 时省略 --proj9。动态库若不在默认搜索路径，需要先由
平台模块或 LD_LIBRARY_PATH 配置。MPI wrapper 必须使用 GNU Fortran；其他 Fortran
编译器应另写匹配的构建配置并执行相同数值回归。--dry-run 可先检查依赖和命令。
编译日志/编译器/参数/源码及可执行文件哈希保存在 build/gnu/。
通用 FFTW/ARM 路径需要在目标平台实测；这里的计时来自下述本机配置。

本机现有依赖的复现命令（--local 只适用于原开发机，不是可移植配置）：

  source /opt/intel/oneapi/mpi/2021.12/env/vars.sh
  /home/user_home/ylf/disaster-chain-secom-20260928/py/bin/python benchmarks/build_gnu.py --local

一次性解包（各平台相同）：

  python3 benchmarks/hirota_quick/run.py prepare

数据包已经提交，使用普通 Git，不使用 LFS；无需重新下载 DEM 或重新求解 Okada。
解包逐帧验证 SHA-256，得到 build/hirota_inputs 中普通 GRD 输入。
每次 run 都会重新核对输入、时钟、物理参数和冻结参考数据，防止优化时误换案例。

每次开发验证
------------
分配至少 16 个物理核，再执行；输出目录每次必须换一个新名字：

  python3 benchmarks/hirota_quick/run.py run --output runs/check01

本机已测 Intel MPI 16 核命令：

  source /opt/intel/oneapi/mpi/2021.12/env/vars.sh
  I_MPI_FABRICS=shm:tcp I_MPI_PIN_PROCESSOR_LIST=0-15 /home/user_home/ylf/disaster-chain-secom-20260928/py/bin/python benchmarks/hirota_quick/run.py run --output runs/check01 --cores 0-15

OpenMPI 可显式绑定，如：

  python3 benchmarks/hirota_quick/run.py run --output runs/check01 --mpi-args="--bind-to core --map-by core"

遵守目标机器的调度分配。--cores 只是 Linux taskset 限定可用核，具体 MPI 绑定
仍按 MPI 实现设置；不要照抄本机 Intel 专用环境变量到其他 MPI。
--exe 可指定优化后的可执行文件。所有版本都先保持相同进程布局、精度和 I/O
方式再比较速度。32 进程分解对照可用 --ranks 32 --procx 8 --procy 4。
一次运行输出约十余 GB，建议预留 20 GB；旧结果由用户按需清理。

输出与退出码
------------
report.json：总耗时、MPI 耗时、解析波结果、数值及 5 分钟是否通过。
verification.json：48 个测点和全 SD03 最终场的逐项误差、坐标、干湿检查。
profile.json：所有进程的原生详细计时器，以及与旧完整算例分布的比较。
mpi_run.json：命令、进程数、线程数、固定的数学库线程策略、可执行文件哈希。
launcher.log / stdout.000000 等：原生运行日志，排查失败时先看这些文件。

退出码 0：数值通过、全部 MPI 进程详细计时完整且小于 300 s。
退出码 2：数值回归失败或计时资料不完整；3：数值和计时通过但超过 300 s。
数值、计时完整性和速度分别看 numerical_correctness_passed、profile_complete、
within_5_minutes。使用自定义构建时保留 TIMER=DETAIL。
输入损坏、运行错误等抛出异常并返回非零，report.json 记录错误。
需要单独重查现有结果时可运行：

  python3 benchmarks/hirota_quick/run.py verify --output runs/check01
  python3 benchmarks/hirota_quick/run.py profile --output runs/check01

校验器本身的负向测试（另计时间，仅开发校验工具时需要）：

  python3 benchmarks/hirota_quick/check_verifier.py --output runs/check01 --report runs/negative_checks.json

它在临时私有副本里注入水位 +1 m、流量反号、缺失 0.2 s 样本、改变摩擦系数，
四类错误都必须被拒绝。不会改写已完成的正常算例。

正确性是怎么查的
----------------
1. 真实例的参考值直接摘自此前 10861 s 完整计算的前缀，不是本次构建自跑自认。
   11 个海上中心站 + 按地理位置固定选出的 37 个岸边站，比较 t=1..1800 s 的
   eta/qx/qy；同时要求 0.1 s 原生记录连续。SD03 1800 s 的四个原生场比较全部
   230065 个节点，并核对坐标、尺寸及步长，拒绝缺失、NaN 和无穷值。
   单点误差上限：eta/depth 为 2e-5 m + 1e-6*abs(reference)，
   qx/qy 为 1e-4 m^2/s + 1e-6*abs(reference)。这些是优化回归阈值，不是观测
   误差允许到这个量级的声明。水柱阈值附近节点单独报告，稳定干湿节点必须一致。
2. 另跑约几秒的平底解析驻波：H=4000 m，波长40 km，dx=500 m，dt=.25 s，
   振幅 .01 m；独立计算离散浅水波色散关系及固定的跃蛙半步初始相位。
   相对 L2 < 1e-4 且最大水位误差 < 1e-6 m，不能拟合振幅或挪动相位以求通过。
   这是基础传播的独立检查；本身不代表真实地形计算负载。

性能报告与解释
--------------
V0702 新实测结果见 results_v0702/；results/ 下 JSON、SUMMARY.txt 和图片保留
V0701 历史成绩，不是新版本的实测证明。建议优先分析 fxynl_rwg、
hxy/干湿处理、MPI halo、嵌套插值、全域输出及各进程等待。先复现当前结果，再
逐项优化；不要用减少测点、降低精度、改变震源或物理开关冒充同一例的加速。
针对纯算力也可另设少 I/O 性能实验，但需要额外标识，不能与此冻结案例混为一谈。

results/kernel_profile.png 和 PDF 表示 V0701 历史计时。若要从当前运行重画，
需要额外安装 matplotlib：

  python3 benchmarks/hirota_quick/plot_profile.py --profile runs/check01/profile.json --output runs/kernel_profile.png
