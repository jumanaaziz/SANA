import json
import heapq
import time


def load_map(file_path="map.json"):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def build_graph(map_data):
    graph = {}

    for node in map_data["nodes"]:
        graph[node["nodeId"]] = []

    for edge in map_data["edges"]:
        from_node = edge["fromNodeId"]
        to_node = edge["toNodeId"]
        distance = edge["distance"]

        graph[from_node].append((to_node, distance))
        graph[to_node].append((from_node, distance))

    return graph


def find_destination_node(map_data, destination_name):
    destination_name = destination_name.lower().strip()

    for room in map_data["rooms"]:
        if room["name"].lower().strip() == destination_name:
            return room["nodeId"]

    return None


def get_node(map_data, node_id):
    for node in map_data["nodes"]:
        if node["nodeId"] == node_id:
            return node
    return None


def dijkstra(graph, start_node, goal_node):
    queue = [(0, start_node, [])]
    visited = set()

    while queue:
        total_distance, current_node, path = heapq.heappop(queue)

        if current_node in visited:
            continue

        visited.add(current_node)
        path = path + [current_node]

        if current_node == goal_node:
            return path, total_distance

        for neighbor, distance in graph[current_node]:
            if neighbor not in visited:
                heapq.heappush(
                    queue,
                    (total_distance + distance, neighbor, path)
                )

    return None, None


def get_direction(from_node, to_node):
    dx = to_node["x"] - from_node["x"]
    dy = to_node["y"] - from_node["y"]

    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    else:
        return "north" if dy > 0 else "south"


def get_turn_instruction(current_heading, new_heading):
    directions = ["north", "east", "south", "west"]

    old_index = directions.index(current_heading)
    new_index = directions.index(new_heading)

    difference = (new_index - old_index) % 4

    if difference == 0:
        return "استمر للأمام"
    elif difference == 1:
        return "انعطف يمين"
    elif difference == 3:
        return "انعطف يسار"
    else:
        return "استدر للخلف"


def get_edge_info(map_data, from_node_id, to_node_id):
    for edge in map_data["edges"]:
        same_direction = (
            edge["fromNodeId"] == from_node_id and
            edge["toNodeId"] == to_node_id
        )

        opposite_direction = (
            edge["fromNodeId"] == to_node_id and
            edge["toNodeId"] == from_node_id
        )

        if same_direction or opposite_direction:
            return edge

    return None


def get_edge_steps(map_data, from_node_id, to_node_id):
    edge = get_edge_info(map_data, from_node_id, to_node_id)

    if edge is not None:
        return edge["steps"]

    return 0


def get_edge_time(map_data, from_node_id, to_node_id):
    edge = get_edge_info(map_data, from_node_id, to_node_id)

    if edge is not None:
        return edge["timeSeconds"]

    return 0


def get_step_word(steps):
    if steps == 1:
        return "خطوة"
    elif steps == 2:
        return "خطوتين"
    else:
        return "خطوات"


def generate_instructions(map_data, route, start_heading="north"):
    instructions = []
    current_heading = start_heading

    for i in range(len(route) - 1):
        current_node = get_node(map_data, route[i])
        next_node = get_node(map_data, route[i + 1])

        new_heading = get_direction(current_node, next_node)
        turn_text = get_turn_instruction(current_heading, new_heading)

        steps = get_edge_steps(map_data, route[i], route[i + 1])
        step_word = get_step_word(steps)

        time_seconds = get_edge_time(map_data, route[i], route[i + 1])

        instructions.append(
            f"{turn_text} ثم امشِ {steps} {step_word}. الوقت المتوقع {time_seconds} ثانية"
        )

        current_heading = new_heading

    instructions.append("وصلت إلى الوجهة")
    return instructions


def navigate(current_node_id, destination_name, start_heading="north"):
    map_data = load_map()

    destination_node = find_destination_node(map_data, destination_name)

    if destination_node is None:
        return None, None, ["لم يتم العثور على الوجهة"]

    graph = build_graph(map_data)

    route, total_distance = dijkstra(
        graph,
        current_node_id,
        destination_node
    )

    if route is None:
        return None, None, ["لا يوجد مسار متاح لهذه الوجهة"]

    instructions = generate_instructions(
        map_data,
        route,
        start_heading
    )

    return route, total_distance, instructions


def navigate_step_by_step(current_node_id, destination_name, start_heading="north"):
    map_data = load_map()

    destination_node = find_destination_node(map_data, destination_name)

    if destination_node is None:
        print("لم يتم العثور على الوجهة")
        return current_node_id

    graph = build_graph(map_data)

    route, total_distance = dijkstra(
        graph,
        current_node_id,
        destination_node
    )

    if route is None:
        print("لا يوجد مسار متاح لهذه الوجهة")
        return current_node_id

    current_heading = start_heading

    for i in range(len(route) - 1):
        current_node = get_node(map_data, route[i])
        next_node = get_node(map_data, route[i + 1])

        edge = get_edge_info(map_data, route[i], route[i + 1])

        if edge is None:
            print("حدث خطأ في المسار")
            return current_node_id

        new_heading = get_direction(current_node, next_node)
        turn_text = get_turn_instruction(current_heading, new_heading)

        steps = edge["steps"]
        step_word = get_step_word(steps)

        time_seconds = edge["timeSeconds"]

        print(f"{turn_text} ثم امشِ {steps} {step_word}")

        time.sleep(time_seconds)

        current_node_id = route[i + 1]
        current_heading = new_heading

    print("وصلت إلى الوجهة")

    return current_node_id