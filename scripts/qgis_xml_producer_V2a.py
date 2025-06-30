import os
import uuid
import re
import random
import hashlib # 用于生成SHA256哈希值
# import base64  # 已移除，因为自定义Base62不再需要
from datetime import datetime
from qgis.core import QgsVectorLayer, QgsFeature, QgsField, QgsProject, QgsPointXY, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsWkbTypes
from qgis.PyQt.QtCore import QVariant
from xml.etree.ElementTree import Element, SubElement, tostring

# --- 辅助函数：生成随机ID（保留，但现在仅用于非坐标生成场景） ---
def generate_random_id(length=9):
    """
    生成一个指定长度的随机ID，包含数字和大小写字母。
    该函数现在主要作为备用或用于其他非坐标关联的ID生成场景。
    """
    characters = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return ''.join(random.choice(characters) for i in range(length))

# --- 自定义 Base62 编码的辅助函数 ---
# Base62编码的字符集：0-9, A-Z, a-z
BASE62_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

def base_encode(number, base_chars):
    """
    将一个整数编码为指定字符集的字符串。
    用于将大整数（如哈希值）转换为更短的字符串形式。

    参数:
        number (int): 要编码的整数。
        base_chars (str): 用于编码的字符集字符串（例如 BASE62_CHARS）。

    返回:
        str: 编码后的字符串。
    """
    if number == 0:
        return base_chars[0]
    base = len(base_chars)
    encoded_string = []
    while number > 0:
        encoded_string.append(base_chars[number % base])
        number //= base
    return "".join(reversed(encoded_string))


# --- 修改后的函数：生成基于坐标的短且稳定的ID (9位) ---
def generate_stable_id_from_coords(x, y, target_length=9):
    """
    根据给定的 (x, y) 坐标生成一个稳定、确定性且长度为 9 位的短 ID。
    此函数通过以下步骤实现：
    1. 将坐标组合成一个字符串。
    2. 计算该字符串的 SHA256 哈希值。
    3. 将哈希值转换为一个大整数。
    4. 将该整数编码为 Base62 字符串。
    5. 截取 Base62 字符串的前 target_length (默认为9) 位作为最终ID。

    参数:
        x (float): 坐标的 X 值 (经度)。
        y (float): 坐标的 Y 值 (纬度)。
        target_length (int): 目标 ID 的长度 (默认为 9)。

    返回:
        str: 基于坐标生成的稳定且指定长度的短 ID 字符串。
    """
    # 1. 将 x, y 坐标组合成一个字符串。
    # 确保坐标精度一致，防止浮点数精度问题导致哈希不一致。
    # 例如，保留 6 位小数，这对于地理坐标通常足够精确，并确保相同物理位置的哈希值相同。
    coord_string = f"{x:.6f},{y:.6f}"

    # 2. 计算该字符串的 SHA256 哈希值。
    # SHA256 是一种安全的哈希算法，提供良好的唯一性保证。
    # `digest()` 返回字节串，`hexdigest()` 返回十六进制字符串。
    sha256_hash = hashlib.sha256(coord_string.encode('utf-8')).hexdigest()

    # 3. 将十六进制哈希值转换为一个大整数。
    # 这样可以将其视为一个数字，用于 Base62 编码。
    hash_as_int = int(sha256_hash, 16)

    # 4. 将该整数编码为 Base62 字符串。
    # Base62 编码比十六进制更紧凑，能用更短的字符串表示相同的信息量。
    base62_encoded = base_encode(hash_as_int, BASE62_CHARS)

    # 5. 截取 Base62 字符串的前 target_length 位作为最终ID。
    # 由于 Base62 编码的结果通常很长，我们只取其前 N 位。
    # 注意：截取会增加理论上的碰撞风险，但对于有限数量的站点，实践中极低。
    final_id = base62_encoded[:target_length]

    # 如果截取后的长度不足 target_length，理论上这种情况很少发生，
    # 但为确保长度，可以进行填充（如果需要）。但对于SHA256哈希，Base62编码结果很长，
    # 不太可能出现不足9位的情况。这里不做额外填充，如果真不足9位，就保持原样。
    return final_id


def _try_int(s):
    """
    尝试将字符串转换为整数，如果失败，则尝试匹配特定格式的字符串（例如“L1_01”），
    否则返回原始字符串。用于排序。
    关键修改：确保始终返回一个元组，以避免排序时出现TypeError。
    """
    try:
        # 如果能转换为整数，则返回包含该整数的元组
        return (int(s),)
    except ValueError:
        # 尝试匹配 "前缀数字_数字" 的格式 (例如 L1_01)
        match = re.match(r'([A-Za-z]+)(\d+)_(\d+)', s)
        if match:
            prefix, line_num, station_num = match.groups()
            # 返回一个包含字符串前缀和两个整数的元组
            return (prefix, int(line_num), int(station_num))
        # 尝试匹配 "数字_数字" 的格式 (例如 1_01)
        match = re.match(r'(\d+)_(\d+)', s)
        if match:
            line_num, station_num = match.groups()
            # 返回一个包含两个整数的元组
            return (int(line_num), int(station_num))
        # 如果以上都不匹配，则返回包含原始字符串的元组
        # 这样确保了在所有情况下，_try_int 都返回一个元组，避免 TypeError
        return (s,)

def process_and_export_qgis_layers_to_xml(layer_names, output_filepath, num_transfer_lines=6):
    """
    处理指定的 QGIS 矢量图层中的点要素，将其转换为特定的 XML 格式并导出。

    参数:
        layer_names (list): 包含要处理的 QGIS 图层名称的列表。
        output_filepath (str): 导出 XML 文件的完整路径和文件名。
        num_transfer_lines (int): 要处理的换乘线字段（t_lineX）的数量。
                                  这会影响 XML 中 transfer_line_X 列的生成。
    """
    # 获取 QGIS 项目实例
    project = QgsProject.instance()
    # 定义目标坐标系为 WGS84 (EPSG:4326)，即经纬度。所有导出的坐标都将转换为此坐标系。
    target_crs = QgsCoordinateReferenceSystem("EPSG:4326")

    # 定义 QGIS 字段名到 XML 表头名的映射。
    # 这是一个字典，键是 QGIS 图层中的字段名，值是 XML 中对应的表头名。
    qgis_field_to_xml_header_map = {
        'FHM_No': 'Firm_Highway_Number', # 'FHM_No' 在 QGIS 中，对应 XML 的 'Firm_Highway_Number'
    }
    # 动态添加 num_transfer_lines 数量的换乘线字段到映射中。
    # 例如，如果 num_transfer_lines=6，会添加 't_line1' -> 'transfer_line_1'，直到 't_line6' -> 'transfer_line_6'。
    for i in range(1, num_transfer_lines + 1):
        qgis_short_name = f"t_line{i}"
        xml_long_name = f"transfer_line_{i}"
        # 检查是否已存在，防止重复添加（虽然这里不会，但良好习惯）
        if qgis_short_name not in qgis_field_to_xml_header_map:
             qgis_field_to_xml_header_map[qgis_short_name] = xml_long_name

    # 初始化一个空列表，用于存储所有图层中处理后的点数据。
    # 每个点的数据是一个字典，包含了 XML 导出的所有必要信息。
    all_processed_points_for_final_export = []

    # 遍历传入的每个图层名称。
    for layer_name in layer_names:
        # 通过名称从 QGIS 项目中获取图层列表。
        layer_list = project.mapLayersByName(layer_name)
        if not layer_list:
            # 如果未找到图层，打印错误信息并跳过当前图层。
            print(f"错误: 未找到 QGIS 图层: '{layer_name}'。跳过此图层。")
            continue
        # 获取找到的第一个图层对象。
        layer = layer_list[0]

        # 检查获取到的对象是否确实是矢量图层。
        if not isinstance(layer, QgsVectorLayer):
            print(f"错误: 图层 '{layer_name}' 不是矢量图层。跳过此图层。")
            continue

        # 获取图层的几何类型（例如，点、线、面）。
        layer_wkb_type = layer.wkbType()
        # 检查几何类型是否为点 (Point) 或多点 (MultiPoint)。
        # 只有这两种类型支持导出为单个点数据。
        if layer_wkb_type not in [QgsWkbTypes.Point, QgsWkbTypes.MultiPoint]:
            print(f"错误: 图层 '{layer_name}' 的几何类型 '{QgsWkbTypes.displayString(int(layer_wkb_type))}' 不受支持。只支持Point和MultiPoint。跳过此图层。")
            continue

        # 获取当前图层的原始坐标系。
        source_crs = layer.crs()
        # 创建一个坐标转换对象，用于将图层原始坐标系转换为目标坐标系 (WGS84)。
        transform = QgsCoordinateTransform(source_crs, target_crs, project)

        # 存储当前图层所有要素的原始属性和几何。
        current_layer_features_raw_data = []
        # 用于存储当前图层检测到的第一个非空有效线路名称。
        first_valid_line_name_in_layer = None
        # 用于存储当前图层检测到的第一个非空有效 FHM_No 值。
        first_valid_fhm_no_in_layer = None
        # 【新增变量】用于存储当前图层检测到的第一个非空有效 direction 值。
        first_valid_direction_in_layer = None
        # 【新增变量】用于存储当前图层检测到的第一个非空有效 color 值。
        first_valid_color_in_layer = None

        # --- 第一次遍历：收集所有要素的原始数据，并尝试找到有效的线路名称、FHM_No、direction 和 color ---
        # 这一步是为了在处理具体点数据之前，先确定整个图层可能使用的默认值。
        for feature in layer.getFeatures(): # 遍历图层中的每一个要素
            attrs = feature.attributes() # 获取要素的所有属性值
            # 将属性名和属性值组合成一个字典，方便按名称访问。
            feature_data_raw = {layer.fields().at(i).name(): attrs[i] for i in range(len(attrs))}

            # 寻找第一个非空且非空白的 'name' 值。
            # 如果要素的 'name' 字段有值，就用它作为该图层的默认线路名称。
            name_value_check = str(feature_data_raw.get('name', '') or '').strip()
            if name_value_check and first_valid_line_name_in_layer is None:
                first_valid_line_name_in_layer = name_value_check

            # 寻找第一个非空且非空白的 'FHM_No' 值。
            # 如果要素的 'FHM_No' 字段有值，就用它作为该图层的默认 FHM_No。
            fhm_no_value_check = str(feature_data_raw.get('FHM_No', '') or '').strip()
            if fhm_no_value_check and first_valid_fhm_no_in_layer is None:
                first_valid_fhm_no_in_layer = fhm_no_value_check

            # 【新增逻辑】寻找第一个非空且非空白的 'direction' 值。
            direction_value_check = str(feature_data_raw.get('direction', '') or '').strip()
            if direction_value_check and first_valid_direction_in_layer is None:
                first_valid_direction_in_layer = direction_value_check

            # 【新增逻辑】寻找第一个非空且非空白的 'color' 值。
            color_value_check = str(feature_data_raw.get('color', '') or '').strip()
            if color_value_check and first_valid_color_in_layer is None:
                first_valid_color_in_layer = color_value_check

            geom = feature.geometry() # 获取要素的几何信息
            # 将要素本身、其原始属性字典和几何对象存储起来。
            current_layer_features_raw_data.append((feature, feature_data_raw, geom))


        # 检查是否找到了有效的线路名称。如果没有，则警告并跳过此图层。
        if first_valid_line_name_in_layer is None:
            print(f"警告: 图层 '{layer_name}' 中所有要素的 'name' 字段都为空或只包含空白字符。此图层将不会导出任何要素。")
            continue # 跳过整个图层的处理和导出

        else:
            print(f"信息: 图层 '{layer_name}' 找到线路名称: '{first_valid_line_name_in_layer}'。所有未填写 'name' 字段的要素将使用此值。")

        # 检查是否找到了有效的 FHM_No。如果没有，则警告。
        if first_valid_fhm_no_in_layer is None:
            print(f"警告: 图层 '{layer_name}' 中所有要素的 'FHM_No' 字段都为空或只包含空白字符。此图层所有要素的 'Firm_Highway_Number' 将为空。")
        else:
            print(f"信息: 图层 '{layer_name}' 找到 'FHM_No': '{first_valid_fhm_no_in_layer}'。所有未填写 'FHM_No' 字段的要素将使用此值。")

        # 【新增逻辑】检查是否找到了有效的 direction。
        if first_valid_direction_in_layer is None:
            print(f"警告: 图层 '{layer_name}' 中所有要素的 'direction' 字段都为空或只包含空白字符。此图层所有要素的 'direction' 将为空。")
        else:
            print(f"信息: 图层 '{layer_name}' 找到 'direction': '{first_valid_direction_in_layer}'。所有未填写 'direction' 字段的要素将使用此值。")

        # 【新增逻辑】检查是否找到了有效的 color。
        if first_valid_color_in_layer is None:
            print(f"警告: 图层 '{layer_name}' 中所有要素的 'color' 字段都为空或只包含空白字符。此图层所有要素的 'color' 将为空。")
        else:
            print(f"信息: 图层 '{layer_name}' 找到 'color': '{first_valid_color_in_layer}'。所有未填写 'color' 字段的要素将使用此值。")


        # --- 第二遍遍历：处理数据，并应用找到的线路名称、FHM_No、direction、color，并生成ID ---
        current_layer_features_processed = [] # 存储当前图层处理后的点数据

        for feature, feature_data_raw, geom in current_layer_features_raw_data:
            # 检查几何是否为空或无效。
            if not geom or geom.isEmpty():
                print(f"警告: 要素 {feature.id()} 几何为空或无效。跳过其点位导出。")
                continue # 跳过几何为空的要素，因为无法提取坐标

            points_in_feature = [] # 用于存储当前要素中的所有点（对于多点要素）
            if geom.wkbType() == QgsWkbTypes.Point:
                # 如果是点几何，直接添加其坐标。
                points_in_feature.append(geom.asPoint())
            elif geom.wkbType() == QgsWkbTypes.MultiPoint:
                # 如果是多点几何，遍历并添加所有子点坐标。
                multi_points = geom.asMultiPoint()
                if multi_points:
                    for pt in multi_points:
                        points_in_feature.append(pt)
                else:
                    print(f"警告: MultiPoint 要素 {feature.id()} 不包含任何子点。跳过。")
                    continue
            else:
                # 不支持的几何类型，跳过。
                print(f"警告: 要素 {feature.id()} 的几何类型 '{QgsWkbTypes.displayString(int(geom.wkbType()))}' 不受支持。跳过。")
                continue

            # 遍历要素中的每一个点（对于单点要素只有一个点，对于多点要素有多个点）。
            for pt in points_in_feature:
                # 将点坐标从原始 CRS 转换为目标 CRS (WGS84)。
                transformed_point = transform.transform(pt)
                # 提取经度 (x) 和纬度 (y)，并四舍五入到小数点后6位，确保精度一致性。
                x_coord = round(transformed_point.x(), 6)
                y_coord = round(transformed_point.y(), 6)

                processed_data = {} # 存储当前点的处理结果
                processed_data['x'] = x_coord
                processed_data['y'] = y_coord

                # 获取当前要素的 'name' 值，如果为空则使用图层公共值 (first_valid_line_name_in_layer)。
                current_name_value = str(feature_data_raw.get('name', '') or '').strip()
                processed_data['name'] = current_name_value if current_name_value else first_valid_line_name_in_layer

                # 获取当前要素的 'FHM_No' 值，如果为空则使用图层公共值 (first_valid_fhm_no_in_layer)。
                current_fhm_no_value = str(feature_data_raw.get('FHM_No', '') or '').strip()
                processed_data['Firm_Highway_Number'] = current_fhm_no_value if current_fhm_no_value else first_valid_fhm_no_in_layer

                # 【修改逻辑】获取当前要素的 'color' 值，如果为空则使用图层公共值 (first_valid_color_in_layer)。
                current_color_value = str(feature_data_raw.get('color', '') or '').strip()
                processed_data['color'] = current_color_value if current_color_value else first_valid_color_in_layer

                # 【修改逻辑】获取当前要素的 'direction' 值，如果为空则使用图层公共值 (first_valid_direction_in_layer)。
                current_direction_value = str(feature_data_raw.get('direction', '') or '').strip()
                processed_data['direction'] = current_direction_value if current_direction_value else first_valid_direction_in_layer


                # 直接映射 'name_zh', 'name_en', 'type' 字段。
                processed_data['name_zh'] = str(feature_data_raw.get('name_zh', '') or '')
                processed_data['name_en'] = str(feature_data_raw.get('name_en', '') or '')
                processed_data['type'] = str(feature_data_raw.get('type', '') or '')

                # 映射并添加预定义的特殊字段（如 transfer_line_X）。
                # 遍历映射字典，将 QGIS 字段名转换为 XML 表头名。
                # 注意：'FHM_No' 已经在上面单独处理了，所以这里要跳过，避免重复处理。
                for qgis_field_name, xml_header_name in qgis_field_to_xml_header_map.items():
                    if qgis_field_name == 'FHM_No': # 避免重复处理 FHM_No
                        continue
                    if qgis_field_name in feature_data_raw:
                        processed_data[xml_header_name] = str(feature_data_raw.get(qgis_field_name, '') or '')

                # 添加所有未被特殊处理的 QGIS 字段。
                # 这一步是为了将 QGIS 图层中除了已明确映射和处理的字段之外，
                # 其他的所有字段也一并添加到 processed_data 中。
                for field_name in layer.fields().names():
                    # 确保不添加已在映射中处理过的字段 ('qgis_field_to_xml_header_map' 的键)
                    # 也不添加已经直接添加到 processed_data 的字段 (如 'x', 'y', 'name' 等)
                    # 也不添加 'FHM_No' (因为它被特殊处理了)
                    is_mapped = field_name in qgis_field_to_xml_header_map
                    is_directly_added = field_name in processed_data
                    is_fhm_no = field_name == 'FHM_No'

                    if not is_mapped and not is_directly_added and not is_fhm_no:
                        processed_data[field_name] = str(feature_data_raw.get(field_name, '') or '')

                # --- 核心修改：处理 'id' 字段 ---
                # 获取 QGIS 中已有的 'id' 值
                existing_id = str(feature_data_raw.get('id', '') or '').strip()

                if existing_id:
                    # 如果 QGIS 中 'id' 字段不为空，则优先使用它。
                    processed_data['id'] = existing_id
                else:
                    # 如果 QGIS 中 'id' 字段为空，则根据 (x, y) 坐标生成一个稳定的短 ID (9位)。
                    processed_data['id'] = generate_stable_id_from_coords(x_coord, y_coord, target_length=9)
                    # print(f"为坐标 ({x_coord}, {y_coord}) 生成了短稳定ID: {processed_data['id']}") # 调试信息

                # 处理 'seq' 字段：如果 QGIS 中为空，则在后续步骤中生成。
                # 'seq' 字段在这里只是从原始数据中获取，具体的自动生成逻辑在后面排序后进行。
                processed_data['seq'] = str(feature_data_raw.get('seq', '') or '')

                # 将当前处理好的点数据添加到当前图层的列表中。
                current_layer_features_processed.append(processed_data)

        # 对当前图层内的要素进行排序：首先按 'name' 字段，然后按 'seq' 字段。
        # _try_int 辅助函数用于确保 'seq' 字段（可能包含混合字符串和数字）的正确排序。
        # 确保 _try_int 始终返回元组，以避免 TypeError
        current_layer_features_processed.sort(key=lambda p: (p.get('name', ''), _try_int(p.get('seq', ''))))

        seq_counter_by_line = {} # 字典，用于为每个线路生成独立的 'seq' 值。
                                 # 键是线路名称，值是当前线路的下一个序列号。

        # 第三遍遍历：为没有 'seq' 值的点生成 'seq'，并将其添加到最终导出列表。
        for point_data in current_layer_features_processed:
            line_name = point_data.get('name')
            # 如果当前线路名称是第一次出现，则初始化其序列号为 1。
            if line_name not in seq_counter_by_line:
                seq_counter_by_line[line_name] = 1

            # 如果 'seq' 字段在 QGIS 中为空，则自动生成 'seq' 值。
            if not point_data['seq']:
                # 尝试从线路名称中提取数字部分，例如 "L1" 中的 "1"。
                line_num_match = re.search(r'\d+', line_name)
                # 构建线路前缀，例如 "L1"，如果线路名称没有数字，就直接用线路名称。
                line_prefix = f"L{line_num_match.group(0)}" if line_num_match else line_name
                # 生成新的 'seq' 值，格式为 "L<线路号>_<两位站号>" (例如 "L1_01")。
                point_data['seq'] = f"{line_prefix}_{seq_counter_by_line[line_name]:02d}"

            seq_counter_by_line[line_name] += 1 # 当前线路的序列号递增。

            # 将当前处理好的点数据直接添加到最终要导出的总列表中。
            # 这里不再进行坐标去重，因为需求是只要是要素里的点，都导出。
            all_processed_points_for_final_export.append(point_data)

    # --- 最终导出前，对所有点进行统一排序 ---
    # 如果处理完所有图层后，没有收集到任何可导出的数据，则打印警告并返回。
    if not all_processed_points_for_final_export:
        print("没有可导出数据。请检查图层是否包含有效点要素，并且字段已正确填充。")
        return

    # 最终的导出列表就是已经包含了所有图层并已处理好的点数据。
    all_points_for_final_export = all_processed_points_for_final_export

    def final_sort_key(p):
        """
        定义最终导出顺序的排序键：首先按线路名称，然后按序列号。
        这确保了 XML 中数据的组织结构是逻辑和可预测的。
        """
        name = p.get('name', '')
        seq = p.get('seq', '')
        # 使用 _try_int 确保正确的数字和文本混合排序，并且始终返回元组
        return (name, _try_int(seq))

    # 对所有点进行最终排序。
    all_points_for_final_export.sort(key=final_sort_key)

    # 获取当前时间，用于 XML 中的创建/保存时间戳。
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    # XML 声明和处理指令，这是 XML 文件开头的标准部分。
    xml_declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    mso_application_pi = '<?mso-application progid="Excel.Sheet"?>\n'

    # 构建 XML Workbook 根元素及其属性。
    # 这些属性定义了 XML 命名空间，是 Excel SpreadsheetML 格式的要求。
    workbook = Element("Workbook", {
        "xmlns": "urn:schemas-microsoft-com:office:spreadsheet",
        "xmlns:o": "urn:schemas-microsoft-com:office:office",
        "xmlns:x": "urn:schemas-microsoft-com:office:excel",
        "xmlns:ss": "urn:schemas-microsoft-com:office:spreadsheet",
        "xmlns:html": "http://www.w3.org/TR/REC-html40",
        "xmlns:dt": "uuid:C2F41010-65B3-11d1-A29F-00AA00C14882"
    })

    # 添加文档属性，如作者、创建/保存时间。
    document_properties = SubElement(workbook, "DocumentProperties", {
        "xmlns": "urn:schemas-microsoft-com:office:office"
    })
    SubElement(document_properties, "Author").text = "QGIS Exporter"
    SubElement(document_properties, "LastAuthor").text = "QGIS Exporter"
    SubElement(document_properties, "Created").text = current_time
    SubElement(document_properties, "LastSaved").text = current_time

    # 添加自定义文档属性，这些是 WPS Excel 特有的元数据。
    custom_doc_props = SubElement(workbook, "CustomDocumentProperties", {
        "xmlns": "urn:schemas-microsoft-com:office:office"
    })
    # ICV 值根据 FIRM_XML.xml 调整为 _11
    SubElement(custom_doc_props, "ICV", {"dt:dt": "string"}).text = "A07F866F274640CBBCB2099FFB2A5A59_11"
    SubElement(custom_doc_props, "KSOProductBuildVer", {"dt:dt": "string"}).text = "2052-12.1.0.21171"

    # 添加 ExcelWorkbook 设置，控制 Excel 窗口的一些行为。
    excel_workbook = SubElement(workbook, "ExcelWorkbook", {
        "xmlns": "urn:schemas-microsoft-com:office:excel"
    })
    SubElement(excel_workbook, "WindowWidth").text = "25600"
    SubElement(excel_workbook, "WindowHeight").text = "10480"
    SubElement(excel_workbook, "ProtectStructure").text = "False"
    SubElement(excel_workbook, "ProtectWindows").text = "False"

    # 定义 Excel 中的样式。
    styles = SubElement(workbook, "Styles")
    # 默认样式
    default_style = SubElement(styles, "Style", {"ss:ID": "Default", "ss:Name": "Normal"})
    SubElement(default_style, "Alignment", {"ss:Vertical": "Center"})
    SubElement(default_style, "Borders")
    SubElement(default_style, "Font", {"ss:FontName": "宋体", "x:CharSet": "134", "ss:Size": "11", "ss:Color": "#000000"})
    SubElement(default_style, "Interior")
    SubElement(default_style, "NumberFormat")
    SubElement(default_style, "Protection")

    # 自定义样式 s49
    s49_style = SubElement(styles, "Style", {"ss:ID": "s49"})
    SubElement(s49_style, "Alignment", {"ss:Vertical": "Center"})
    SubElement(s49_style, "Borders")
    SubElement(s49_style, "Font", {"ss:FontName": "宋体", "x:CharSet": "134", "ss:Size": "11", "ss:Color": "#000000"})
    SubElement(s49_style, "Interior")
    SubElement(s49_style, "NumberFormat")
    SubElement(s49_style, "Protection")

    # 自定义样式 s50 (用于线路标题行)
    s50_style = SubElement(styles, "Style", {"ss:ID": "s50"})
    SubElement(s50_style, "Alignment", {"ss:Horizontal": "Center", "ss:Vertical": "Center"})
    SubElement(s50_style, "Font", {"ss:FontName": "宋体", "x:CharSet": "134", "ss:Size": "12", "ss:Color": "#0000FF", "ss:Bold": "1" })

    # 自定义样式 s51 (用于文本格式单元格)
    s51_style = SubElement(styles, "Style", {"ss:ID": "s51"})
    SubElement(s51_style, "NumberFormat", {"ss:Format": "@"}) # @ 表示文本格式

    # 自定义样式 s52 (用于数字格式单元格)
    s52_style = SubElement(styles, "Style", {"ss:ID": "s52"})
    SubElement(s52_style, "NumberFormat") # 通用数字格式

    # 创建 Worksheet (工作表)
    worksheet = SubElement(workbook, "Worksheet", {"ss:Name": "Sheet1"})

    # 定义所有预期列的名称和它们在最终 XML 中的固定 1-based 索引。
    # 这是严格按照 FIRM_XML_3.xml 模板的结构来定义的，确保列顺序和数量正确。
    xml_header_definitions = [
        ("name", 1), ("color", 2), ("direction", 3), ("seq", 4), ("type", 5),
        ("name_zh", 6), ("name_en", 7), ("x", 8), ("y", 9), ("id", 10)
    ]

    # 动态生成 transfer_line_X 列的定义 (11-16)。
    # 这里固定生成到 transfer_line_6，以匹配 WPS 导出的 XML 结构。
    for i in range(1, 7):
        xml_header_definitions.append((f"transfer_line_{i}", 10 + i))

    # 添加 Firm_Highway_Number 列的定义 (17)。
    xml_header_definitions.append(("Firm_Highway_Number", 17))

    # 从定义中创建 header_name 到固定列索引的映射。
    # 方便通过列名快速查找其在 XML 中的位置。
    header_to_fixed_col_index = {header[0]: header[1] for header in xml_header_definitions}
    # 创建有序的 header names 列表，用于遍历时按照正确的顺序生成 XML 列。
    all_ordered_header_names = [header[0] for header in xml_header_definitions]

    # 获取最大的列号，用于 Table 的 ExpandedColumnCount 属性。
    max_column_index = xml_header_definitions[-1][1] # Firm_Highway_Number 的索引，即 17

    # 预设列宽度，匹配 FIRM_XML_3.xml 的 Column 定义。
    # 这些宽度是 WPS Excel 导出的标准宽度。
    column_widths = {
        "name": 71.25, "color": 46.5, "direction": 78.75, "seq": 66.75, "type": 32.25,
        "name_zh": 120.75, "name_en": 120.75, "x": 85.5, "y": 86.25, "id": 93.75,
        "transfer_line_1": 105,
        "transfer_line_2": 105,
        "transfer_line_3": 105,
        "transfer_line_4": 105,
        "transfer_line_5": 105,
        "transfer_line_6": 105,
        "Firm_Highway_Number": 136.5
    }

    # 创建 Table 元素，它包含了所有数据行和列定义。
    table = SubElement(worksheet, "Table", {
        "ss:ExpandedColumnCount": str(max_column_index), # 定义总列数
        "x:FullColumns": "1", # Excel 内部属性
        "x:FullRows": "1", # Excel 内部属性
        "ss:DefaultColumnWidth": "48", # 默认列宽
        "ss:DefaultRowHeight": "14" # 默认行高
    })

    # 生成 Column 定义。
    # 这一步是为了在 XML 中预定义每一列的宽度和样式。
    for i in range(1, max_column_index + 1):
        col_attrs = {"ss:StyleID": "s49", "ss:AutoFitWidth": "0"} # 默认样式和不自动调整宽度

        current_header_key_for_width = None
        # 查找当前列索引对应的表头名称，以便获取其预设宽度。
        for header_name, index in xml_header_definitions:
            if index == i:
                current_header_key_for_width = header_name
                break

        # 根据表头名称获取列宽，如果未找到则使用默认值 48。
        col_width = column_widths.get(current_header_key_for_width, 48) if current_header_key_for_width else 48
        col_attrs["ss:Width"] = str(col_width) # 设置列宽属性

        # 为特定的列设置 ss:Index 属性。
        # 这是为了在 XML 中明确指示某些列的起始索引，通常用于优化或兼容性。
        if i == 1:
            col_attrs["ss:Index"] = "1"
        elif i == 11:
            col_attrs["ss:Index"] = "11"

        SubElement(table, "Column", col_attrs) # 将 Column 元素添加到 Table 中

    # 创建第1行，数据标识行 (表头)。
    header_data_row = SubElement(table, "Row", {"ss:Index": "1"})
    # 按照预定义的顺序遍历所有表头名称，生成 Cell 和 Data 元素。
    for header_name in all_ordered_header_names:
        cell = SubElement(header_data_row, "Cell")
        data = SubElement(cell, "Data", {"ss:Type": "String"})
        data.text = header_name # 表头名称作为 Cell 的数据

    current_physical_row_count = 2 # 跟踪当前在 XML Table 中的物理行数，从第2行开始（第1行是表头）。
    last_line_name = None # 用于检测线路名称变化，以便插入线路标题行。
    line_title_style_id = "s50" # 线路标题行使用的样式 ID。

    # 遍历所有要导出的点数据，生成实际数据行。
    # all_points_for_final_export 列表中的点数据已经按照线路和序列号排好序。
    for point_data in all_points_for_final_export:
        current_line_name = point_data.get('name')

        # 如果当前线路名称与上一行不同，表示进入了新的线路，需要插入一个线路标题行。
        if current_line_name != last_line_name:
            line_title_row = SubElement(table, "Row") # 创建新的行元素
            line_title_row.set("ss:Height", "24") # 设置行高
            line_title_row.set("ss:AutoFitHeight", "0") # 不自动调整行高

            # 创建合并单元格的 Cell，MergeAcross 属性表示合并的列数。
            # 合并的列数是总列数减去 1 (因为当前 Cell 自身也占一列)。
            line_title_cell = SubElement(line_title_row, "Cell", {"ss:MergeAcross": str(max_column_index - 1)})
            line_title_cell.set("ss:StyleID", line_title_style_id) # 应用线路标题样式

            line_title_data = SubElement(line_title_cell, "Data", {"ss:Type": "String"})
            # 格式化线路标题的文本内容。
            line_title_data.text = (
                f"线路名称: {current_line_name} "
                f"(颜色: {point_data.get('color', '') or ''}, "
                f"方向: {point_data.get('direction', '') or ''})"
            )
            current_physical_row_count += 1 # 线路标题行也算作一物理行

        row = SubElement(table, "Row") # 创建数据行

        last_generated_col_index = 0 # 跟踪上一个生成的 Cell 的列索引，用于处理 ss:Index 属性

        # 按照预定义的表头顺序遍历，生成每个 Cell。
        for header_name in all_ordered_header_names:
            value = point_data.get(header_name, "") # 获取当前点数据中对应列的值

            fixed_col_index = header_to_fixed_col_index[header_name] # 获取该列的固定索引

            # 判断是否为核心列 (name 到 id)。
            # 核心列即使为空也需要生成 Cell 标签，非核心列为空则可以跳过。
            is_core_column = (fixed_col_index >= 1 and fixed_col_index <= 10)

            if str(value).strip() == "" and not is_core_column:
                # 如果值为空字符串且不是核心列，则完全跳过，不生成 Cell 标签。
                # 这样可以减小 XML 文件大小，并与 WPS Excel 导出的行为保持一致。
                continue

            cell_attrs = {} # 单元格属性字典
            if header_name in ["x", "y"]:
                cell_attrs["ss:StyleID"] = "s52" # 坐标使用数字样式
                data_type = "Number" # 数据类型为数字
            else:
                cell_attrs["ss:StyleID"] = "s51" # 其他使用文本样式
                data_type = "String" # 数据类型为字符串

            # 如果当前列的索引与上一个生成的列的索引不连续，则需要明确指定 ss:Index。
            # 这是为了处理跳过空非核心列后，后续列的索引能够正确对齐。
            if fixed_col_index != (last_generated_col_index + 1):
                cell_attrs["ss:Index"] = str(fixed_col_index)

            cell = SubElement(row, "Cell", cell_attrs) # 创建 Cell 元素并设置属性
            data = SubElement(cell, "Data", {"ss:Type": data_type}) # 创建 Data 元素并设置数据类型
            data.text = str(value) # 将值作为 Data 的文本内容

            last_generated_col_index = fixed_col_index # 更新上一个生成的列索引

        current_physical_row_count += 1 # 数据行也算作一物理行
        last_line_name = current_line_name # 更新上一行的线路名称

    # 更新 Table 的 ExpandedRowCount 属性，指示表格的总行数（包括表头和线路标题行）。
    table.set("ss:ExpandedRowCount", str(current_physical_row_count - 1))

    # 添加 WorksheetOptions，控制 Excel 工作表的一些显示和保护设置。
    worksheet_options = SubElement(worksheet, "WorksheetOptions", {
        "xmlns": "urn:schemas-microsoft-com:office:excel"
    })
    page_setup = SubElement(worksheet_options, "PageSetup")
    SubElement(page_setup, "Header")
    SubElement(page_setup, "Footer")
    SubElement(worksheet_options, "Selected")
    SubElement(worksheet_options, "TopRowVisible").text = "0"
    SubElement(worksheet_options, "LeftColumnVisible").text = "0"
    SubElement(worksheet_options, "PageBreakZoom").text = "100"
    panes = SubElement(worksheet_options, "Panes")
    pane = SubElement(panes, "Pane")
    SubElement(pane, "Number").text = "3"
    SubElement(pane, "ActiveRow").text = "0"
    SubElement(pane, "ActiveCol").text = "0"

    SubElement(worksheet_options, "ProtectObjects").text = "False"
    SubElement(worksheet_options, "ProtectScenarios").text = "False"

    # 将 XML 树转换为字符串。
    raw_xml_string = tostring(workbook, encoding='utf-8').decode("utf-8")

    # 对生成的 XML 字符串进行一些格式清理，移除多余的换行符和空格，
    # 以使其更紧凑，并更接近 WPS Excel 导出的风格。
    raw_xml_string = re.sub(r'>\s*<', '><', raw_xml_string)
    raw_xml_string = raw_xml_string.replace('>\n<', '><')
    raw_xml_string = raw_xml_string.replace('/>\n<', '><')

    # 添加 XML 声明和处理指令到 XML 内容的开头。
    final_xml_content = xml_declaration + mso_application_pi + raw_xml_string

    # 将最终的 XML 内容写入到指定的文件中。
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(final_xml_content)

    print(f"数据已成功导出到: {output_filepath}")

# --- 如何在QGIS中使用此代码 ---
# (此部分与之前的说明相同，无需修改)
