# TJCZ-Map-Tool

>**总项目版本：** 1.0
   **总项目名称：** 图锦彩织（Tujincaizhi-自动化绘图工作流）
   **时间:**  2025-06-30 
   **项目开发人员：** 微星（ThinkyStar）
   **源项目：** Rail.Map.Toolkit（开源项目）
   **源项目开发作者：** thekingofcity
   **QGIS 版本：** Version 3.40.7（LTR Version）
   **许可证：MIT license **


欢迎你来到“图锦彩织”的世界！这是一个基于QGIS和Rail.Map.Toolkit项目的开源绘图项目~✨✨

### 🌟 项目简介

“图锦彩织”是一个利用 **QGIS** 和 **Python** 自动生成地铁风格地图的工具。它旨在帮助地图爱好者和设计师们，将地理数据快速转换为美观、清晰的地铁网络图。

**核心功能:**
- **数据输入:** 在 QGIS 中编辑地图数据（点和线）。
- **自动化生成:** Python 脚本将 QGIS 数据自动转换为 XML文档和JSON 格式文件，用以在'Rail.Map.Toolkit'上绘制地图。
- **详细教程:** 提供三份教程文档，手把手教你从环境配置到地图绘制。

### 🛠️ 快速开始

1.  **环境配置:**
    * 安装 **QGIS 3.40 LTR** 和 **Python 3.9.9+**。
    * **重要:** 按照 `docs/` 文件夹中的教程文档完成所有配置步骤。
2.  **修改脚本路径:**
    * 打开 `Auto_map_producer/run_my_qgis_export_V2b.py`。
    * 将 `log_file_path` 和 `script_dir` 两行代码中的路径，替换为你本地项目文件夹的**完整路径**。
3.  **绘制地图:**
    * 在 QGIS 中新建项目，保存到 `inbox/`。
    * 创建“点”图层，添加教程中指定的字段（如 `id`, `name`, `color` 等）。
    * 使用 QGIS 工具编辑你的站点和线路数据。
4.  **运行脚本:**
    * 在 QGIS 的 **Python 控制台**中运行 `run_my_qgis_export_V2b.py`。
    * 脚本将自动导出数据，并在 `json_output` 文件夹中生成最终的 JSON 地图文件。

### ❓ 常见问题

* **脚本报错?** 请检查脚本中的路径是否正确修改，并查看 `xml_output/xml_producer_logs/error_log.txt` 获取详细日志。
* **如何自定义?** 可修改 `config` 文件夹中的映射关系，或调整 Python 脚本中的常量来改变地图样式。

### 📞 联系方式

如果你有任何问题或建议，可以在 GitHub 仓库中提交 [Issues](https://github.com/ThinkyStar/TJCZ-Map-Tool/issues)。

---

**致谢:** 
感谢QGIS官方提供了开源的地图软件平台！
感谢天地图官方的地图插件！
特别感谢 **thekingofcity** 提供了宝贵的**Rail.Map.Toolkit**开源工具！
