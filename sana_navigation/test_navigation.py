from navigation_engine import navigate_step_by_step

current_location = "N1"
current_heading = "north"

current_location = navigate_step_by_step(
    current_node_id=current_location,
    destination_name="Classroom 44",
    start_heading=current_heading
)

print("Current location after navigation:", current_location)