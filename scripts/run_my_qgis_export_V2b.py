import sys
import os
import importlib
import logging
from datetime import datetime
from pathlib import Path # 确保导入Path，用于处理文件路径

# --- 日志配置 ---
# 定义日志文件的名称
log_file_name = "error_log.txt"
# 构建日志文件的完整路径。请确保 'D:/map_maker/xml_output/xml_producer_logs' 文件夹已经存在。
# 如果您的项目脚本是放在'map_generator'这个文件夹，请将路径改为'D:/map_generator/xml_output/xml_producer_logs'文件夹，或你实际所定的输出路径
# 如果该文件夹不存在，脚本将无法写入日志文件并可能报错。
log_file_path = os.path.join("D:/map_maker/xml_output/xml_producer_logs", log_file_name)

# 配置日志系统
logging.basicConfig(
    level=logging.ERROR,  # 设置日志级别为 ERROR，这意味着只记录 ERROR 及以上级别的消息。
    format='%(asctime)s - %(levelname)s - %(message)s',  # 定义日志消息的格式。
    datefmt='%Y-%m-%d %H:%M:%S',  # 定义时间戳的格式。
    filename=log_file_path,  # 指定日志文件路径。
    filemode='a',  # 设置文件模式为追加 (append)，每次运行都会在文件末尾添加新的日志。
    encoding='utf-8'  # 设置文件编码为 UTF-8，以支持各种字符。
)
# 获取一个日志器实例
logger = logging.getLogger(__name__)

# 同时配置日志输出到控制台，方便实时查看
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)  # 控制台输出 INFO 级别及以上的日志，便于调试和查看运行信息。
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.info("--- 脚本开始运行 ---")

# --- 脚本文件路径配置 ---
# 指定 qgis_xml_producer_V2a.py 文件所在的目录。
# 这是一个非常重要的路径，如果错误，Python 将找不到要导入的模块。
# 请务必将此路径替换为您的 qgis_xml_producer_V2a.py 文件的实际存放位置。
script_dir = 'C:/Users/yourname/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/'
# 该文件夹是QGIS的python代码脚本实际存储文件夹，你可以根据你的实际配置进行修改。
# 请将'yourname'改为你的实际用户名。


# 将脚本目录添加到 Python 的模块搜索路径中。
# 这样 Python 解释器在查找模块时就能找到 qgis_xml_producer_V2a。
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)  # 将路径插入到列表的开头，确保优先搜索。
    logger.info(f"✅ 已将脚本目录添加到sys.path: {script_dir}")
else:
    logger.info(f"ℹ️ 脚本目录已在sys.path中: {script_dir}")

# 模块名称与 qgis_xml_producer_V2a.py 文件名一致
MODULE_NAME = 'qgis_xml_producer_V2a' 

logger.info(f"--- 准备导入 {MODULE_NAME} 模块 ---")

try:
    # 尝试导入 qgis_xml_producer_V2a 模块。
    # 如果模块已经被导入过（例如，在 QGIS 会话中多次运行），
    # importlib.reload() 会重新加载模块，确保最新的修改生效。
    if MODULE_NAME in sys.modules:
        importlib.reload(sys.modules[MODULE_NAME])
        logger.info(f"✅ 模块 '{MODULE_NAME}' 已重新加载。")
    else:
        globals()[MODULE_NAME] = importlib.import_module(MODULE_NAME)
        logger.info(f"✅ 模块 '{MODULE_NAME}' 已首次导入。")
except ImportError as ie:
    # 捕获导入错误，例如文件不存在或路径错误。
    logger.error(f"❌ 错误: 导入模块失败。请检查文件是否存在且路径是否正确。错误信息: {ie}")
    logger.exception("导入模块时的完整错误堆栈:")  # 记录完整的错误堆栈信息，便于调试。
    sys.exit(1)  # 脚本退出，并返回状态码 1 表示出错。
except Exception as e:
    # 捕获其他未知错误。
    logger.error(f"❌ 错误: 重新加载/导入模块时发生未知错误。错误信息: {e}")
    logger.exception("重新加载/导入模块时的完整错误堆栈:")
    sys.exit(1)

# 获取导入的模块对象，以便后续调用其函数
qgis_xml_producer_module = sys.modules[MODULE_NAME]


# --- 导出参数配置 ---
# 定义输出 XML 文件的目标目录。
# 请确保您对该路径有写入权限！
output_dir = 'D:/map_maker/xml_output/'
# 如果您的项目脚本是放在'map_generator'这个文件夹，请将路径改为'D:/map_generator/xml_output/'文件夹，或你实际所定的输出路径

# 【新增功能】动态获取 QGIS 项目名称并用于命名输出文件
project_name = "exported_stations_data_all_layers" # 默认输出文件名，以防获取项目名失败

try:
    # 导入 QgsProject 类，用于访问 QGIS 项目中的图层。
    from qgis.core import QgsProject # 确保 QgsProject 在这里被导入

    # 获取当前 QGIS 项目的实例。
    project = QgsProject.instance()
    # 获取当前 QGIS 项目文件的完整路径。
    project_file_path = project.fileName()

    if not project_file_path:
        # 如果项目未保存，或者是一个新的、未命名的项目
        logger.warning("⚠️ 警告: QGIS 项目未保存或未命名。输出文件将使用默认名称。")
        # 此时 project_name 保持为默认值 "exported_stations_data_all_layers"
    else:
        # 从完整路径中提取文件名（不带扩展名），这将作为 XML 文件的新名称。
        project_name = Path(project_file_path).stem # .stem 获取不带扩展名的文件名
        logger.info(f"✅ 获取到 QGIS 项目名称: '{project_name}'，将用于命名输出文件。")

    # 构建最终的输出 XML 文件路径。
    output_file = os.path.join(output_dir, f"{project_name}.xml")

except Exception as e:
    logger.error(f"❌ 错误: 获取 QGIS 项目名称失败。将使用默认输出文件名。错误信息: {e}")
    # 发生错误时，回退到使用硬编码的默认文件名
    output_file = os.path.join(output_dir, "exported_stations_data_all_layers.xml")


# 设置要包含的 'transfer_line_X' 列的数量。
# 根据 XML 模板 (FIRM_XML_3.xml) 的要求，建议设置为 6，以匹配固定的列结构。
num_transfer_lines = 6

logger.info(f"\n--- 尝试运行导出函数 ---")
logger.info(f"    输出文件路径: {output_file}")
logger.info(f"    换乘线数量: {num_transfer_lines}")

try:
    # 导入 QgsVectorLayer, QgsWkbTypes (如果之前没有导入的话)
    from qgis.core import QgsVectorLayer, QgsWkbTypes # 确保这些类在这里被导入

    # 获取所有图层的名称。
    # mapLayers() 方法返回一个字典，其键是图层ID，值是图层对象。
    all_qgis_layers = project.mapLayers().values()

    # 创建一个空列表，用于存储所有符合条件的点/多点图层的名称。
    point_layers_to_export = []

    # 遍历所有 QGIS 图层，筛选出点或多点矢量图层。
    logger.info("正在检测 QGIS 项目中的图层...")
    for layer in all_qgis_layers:
        # 检查图层是否是矢量图层。
        if isinstance(layer, QgsVectorLayer):
            layer_wkb_type = layer.wkbType()
            # 检查图层几何类型是否是点 (Point) 或多点 (MultiPoint)。
            if layer_wkb_type in [QgsWkbTypes.Point, QgsWkbTypes.MultiPoint]:
                point_layers_to_export.append(layer.name()) # 将符合条件的图层名称添加到列表中。
                logger.info(f"    ✓ 发现并添加点/多点图层: '{layer.name()}'")
            else:
                logger.info(f"    - 跳过图层 '{layer.name()}' (几何类型: {QgsWkbTypes.displayString(int(layer_wkb_type))})，非点/多点图层。")
        else:
            logger.info(f"    - 跳过图层 '{layer.name()}'，不是矢量图层。")

    # 检查是否找到了任何点/多点图层。
    if not point_layers_to_export:
        logger.warning("⚠️ 警告: 在 QGIS 项目中未找到任何点或多点矢量图层可供导出。请确保您的项目包含此类图层。")
    else:
        logger.info(f"⭐ 将要导出以下图层: {point_layers_to_export}")
        # 调用 qgis_xml_producer_V2a 模块中的主导出函数。
        # 将检测到的所有点图层列表作为第一个参数传递。
        qgis_xml_producer_module.process_and_export_qgis_layers_to_xml(
            point_layers_to_export,
            output_file,
            num_transfer_lines=num_transfer_lines
        )
        logger.info("\n--- 导出脚本运行成功！请检查输出文件 ---")

except Exception as e:
    # 捕获在导出过程中可能发生的任何错误。
    logger.error("\n--- 导出脚本运行失败！ ---")
    logger.error(f"❌ 发生错误: {e}")
    logger.exception("导出函数运行时的完整错误堆栈:")
    logger.error("--------------------------")

logger.info("\n--- 脚本运行结束 ---")
