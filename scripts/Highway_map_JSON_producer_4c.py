import xml.etree.ElementTree as ET # 导入XML解析库，用于处理XML文件
import json # 导入JSON库，用于处理JSON数据
import os # 导入操作系统库，用于文件路径操作、目录创建等
import tkinter as tk # 导入Tkinter库，用于创建图形用户界面（GUI），例如文件选择对话框
from tkinter import filedialog, messagebox # 从Tkinter导入文件对话框和消息框模块
import re # 导入正则表达式库，用于字符串匹配和处理
import copy # 导入copy库，用于深拷贝对象（如JSON模板），避免修改原始模板
import random # 导入random库，用于生成随机ID
import datetime # 导入datetime库，用于获取当前时间，用于日志记录
import hashlib # 用于SHA256哈希，生成稳定ID

# --- 配置常量 ---
# 设置一个SVG输出维度的上限。这是为了控制生成地图的最大尺寸，
# 避免在数据范围过大时生成过于巨大的SVG坐标，影响前端渲染性能或显示效果。
# 同时，也兼顾了用户提出的“svgViewBoxZoom 和 svgViewBoxMin大小最好不要超过1000”的要求，
# 虽然这里是控制内部坐标系的尺寸，但后续viewBox会基于此进行调整。
MAX_SVG_DIMENSION = 1000.0 # 建议最大尺寸，可根据实际显示需求调整

# 【新增常量】用于svgViewBoxZoom的计算和限制
MIN_ZOOM_VALUE = 45.0
MAX_ZOOM_VALUE = 70.0
# 【新增常量】用于svgViewBoxMin的计算和限制
MIN_VIEWBOX_MIN_COORD = 80.0
MAX_VIEWBOX_MIN_COORD = 300.0

# 这是一个经验值，用于将地图的实际地理范围映射到视图框的缩放比例。
# 调整这个值可以改变自动缩放的灵敏度。
# 例如，如果设置为1000.0，那么当地图最大跨度为1000个地理单位时，默认缩放可能是1.0 (如果这里不是1:1的关系)。
# 在我们的策略中，svgViewBoxZoom = NOMINAL_VIEWBOX_SIZE / (max_map_span + epsilon)
# NOMINAL_VIEWBOX_SIZE 可以理解为我们希望在理想情况下（例如缩放为1时）视图框的尺寸。
NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC = 1000.0 # 用于计算zoom的基准视图框大小

# 【新增常量】节点类型优先级映射 (同时包含简化和完整类型名)
NODE_TYPE_PRIORITY = {
    't': 3,
    's': 2,
    'v': 1,
    'shmetro-osysi': 3,
    'shmetro-basic': 2,
    'virtual': 1
}

# 【新增常量】节点key前缀映射 (同时包含简化和完整类型名)
NODE_KEY_PREFIX = {
    't': 'stn_',
    's': 'stn_',
    'v': 'misc_node_',
    'shmetro-osysi': 'stn_',
    'shmetro-basic': 'stn_',
    'virtual': 'misc_node_'
}

# 【新增常量】完整节点类型名称映射 (用于输出JSON)
FULL_NODE_TYPE_NAMES = {
    't': 'shmetro-osysi',
    's': 'shmetro-basic',
    'v': 'virtual'
}

# --- 辅助函数：生成稳定ID (从 qgis_xml_producer_V2a.py 复制过来) ---
# Base62编码的字符集：0-9, A-Z, a-z
BASE62_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

def base_encode(number, base_chars):
    """
    将一个整数编码为指定字符集的字符串。
    用于将大整数（如哈希值）转换为更短的字符串形式。
    """
    if number == 0:
        return base_chars[0]
    base = len(base_chars)
    encoded_string = []
    while number > 0:
        encoded_string.append(base_chars[number % base])
        number //= base
    return "".join(reversed(encoded_string))


def generate_stable_id_from_coords(x, y, target_length=9):
    """
    根据给定的 (x, y) 坐标生成一个稳定、确定性且长度为 target_length 的短 ID。
    """
    # 确保坐标精度一致，防止浮点数精度问题导致哈希不一致。
    coord_string = f"{x:.6f},{y:.6f}"

    sha256_hash = hashlib.sha256(coord_string.encode('utf-8')).hexdigest()

    hash_as_int = int(sha256_hash, 16)

    base62_encoded = base_encode(hash_as_int, BASE62_CHARS)

    final_id = base62_encoded[:target_length]

    return final_id

# 【新增辅助函数】获取节点类型的优先级
def get_type_priority(node_type_str):
    """
    根据节点类型字符串获取其优先级。
    """
    return NODE_TYPE_PRIORITY.get(node_type_str.lower(), 0) # 默认为0，处理未知类型

# 【新增辅助函数】获取节点key前缀
def get_key_prefix(node_type_str):
    """
    根据节点类型获取其在JSON中对应的key前缀 (stn_ 或 misc_node_)。
    """
    return NODE_KEY_PREFIX.get(node_type_str.lower(), 'stn_') # 默认为stn_

# 【新增辅助函数】获取完整节点类型名称
def get_full_node_type_name(simplified_type_char):
    """
    根据简化类型字符 ('v', 's', 't') 获取完整的节点类型名称。
    """
    return FULL_NODE_TYPE_NAMES.get(simplified_type_char.lower(), 'shmetro-basic') # 默认为shmetro-basic


def select_file_dialog(file_type_name, file_extensions):
    """
    显示文件选择对话框，让用户选择指定类型的文件。
    """
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title=f"请选择 {file_type_name}", filetypes=file_extensions)
    return file_path

def get_cell_text(cell, ns_map):
    """
    从XML的<Cell>元素中提取<Data>标签的文本内容。
    """
    if cell is None:
        return ""
    data_tag = cell.find('ss:Data', ns_map)
    return data_tag.text.strip() if data_tag is not None and data_tag.text is not None else ""

def parse_row_to_column_dict(row_cells, ns_map):
    """
    解析XML <Row> 元素中的 <Cell> 列表，将其转换为以列索引为键、单元格文本为值的字典。
    正确处理了 `ss:Index` 属性，该属性指定了当前单元格的列索引，可以跳过空白列。
    """
    col_data_dict = {}
    current_col_tracker = 1
    for cell_element in row_cells:
        explicit_cell_index_str = cell_element.get('{urn:schemas-microsoft-com:office:spreadsheet}Index')
        if explicit_cell_index_str:
            current_col_tracker = int(explicit_cell_index_str)
        data_tag = cell_element.find('ss:Data', ns_map)
        if data_tag is not None:
            data_type = data_tag.get('{urn:schemas-microsoft-com:office:spreadsheet}Type')
            text_content = data_tag.text if data_tag.text is not None else ""
            if data_type == 'Number':
                try:
                    col_data_dict[current_col_tracker] = float(text_content)
                except ValueError:
                    col_data_dict[current_col_tracker] = text_content # 如果转换失败，保留为字符串
            else:
                col_data_dict[current_col_tracker] = text_content.strip()
        else:
            col_data_dict[current_col_tracker] = ""
        current_col_tracker += 1
    return col_data_dict

def parse_seq_key(seq_str):
    """
    解析 'LX_Y' 格式的站点序列字符串，生成一个可用于正确排序的元组。
    """
    match = re.match(r'([A-Za-z]+)(\d+)_(\d+)', seq_str)
    if match:
        try:
            line_prefix = match.group(1)
            line_num = int(match.group(2))
            station_num = int(match.group(3))
            return (line_prefix, line_num, station_num)
        except ValueError:
            log_message("WARNING", "Parsing Error", f"Could not parse numeric part of sequence '{seq_str}'.", f"无法解析序列号 '{seq_str}' 中的数字部分。")
            return (seq_str, 0, 0)
    else:
        log_message("WARNING", "Parsing Error", f"Sequence string '{seq_str}' does not match expected 'LX_Y' format.", f"序列号字符串 '{seq_str}' 不符合预期格式 'LX_Y'。")
        return (seq_str, 0, 0)

def convert_lonlat_to_svg_coords(lon, lat, min_lon, max_lon, min_lat, max_lat,
                                 target_svg_width, target_svg_height, padding_factor=0.05):
    """
    将经纬度 (lon, lat) 转换为 SVG 坐标 (svg_x, svg_y)。
    """
    lon_range = max_lon - min_lon
    lat_range = max_lat - min_lat

    if lon_range == 0: lon_range = 0.0001
    if lat_range == 0: lat_range = 0.0001

    effective_drawable_width = target_svg_width * (1 - 2 * padding_factor)
    effective_drawable_height = target_svg_height * (1 - 2 * padding_factor)

    offset_x_padding = target_svg_width * padding_factor
    offset_y_padding = target_svg_height * padding_factor

    scale_factor_x = effective_drawable_width / lon_range
    scale_factor_y = effective_drawable_height / lat_range

    unified_scale_factor = min(scale_factor_x, scale_factor_y)

    scaled_map_width = lon_range * unified_scale_factor
    scaled_map_height = lat_range * unified_scale_factor

    center_offset_x = (effective_drawable_width - scaled_map_width) / 2
    center_offset_y = (effective_drawable_height - scaled_map_height) / 2

    svg_x = (lon - min_lon) * unified_scale_factor + offset_x_padding + center_offset_x
    svg_y = (max_lat - lat) * unified_scale_factor + offset_y_padding + center_offset_y

    return round(svg_x, 3), round(svg_y, 3)

# --- 主处理函数 ---

def process_highway_data(xml_content, json_template_content):
    """
    读取XML数据，结合JSON模板，生成新的JSON文件。
    此函数负责解析XML，提取节点和边的信息，并填充到JSON结构中。
    特别处理基于SVG坐标的节点去重，并动态调整SVG视图框参数。
    实现了节点类型覆盖等级：T > S > V。

    参数:
        xml_content (str): XML数据表的字符串内容。
        json_template_content (str): JSON模板文件的字符串内容。

    返回:
        str: 包含生成的JSON数据的字符串。
    """
    # 定义XML命名空间
    ns = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
    
    # 从XML字符串解析出根元素
    root = ET.fromstring(xml_content)
    # 在整个工作表中查找所有行
    rows = root.findall('.//ss:Worksheet/ss:Table/ss:Row', ns)

    if not rows:
        log_message("ERROR", "Processing Error", "No data rows found in XML. Please check XML structure.", "未在XML中找到任何数据行。请检查XML结构。")
        raise ValueError("未在XML中找到任何数据行。请检查XML结构。")

    # 解析表头行，建立列名到索引的映射
    header_row = rows[0]
    header_cells = header_row.findall('ss:Cell', ns)
    header_names = {i + 1: get_cell_text(cell, ns) for i, cell in enumerate(header_cells)}

    actual_station_data_rows = [] # 存储所有实际的站点数据行
    line_colors = {} # 存储线路颜色

    all_longitudes = [] # 收集所有有效站点的经度
    all_latitudes = [] # 收集所有有效站点的纬度

    # 从XML的第二行开始遍历
    for i in range(1, len(rows)):
        row_element = rows[i]
        
        # 识别并处理线路标题行
        merged_cell = row_element.find('ss:Cell[@ss:MergeAcross]', ns)
        if merged_cell is not None and row_element.get('{urn:schemas-microsoft-com:office:spreadsheet}Height') == "24":
            data_text = get_cell_text(merged_cell, ns)
            match = re.search(r'线路名称:\s*([^ ]+)\s*\(颜色:\s*(#[0-9a-fA-F]+)', data_text)
            if match:
                line_name_from_header = match.group(1).strip()
                line_color_from_header = match.group(2).strip()
                line_colors[line_name_from_header] = line_color_from_header
                log_message("NORMAL", "XML解析", 
                            f"Identified line header: Line='{line_name_from_header}', Color='{line_color_from_header}'.",
                            f"识别到线路标题: 线路='{line_name_from_header}', 颜色='{line_color_from_header}'。")
            continue

        # 站点数据行处理
        row_cells = row_element.findall('ss:Cell', ns)
        if not row_cells:
            continue

        row_data = parse_row_to_column_dict(row_cells, ns)
        
        station_info = {}
        for col_idx, value in row_data.items():
            col_name = header_names.get(col_idx)
            if col_name:
                station_info[col_name] = value
        
        # 核心必填字段验证
        core_required_fields = ['name', 'seq', 'x', 'y', 'type', 'id'] 
        if not all(station_info.get(field) for field in core_required_fields):
            log_message("WARNING", "数据验证错误", 
                        f"Skipping row due to missing core critical station fields: {station_info.get('name_zh', '')}_{station_info.get('seq', '')}", 
                        f"由于缺少核心关键站点字段，跳过行: {station_info.get('name_zh', '')}_{station_info.get('seq', '')}")
            continue

        station_type = station_info.get('type')
        if station_type == 'T':
            if not station_info.get('name_zh') or not station_info.get('name_en'):
                log_message("WARNING", "数据验证错误", 
                            f"Skipping transfer station '{station_info.get('name', '')}_{station_info.get('seq', '')}' due to missing Chinese or English names.", 
                            f"由于缺少中文或英文名称，跳过换乘站 '{station_info.get('name', '')}_{station_info.get('seq', '')}'。")
                continue
        
        station_line_name = station_info.get('name')
        if not station_line_name:
            log_message("WARNING", "数据解析错误", f"Station row missing 'name' field after initial validation: {row_data}", f"站点行缺少'name'字段: {row_data}")
            continue 
            
        station_info['color'] = line_colors.get(station_line_name, '#000000')

        # 收集经纬度数据并处理类型转换错误
        try:
            lon = float(station_info.get('x'))
            lat = float(station_info.get('y'))
            all_longitudes.append(lon)
            all_latitudes.append(lat)
            actual_station_data_rows.append(station_info)
        except ValueError:
            log_message("WARNING", "数据解析错误",
                      f"Invalid longitude or latitude found for station: {station_info.get('name_zh', station_info.get('name', ''))}_{station_info.get('seq', '')} (x:{station_info.get('x')}, y:{station_info.get('y')}). Skipping.",
                      f"站点 '{station_info.get('name_zh', station_info.get('name', ''))}_{station_info.get('seq', '')}' 的经纬度无效。跳过此行。")
            continue

    # 准备JSON数据结构
    json_data = json.loads(json_template_content)
    new_nodes = [] # 存储所有最终生成的节点对象
    new_edges = []

    # 【核心修改】用于跟踪已处理的SVG坐标及其对应的节点key和节点对象引用
    # 存储 {final_node_base_id: {'node_object': <reference_to_node_in_new_nodes>, 'data': station_info, 'current_simplified_type': 's', ...}}
    seen_svg_coords_info = {} 
    # 用于存储原始XML ID到最终生成的节点key的映射
    node_id_to_key_map = {} 

    last_station_info_by_line = {} # 存储每条线路的最后一个站点信息，用于生成边

    # 动态计算SVG ViewBox参数
    if not all_longitudes or not all_latitudes:
        log_message("ERROR", "数据错误", "No valid longitude/latitude data found for SVG viewbox calculation. Cannot generate map.", "未找到有效的经纬度数据，无法进行SVG视图框计算。")
        raise ValueError("未找到有效的经纬度数据，无法进行SVG视图框计算。")
    
    min_lon, max_lon = min(all_longitudes), max(all_longitudes)
    min_lat, max_lat = min(all_latitudes), max(all_latitudes)

    range_x = max_lon - min_lon
    range_y = max_lat - min_lat

    effective_range_x = max(range_x, 0.0001)
    effective_range_y = max(range_y, 0.0001)

    max_map_span = max(effective_range_x, effective_range_y)

    calculated_zoom = NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC / max_map_span
    json_data["svgViewBoxZoom"] = max(MIN_ZOOM_VALUE, min(MAX_ZOOM_VALUE, calculated_zoom))
    log_message("INFO", "SVG参数", f"Calculated svgViewBoxZoom: {json_data['svgViewBoxZoom']}", f"计算得到svgViewBoxZoom: {json_data['svgViewBoxZoom']}")

    actual_viewbox_coord_span = NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC / json_data["svgViewBoxZoom"]

    center_x_data = (min_lon + max_lon) / 2
    center_y_data = (min_lat + max_lat) / 2

    calculated_min_x = center_x_data - (actual_viewbox_coord_span / 2)
    calculated_min_y = center_y_data - (actual_viewbox_coord_span / 2)

    json_data["svgViewBoxMin"]["x"] = max(MIN_VIEWBOX_MIN_COORD, min(MAX_VIEWBOX_MIN_COORD, calculated_min_x))
    json_data["svgViewBoxMin"]["y"] = max(MIN_VIEWBOX_MIN_COORD, min(MAX_VIEWBOX_MIN_COORD, calculated_min_y))

    log_message("INFO", "SVG参数", f"Calculated svgViewBoxMin.x: {json_data['svgViewBoxMin']['x']}", f"计算得到svgViewBoxMin.x: {json_data['svgViewBoxMin']['x']}")
    log_message("INFO", "SVG参数", f"Calculated svgViewBoxMin.y: {json_data['svgViewBoxMin']['y']}", f"计算得到svgViewBoxMin.y: {json_data['svgViewBoxMin']['y']}")
    
    svg_padding_factor = 0.05 

    svg_output_width = NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC
    svg_output_height = NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC

    log_message("NORMAL", "坐标缩放", 
                f"Calculated geographical bounds: Lon({min_lon}, {max_lon}), Lat({min_lat}, {max_lat}).",
                f"计算的地理边界: 经度({min_lon}, {max_lon}), 纬度({min_lat}, {max_lat})。")
    log_message("NORMAL", "坐标缩放", 
                f"Used nominal SVG output size for coordinate conversion: Width={round(svg_output_width, 2)}, Height={round(svg_output_height, 2)}.",
                f"用于坐标转换的SVG名义输出尺寸: 宽度={round(svg_output_width, 2)}, 高度={round(svg_output_height, 2)}。")


    # 提取节点和边模板
    node_templates = {}
    if json_data['graph']['nodes']:
        for node_t in json_data['graph']['nodes']:
            node_type_attr = node_t.get('attributes', {}).get('type')
            base_type = node_type_attr.split('-')[-1].lower() if node_type_attr else ''
            
            if base_type == 'virtual':
                node_templates['V'] = node_t
            elif base_type == 'basic':
                node_templates['S'] = node_t
            elif base_type == 'osysi':
                node_templates['T'] = node_t
    else:
        log_message("WARNING", "模板错误", "JSON template's 'graph.nodes' array is empty. Using default node templates.", "JSON模板的'graph.nodes'数组为空。将使用默认节点模板。")
        node_templates['V'] = { "key": "", "attributes": {"visible": True, "zIndex": 0, "x": 0, "y": 0, "type": "virtual", "virtual": {}} }
        node_templates['S'] = { "key": "", "attributes": {"visible": True, "zIndex": 0, "x": 0, "y": 0, "type": "shmetro-basic", "shmetro-basic": {"names": ["", ""], "nameOffsetX": "right", "nameOffsetY": "top"}} }
        node_templates['T'] = { "key": "", "attributes": {"visible": True, "zIndex": 0, "x": 0, "y": 0, "type": "shmetro-osysi", "shmetro-osysi": {"names": ["", ""], "nameOffsetX": "right", "nameOffsetY": "top"}} }

    edge_template_from_model = None
    if json_data.get('graph', {}).get('edges'):
        edge_template_from_model = json_data['graph']['edges'][0]
    
    if edge_template_from_model is None:
        log_message("WARNING", "模板错误", "Edge template not found in JSON model. Using default minimal edge template.", "JSON模板中未找到边模板。将使用默认最小边模板。")
        edge_template_from_model = {
            "key": "line_DEFAULTEDGE", 
            "source": "", "target": "",
            "attributes": {
                "visible": True, "zIndex": 0, "type": "diagonal", 
                "diagonal": {"startFrom": "from", "offsetFrom": 0, "offsetTo": 0, "roundCornerFactor": 10},
                "style": "single-color",
                "single-color": {"color": ["other", "other", "#000000", "#FFFFFF"]},
                "reconcileId": "", "parallelIndex": -1
            }
        }

    # 核心处理逻辑：遍历站点数据，创建节点和边
    actual_station_data_rows.sort(key=lambda x: (x.get('name', ''), parse_seq_key(x.get('seq', ''))))
    log_message("NORMAL", "排序", "Station data rows sorted by line name and parsed sequence key.", "站点数据行已按线路名称和解析后的序列键排序。")


    for station_info in actual_station_data_rows: 
        line_name = station_info.get('name')
        seq = station_info.get('seq')
        lon = float(station_info.get('x'))
        lat = float(station_info.get('y'))
        
        # 原始XML中的节点类型 (可能是 'V', 'S', 'T' 或完整的 'shmetro-basic' 等)
        # current_xml_node_type_raw 用于实际输出的JSON 'type' 属性
        current_xml_node_type_raw = station_info.get('type', 'S') 
        # current_xml_node_type_simplified 用于优先级比较和前缀查找
        current_xml_node_type_simplified = current_xml_node_type_raw.lower().split('-')[-1][0] 
        
        line_color_for_edge = station_info.get('color', '#000000') # 从station_info获取颜色
        original_xml_id = station_info.get('id')
        
        station_name_zh = station_info.get('name_zh', '')
        station_name_en = station_info.get('name_en', '')

        # 调用坐标转换函数，将经纬度转换为SVG坐标
        svg_x, svg_y = convert_lonlat_to_svg_coords(
            lon, lat,
            min_lon, max_lon, min_lat, max_lat,
            NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC, NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC,
            svg_padding_factor
        )

        # 根据SVG坐标生成基础ID (不带前缀)
        base_node_id_from_coords = generate_stable_id_from_coords(svg_x, svg_y, target_length=9)
        
        # 初始的最终节点key（带有当前行数据对应的类型前缀）
        final_node_key = get_key_prefix(current_xml_node_type_simplified) + base_node_id_from_coords

        # 【核心去重与覆盖逻辑】
        if base_node_id_from_coords in seen_svg_coords_info: # 使用不带前缀的base_node_id_from_coords进行去重判断
            # 坐标已存在，需要进行类型比较和数据合并
            existing_node_info = seen_svg_coords_info[base_node_id_from_coords]
            existing_node_object = existing_node_info['node_object'] # 获取已存在的节点对象的引用
            existing_node_type_in_json_full = existing_node_object['attributes']['type'] # 获取已存在节点的完整类型名
            existing_node_type_in_json_simplified = existing_node_type_in_json_full.lower().split('-')[-1][0] # 简化
            
            current_priority = get_type_priority(current_xml_node_type_simplified)
            existing_priority = get_type_priority(existing_node_type_in_json_simplified)

            # 更新 final_node_key 为已存在的带前缀的key，以确保一致性 (即使前缀可能在后面类型升级时改变)
            final_node_key = existing_node_object['key'] 

            # ====== 节点类型优先级判断和更新 ======
            if current_priority > existing_priority:
                # 【类型升级】当前XML行的数据具有更高的优先级
                log_message("NORMAL", "节点类型升级", 
                            f"Upgrading node type for key '{final_node_key}' from '{existing_node_type_in_json_full}' to '{get_full_node_type_name(current_xml_node_type_simplified)}'.", 
                            f"节点 '{final_node_key}' 类型从 '{existing_node_type_in_json_full}' 升级到 '{get_full_node_type_name(current_xml_node_type_simplified)}'。")
                
                # 更新现有节点对象的类型为新的完整类型名
                existing_node_object['attributes']['type'] = get_full_node_type_name(current_xml_node_type_simplified)
                
                # 更新key的前缀（如果类型升级导致前缀改变）
                new_key_prefix = get_key_prefix(current_xml_node_type_simplified)
                if not final_node_key.startswith(new_key_prefix): # 检查当前key前缀是否需要改变
                    final_node_key = new_key_prefix + base_node_id_from_coords
                    existing_node_object['key'] = final_node_key
                    log_message("NORMAL", "节点Key更新", f"Updated node key to '{final_node_key}' due to type upgrade.", f"由于类型升级，更新节点键为 '{final_node_key}'。")


                # 清除旧的类型特定属性，并添加新的
                for attr_key in ['virtual', 'shmetro-basic', 'shmetro-osysi']:
                    if attr_key in existing_node_object['attributes']:
                        del existing_node_object['attributes'][attr_key]

                # 根据新类型填充属性
                if current_xml_node_type_simplified == 't': # 换乘节点
                    existing_node_object['attributes']['shmetro-osysi'] = {
                        "names": [station_name_zh, station_name_en],
                        "nameOffsetX": "right", "nameOffsetY": "top",
                        "transferLines": []
                    }
                    # 合并换乘线路信息
                    for i in range(1, 7):
                        transfer_line_key = f"transfer_line_{i}"
                        if transfer_line_key in station_info and station_info[transfer_line_key] and \
                           station_info[transfer_line_key] not in existing_node_object['attributes']['shmetro-osysi']['transferLines']:
                            existing_node_object['attributes']['shmetro-osysi']['transferLines'].append(station_info[transfer_line_key])
                elif current_xml_node_type_simplified == 's': # 普通站点
                    existing_node_object['attributes']['shmetro-basic'] = {
                        "names": [station_name_zh, station_name_en],
                        "nameOffsetX": "right", "nameOffsetY": "top"
                    }
                elif current_xml_node_type_simplified == 'v': # 虚拟节点 (这个分支在类型升级时通常不会被触发，除非从0到V)
                    existing_node_object['attributes']['virtual'] = {}
                
                # 更新其他通用属性 (以更高优先级数据为准)
                existing_node_object['attributes']['color'] = station_info.get('color', '')
                existing_node_object['attributes']['direction'] = station_info.get('direction', '')
                existing_node_object['attributes']['Firm_Highway_Number'] = station_info.get('Firm_Highway_Number', '')
                existing_node_object['attributes']['seq'] = station_info.get('seq', '') # 更新seq

            elif current_priority == existing_priority and current_xml_node_type_simplified == 't':
                # 【同类型合并】如果都是换乘站，则合并 transferLines
                log_message("NORMAL", "节点信息合并", 
                            f"Merging transfer lines for existing node '{final_node_key}' (Type: 'T').", 
                            f"合并节点 '{final_node_key}' (类型: 'T') 的换乘线路。")
                if 'shmetro-osysi' in existing_node_object['attributes'] and \
                   'transferLines' in existing_node_object['attributes']['shmetro-osysi']:
                    for i in range(1, 7):
                        transfer_line_key = f"transfer_line_{i}"
                        if transfer_line_key in station_info and station_info[transfer_line_key] and \
                           station_info[transfer_line_key] not in existing_node_object['attributes']['shmetro-osysi']['transferLines']:
                            existing_node_object['attributes']['shmetro-osysi']['transferLines'].append(station_info[transfer_line_key])
                
                # 可以选择性更新其他通用属性，这里选择以最新数据为准
                existing_node_object['attributes']['color'] = station_info.get('color', '')
                existing_node_object['attributes']['direction'] = station_info.get('direction', '')
                existing_node_object['attributes']['Firm_Highway_Number'] = station_info.get('Firm_Highway_Number', '')
                existing_node_object['attributes']['seq'] = station_info.get('seq', '') # 更新seq

            else:
                # 【类型保持不变】当前优先级低于或等于现有优先级（且非T同类型合并）
                log_message("NORMAL", "节点去重 (坐标)", 
                            f"Skipping node update for key '{final_node_key}' as current type '{current_xml_node_type_simplified}' is not higher priority than '{existing_node_type_in_json_simplified}'.", 
                            f"由于当前类型 '{current_xml_node_type_simplified}' 优先级不高于现有类型 '{existing_node_type_in_json_simplified}'，跳过节点 '{final_node_key}' 的更新。")
            
            # 无论是否更新节点对象，都需要更新 original_xml_id 到 final_node_key 的映射
            node_id_to_key_map[original_xml_id] = final_node_key
            # 更新 seen_svg_coords_info 中的 info，以便存储最新的原始数据或合并后的状态
            seen_svg_coords_info[base_node_id_from_coords]['data'] = station_info # 存储当前行数据作为参考
            seen_svg_coords_info[base_node_id_from_coords]['line_color'] = line_color_for_edge
            seen_svg_coords_info[base_node_id_from_coords]['zh_name'] = station_name_zh
            seen_svg_coords_info[base_node_id_from_coords]['en_name'] = station_name_en

            # 跳过本次循环的节点创建部分，直接进入边生成逻辑
            continue # 确保不重复添加节点
        
        # 如果是新的SVG坐标，则创建新节点
        node_to_add = None 

        # 根据当前XML类型选择对应的模板，并填充数据
        node_full_type_name = get_full_node_type_name(current_xml_node_type_simplified)

        if current_xml_node_type_simplified == 'v':
            node_to_add = copy.deepcopy(node_templates.get('V'))
            if node_to_add:
                node_to_add['key'] = final_node_key # 带有前缀的key
                node_to_add['attributes']['id'] = original_xml_id
                node_to_add['attributes']['virtual'] = {}
            else:
                node_to_add = {
                    "key": final_node_key, "attributes": { "visible": True, "zIndex": 0, "x": 0, "y": 0, "type": "virtual", "virtual": {}, "id": original_xml_id }
                }
            node_to_add['attributes']['type'] = node_full_type_name

        elif current_xml_node_type_simplified == 's':
            node_to_add = copy.deepcopy(node_templates.get('S'))
            if node_to_add:
                node_to_add['key'] = final_node_key # 带有前缀的key
                node_to_add['attributes']['shmetro-basic']['names'] = [station_name_zh, station_name_en]
            else:
                node_to_add = {
                    "key": final_node_key, "attributes": { "visible": True, "zIndex": 0, "x": 0, "y": 0, "type": "shmetro-basic", "shmetro-basic": {"names": ["", ""], "nameOffsetX": "right", "nameOffsetY": "top"} }
                }
            node_to_add['attributes']['type'] = node_full_type_name

        elif current_xml_node_type_simplified == 't':
            node_to_add = copy.deepcopy(node_templates.get('T'))
            if node_to_add:
                node_to_add['key'] = final_node_key # 带有前缀的key
                node_to_add['attributes']['shmetro-osysi']['names'] = [station_name_zh, station_name_en]
                if 'line_transfer_info' in node_to_add['attributes']: del node_to_add['attributes']['line_transfer_info']
            else:
                node_to_add = {
                    "key": final_node_key, "attributes": { "visible": True, "zIndex": 0, "x": 0, "y": 0, "type": "shmetro-osysi", "shmetro-osysi": {"names": ["", ""], "nameOffsetX": "right", "nameOffsetY": "top"} }
                }
            node_to_add['attributes']['type'] = node_full_type_name

            # 添加换乘线路信息 (transfer_line_1 到 transfer_line_6)
            if 'shmetro-osysi' in node_to_add['attributes']:
                for i in range(1, 7):
                    transfer_line_key = f"transfer_line_{i}"
                    if transfer_line_key in station_info and station_info[transfer_line_key]:
                        if "transferLines" not in node_to_add["attributes"]["shmetro-osysi"]:
                            node_to_add["attributes"]["shmetro-osysi"]["transferLines"] = []
                        node_to_add["attributes"]["shmetro-osysi"]["transferLines"].append(station_info[transfer_line_key])

        else: # 未知或空类型，默认为普通站点 'shmetro-basic'
            log_message("WARNING", "处理错误", 
                        f"Station '{station_name_zh or line_name}_{seq}' has unknown or empty type '{current_xml_node_type_raw}'. Defaulting to 'shmetro-basic'.", 
                        f"站点 '{station_name_zh or line_name}_{seq}' 类型 '{current_xml_node_type_raw}' 未知或为空。默认为 'shmetro-basic' 类型。")
            node_to_add = copy.deepcopy(node_templates.get('S')) if node_templates.get('S') else {
                "key": final_node_key, "attributes": { "visible": True, "zIndex": 0, "x": 0, "y": 0, "type": "shmetro-basic", "shmetro-basic": {"names": ["", ""], "nameOffsetX": "right", "nameOffsetY": "top"} }
            }
            node_to_add['attributes']['type'] = 'shmetro-basic' # Fallback to full type name
            node_to_add['attributes']['shmetro-basic']['names'] = [station_name_zh, station_name_en] # Fixed: station_en_name to station_name_en

        # 确保移除不必要的reconcileId (如果模板中存在)
        if 'reconcileId' in node_to_add['attributes']: del node_to_add['attributes']['reconcileId']

        # 设置节点的x, y坐标为转换后的SVG坐标
        node_to_add['attributes']['x'] = svg_x
        node_to_add['attributes']['y'] = svg_y

        # 添加其他额外的属性，如果XML中存在
        for key, value in station_info.items():
            if key not in ['id', 'x', 'y', 'name', 'name_zh', 'name_en', 'type', 'color', 'direction', 'seq', 'Firm_Highway_Number', 'transfer_line_1', 'transfer_line_2', 'transfer_line_3', 'transfer_line_4', 'transfer_line_5', 'transfer_line_6']:
                node_to_add["attributes"][key] = value

        # 添加color, direction, seq, Firm_Highway_Number到attributes
        node_to_add["attributes"]["color"] = station_info.get('color', '')
        node_to_add["attributes"]["direction"] = station_info.get('direction', '')
        node_to_add["attributes"]["seq"] = station_info.get('seq', '')
        node_to_add["attributes"]["Firm_Highway_Number"] = station_info.get('Firm_Highway_Number', '')


        new_nodes.append(node_to_add) # 将新创建的节点添加到列表中

        log_message("NORMAL", "节点创建", 
                    f"Created NEW node (based on SVG coords) for '{station_name_zh}' (Type: {node_to_add['attributes']['type']}, Key: {final_node_key}, SVG_X:{svg_x}, SVG_Y:{svg_y}). Original XML ID: {original_xml_id}",
                    f"基于SVG坐标创建了新节点 '{station_name_zh}' (类型: {node_to_add['attributes']['type']}, 键: {final_node_key}, SVG_X:{svg_x}, SVG_Y:{svg_y})。原始XML ID: {original_xml_id}")

        # 记录新创建的节点信息
        seen_svg_coords_info[base_node_id_from_coords] = { # 用不带前缀的基础ID作为key
            'node_object': node_to_add, # 存储对实际节点对象的引用
            'data': station_info,
            'line_color': line_color_for_edge,
            'zh_name': station_name_zh,
            'en_name': station_name_en
        }
        node_id_to_key_map[original_xml_id] = final_node_key # 将原始XML ID映射到最终节点key (带前缀)
        
    # --- 边生成逻辑 ---
    # 重新遍历 actual_station_data_rows，这次只为生成边。
    # 这样可以确保在生成边时，所有节点都已经被处理完毕，并且它们的类型和key都是最终确定的。
    for station_info in actual_station_data_rows: 
        line_name = station_info.get('name')
        original_xml_id = station_info.get('id')
        
        # 为了确保边的颜色是正确的线路颜色，这里应该从 line_colors 字典中获取
        # 或者从已经处理过的节点信息中获取 (如果节点颜色被优先级覆盖，则使用最终的节点颜色)
        # 考虑到边的颜色通常代表线路本身，使用line_colors字典更合适。
        current_line_color = line_colors.get(line_name, '#000000') # 优先使用线路标题中提取的颜色

        if line_name not in last_station_info_by_line:
            last_station_info_by_line[line_name] = None

        if last_station_info_by_line[line_name] is not None:
            prev_station_info = last_station_info_by_line[line_name]
            
            edge = copy.deepcopy(edge_template_from_model)
            
            prev_original_xml_id = prev_station_info.get('id')
            current_original_xml_id = original_xml_id

            # 从 node_id_to_key_map 中获取源节点和目标节点的最终key
            source_node_key_for_edge = node_id_to_key_map.get(prev_original_xml_id)
            target_node_key_for_edge = node_id_to_key_map.get(current_original_xml_id)

            if source_node_key_for_edge and target_node_key_for_edge:
                edge_key = f"line_{prev_original_xml_id}_{current_original_xml_id}" 
                
                edge['key'] = edge_key
                edge['source'] = source_node_key_for_edge
                edge['target'] = target_node_key_for_edge
                
                if 'single-color' not in edge['attributes']: edge['attributes']['single-color'] = {}
                if 'color' not in edge['attributes']['single-color'] or not isinstance(edge['attributes']['single-color']['color'], list) or len(edge['attributes']['single-color']['color']) < 4:
                    edge['attributes']['single-color']['color'] = ["other", "other", "#000000", "#FFFFFF"] 
                
                # 【核心修正】确保边的颜色使用线路的实际颜色
                edge['attributes']['single-color']['color'][2] = current_line_color 
                
                if 'line_name' in edge['attributes']: del edge['attributes']['line_name']
                if 'color' in edge['attributes']: del edge['attributes']['color']
                
                edge['attributes']['reconcileId'] = edge_key

                new_edges.append(edge)
                log_message("NORMAL", "边创建", 
                            f"Created edge for '{line_name}' from {prev_station_info.get('name_zh', prev_station_info.get('name', ''))} (Key: {source_node_key_for_edge}) to {station_info.get('name_zh', line_name)} (Key: {target_node_key_for_edge}). Color: {current_line_color}", # Added color to log
                            f"为线路 '{line_name}' 创建了从 {prev_station_info.get('name_zh', prev_station_info.get('name', ''))} (键: {source_node_key_for_edge}) 到 {station_info.get('name_zh', line_name)} (键: {target_node_key_for_edge}) 的边。颜色: {current_line_color}")
            else:
                log_message("WARNING", "边创建错误",
                          f"Could not find source ({prev_original_xml_id}) or target ({current_original_xml_id}) node key for edge '{line_name}'. Skipping edge creation.",
                          f"无法为线路 '{line_name}' 的边找到源 ({prev_original_xml_id}) 或目标 ({current_original_xml_id}) 节点的键。跳过边创建。")

        # 更新当前线路的最后一个站点信息为当前处理的站点
        last_station_info_by_line[line_name] = station_info 

    # --- 最终JSON结构组装 ---
    json_data['graph']['nodes'] = new_nodes
    json_data['graph']['edges'] = new_edges

    # 动态计算 svgViewBoxMin 和 svgViewBoxZoom
    center_x_data = (min_lon + max_lon) / 2
    center_y_data = (min_lat + max_lat) / 2

    max_data_span = max(max_lon - min_lon, max_lat - min_lat)
    if max_data_span == 0:
        max_data_span = 0.0001

    calculated_zoom = NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC / max_data_span
    json_data["svgViewBoxZoom"] = max(MIN_ZOOM_VALUE, min(MAX_ZOOM_VALUE, calculated_zoom))
    log_message("INFO", "SVG参数", f"Calculated svgViewBoxZoom: {json_data['svgViewBoxZoom']}", f"计算得到svgViewBoxZoom: {json_data['svgViewBoxZoom']}")

    actual_viewbox_coord_span = NOMINAL_VIEWBOX_SIZE_FOR_ZOOM_CALC / json_data["svgViewBoxZoom"]

    calculated_min_x = center_x_data - (actual_viewbox_coord_span / 2)
    calculated_min_y = center_y_data - (actual_viewbox_coord_span / 2)

    json_data["svgViewBoxMin"]["x"] = max(MIN_VIEWBOX_MIN_COORD, min(MAX_VIEWBOX_MIN_COORD, calculated_min_x))
    json_data["svgViewBoxMin"]["y"] = max(MIN_VIEWBOX_MIN_COORD, min(MAX_VIEWBOX_MIN_COORD, calculated_min_y))

    log_message("INFO", "SVG参数", f"Calculated svgViewBoxMin.x: {json_data['svgViewBoxMin']['x']}", f"计算得到svgViewBoxMin.x: {json_data['svgViewBoxMin']['x']}")
    log_message("INFO", "SVG参数", f"Calculated svgViewBoxMin.y: {json_data['svgViewBoxMin']['y']}", f"计算得到svgViewBoxMin.y: {json_data['svgViewBoxMin']['y']}")
    
    return json.dumps(json_data, indent=4, ensure_ascii=False)


# --- 日志记录函数 (与主处理函数中的log_message区分开，用于独立运行模式) ---
def log_message(level, log_type, message_en, message_cn):
    """
    记录不同级别的日志信息到每日文件中。
    日志文件将按日期命名，并存放在 D:\map_maker\output\logs 目录下。
    """
    log_directory = r"D:\map_maker\json_output\json_producer_logs" 
    try:
        os.makedirs(log_directory, exist_ok=True) 
    except OSError as e:
        print(f"ERROR: Failed to create log directory '{log_directory}': {e}")
        print(f"Original Log Message (failed to write to file): [{level}] {log_type} - EN: {message_en} | CN: {message_cn}")
        return 

    today_date = datetime.datetime.now().strftime("%Y-%m-%d") 
    log_file_name = f"JSON_producer_log_{today_date}.txt"
    log_file_path = os.path.join(log_directory, log_file_name)

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") 

    log_entry = f"[{current_time}] Level: {level}, Type: {log_type}\n" \
                f"    English Message: {message_en}\n" \
                f"    中文解释: {message_cn}\n\n"

    try:
        with open(log_file_path, "a", encoding="utf-8") as f: 
            f.write(log_entry)
    except Exception as e:
        print(f"Failed to write log to file '{log_file_path}': {e}")
        print(f"Original Log Message (failed to write to file): {log_entry}")


# --- 文件选择和执行逻辑 ---
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    current_dir = os.path.dirname(os.path.abspath(__file__)) 

    try:
        xml_file_path = filedialog.askopenfilename(
            title="请选择 XML数据表 (Excel XML)", 
            filetypes=[("XML files", "*.xml")],
            initialdir=current_dir
        )
        if not xml_file_path: 
            messagebox.showinfo("取消", "XML文件选择已取消。")
            log_message("NORMAL", "用户行为", "XML file selection cancelled by user.", "用户取消了XML文件选择。")
            exit()

        json_template_path = filedialog.askopenfilename(
            title="请选择 JSON模板文件", 
            filetypes=[("JSON files", "*.json")],
            initialdir=current_dir
        )
        if not json_template_path: 
            messagebox.showinfo("取消", "JSON模板文件选择已取消。")
            log_message("NORMAL", "用户行为", "JSON template file selection cancelled by user.", "用户取消了JSON模板文件选择。")
            exit()

        if not os.path.exists(xml_file_path):
            error_msg_en = f"XML file not found: {xml_file_path}"
            error_msg_cn = f"XML文件不存在: {xml_file_path}"
            log_message("ERROR", "文件错误", error_msg_en, error_msg_cn)
            messagebox.showerror("文件错误", error_msg_cn)
            exit()
        if not os.path.exists(json_template_path):
            error_msg_en = f"JSON template file not found: {json_template_path}"
            error_msg_cn = f"JSON模板文件不存在: {json_template_path}"
            log_message("ERROR", "文件错误", error_msg_en, error_msg_cn)
            messagebox.showerror("文件错误", error_msg_cn)
            exit()

        with open(xml_file_path, 'r', encoding='utf-8') as f: 
            xml_content = f.read()
            log_message("NORMAL", "文件读取", f"Successfully read XML file: {xml_file_path}", f"成功读取XML文件: {xml_file_path}")
        with open(json_template_path, 'r', encoding='utf-8') as f: 
            json_template_content = f.read()
            log_message("NORMAL", "文件读取", f"Successfully read JSON template file: {json_template_path}", f"成功读取JSON模板文件: {json_template_path}") # Fixed this line in logging

        log_message("NORMAL", "处理开始", "Starting data processing from XML to JSON.", "开始将XML数据处理为JSON。")
        output_json_string = process_highway_data(xml_content, json_template_content)
        log_message("NORMAL", "处理完成", "Data processing completed successfully.", "数据处理成功完成。")
        
        output_directory = r"D:\map_maker\json_output"
        
        if not os.path.exists(output_directory):
            try:
                os.makedirs(output_directory)
                log_message("NORMAL", "目录创建", f"Output directory created: {output_directory}", f"输出目录已创建: {output_directory}")
            except OSError as e:
                error_msg_en = f"Failed to create output directory '{output_directory}': {e}"
                error_msg_cn = f"创建输出文件夹 '{output_directory}' 失败: {e}"
                log_message("ERROR", "输出文件夹创建错误", error_msg_en, error_msg_cn)
                messagebox.showerror("输出文件夹错误", error_msg_cn)
                exit()
        else:
            log_message("NORMAL", "目录检查", f"Output directory already exists: {output_directory}", f"输出目录已存在: {output_directory}")

        base_xml_filename = os.path.splitext(os.path.basename(xml_file_path))[0]
        output_file_name = os.path.join(output_directory, f"{base_xml_filename}.json")
        
        with open(output_file_name, "w", encoding="utf-8") as f: 
            f.write(output_json_string)
            log_message("NORMAL", "操作成功", f"JSON file successfully generated and saved to: {output_file_name}", f"JSON文件已成功生成并保存到: {output_file_name}")
        
        messagebox.showinfo("完成", f"JSON文件已成功生成并保存到:\n{output_file_name}")

    except FileNotFoundError as e:
        error_msg_en = f"File not found during operation: {e.filename}"
        error_msg_cn = f"操作过程中未找到文件: {e.filename}"
        log_message("ERROR", "文件错误", error_msg_en, error_msg_cn)
        messagebox.showerror("文件错误", error_msg_cn)
    except json.JSONDecodeError as e:
        error_msg_en = f"Error decoding JSON template: {e}"
        error_msg_cn = f"解析JSON模板时出错: {e}"
        log_message("ERROR", "处理错误 (JSON)", error_msg_en, error_msg_cn)
        messagebox.showerror("处理错误", error_msg_cn)
    except ET.ParseError as e:
        error_msg_en = f"Error parsing XML file: {e}"
        error_msg_cn = f"解析XML文件时出错: {e}"
        log_message("ERROR", "处理错误 (XML)", error_msg_en, error_msg_cn)
        messagebox.showerror("处理错误", error_msg_cn)
    except ValueError as e:
        error_msg_en = f"A data processing value error occurred: {e}"
        error_msg_cn = f"数据处理值错误: {e}"
        log_message("ERROR", "数据处理错误", error_msg_en, error_msg_cn)
        messagebox.showerror("处理错误", error_msg_cn)
    except Exception as e:
        error_msg_en = f"An unexpected error occurred: {type(e).__name__} - {e}"
        error_msg_cn = f"发生了一个未预期的错误: {type(e).__name__} - {e}"
        log_message("ERROR", "未处理错误", error_msg_en, error_msg_cn) # Fixed: error_cn to error_msg_cn
        messagebox.showerror("错误", error_msg_cn)

