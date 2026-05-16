from navigation_engine import navigate

current_node = "N1"
destination = "Classroom 44"
heading = "south"

route, distance, instructions = navigate(
    current_node,
    destination,
    heading
)

print("Route:", route)
print("Total distance:", distance, "meters")
print("\nInstructions:")

for instruction in instructions:
    print("-", instruction)