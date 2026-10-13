JAGURS V0702 修复版：广田湾灾害链与 HPC 开发
======================================

开发分支：hpc/hirota-v0702-fixed
官方基底：JAGURS-D_V0702，f5c5e3f4d7a463f0092157d09db6622802e91cf2
官方发布：https://github.com/jagurs-admin/jagurs/releases/tag/JAGURS-D_V0702

本分支以官方 V0702 为基底，迁入此前广田湾实验使用的 8 文件科学计算修复，
同时保留 V0702 的上游修改，包括嵌套网格 MPI 异步通信缓冲区修复。
快速案例输入、参考结果及验收阈值仍冻结于此前通过的 V0701 实验。
这不是官方发布的修订版。原始 JAGURS 安装说明见 INSTALL，许可见 LICENSE。

迁移验收通过：完整 10861 s 海啸输出复现旧成功算例；重新转换的全部 15 项
漫滩输入相同；新 100 s sECOM 实跑的七项输出相同。完整 10440 s 漫滩未重跑，
其旧结果按输入等价和短程回归证据继续适用。16/32 MPI 快速回归也均通过，
本机整轮约 175/111 秒。详细范围与限制见下列迁移报告。

V0702 迁移内容与验证范围：V0702_MIGRATION.txt
跨平台开发交接（新平台先读）：HANDOFF_20261013_JAGURS.txt
快速案例、数据和使用步骤：benchmarks/hirota_quick/README.txt
正确性检查方法与结果判读：benchmarks/hirota_quick/CORRECTNESS_CHECK.txt
修改原因和适用范围：benchmarks/hirota_quick/CHANGES.txt
原始数据出处：benchmarks/hirota_quick/DATA_SOURCES.txt
V0701 历史实测报告：benchmarks/hirota_quick/results/
V0702 快速案例报告：benchmarks/hirota_quick/results_v0702/
V0702 长时段母场和下游接口验证：benchmarks/hirota_quick/v0702_validation/
V0702 嵌套 MPI 边缘验证：benchmarks/hirota_quick/v0702_mpi_edges/

V0702 最终验证状态以 V0702_MIGRATION.txt 和上述新报告为准，不能把旧 results/
中的 PASS 或耗时直接当作 V0702 的实测结论。

只需克隆本分支即可取得 JAGURS 快速案例输入和冻结参考值；快速案例不依赖
原实验目录，不需要 Git LFS。完整灾害链复跑仍需原机的 sECOM 和历史档案。
HPC 优化请在此分支上另建工作分支，保留冻结参考值、输入和验收阈值。
