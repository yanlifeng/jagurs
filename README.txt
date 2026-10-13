JAGURS V0701 修复版：广田湾 HPC 开发基线
======================================

开发分支：hpc/hirota-v0701-fixed
官方基底：JAGURS-D_V0701，9934f8970f545deda2cdf4f1bc18f763e191b3cd
官方发布：https://github.com/jagurs-admin/jagurs/releases/tag/JAGURS-D_V0701

本分支保留此前广田湾实验使用的 8 个 Fortran 文件修复，增加可随优化反复运行的
真实案例快速回归。源码修复提交 24bc4dc 的父提交就是官方 V0701。
这不是官方发布的修订版。原始 JAGURS 安装说明见 INSTALL，许可见 LICENSE。

快速案例、数据和使用步骤：benchmarks/hirota_quick/README.txt
修改原因和适用范围：benchmarks/hirota_quick/CHANGES.txt
原始数据出处：benchmarks/hirota_quick/DATA_SOURCES.txt
本机实测报告：benchmarks/hirota_quick/results/

只需克隆本分支即可取得输入和冻结参考值；不依赖原实验目录，不需要 Git LFS。
HPC 优化请在此分支上另建工作分支，保留冻结参考值、输入和验收阈值。
