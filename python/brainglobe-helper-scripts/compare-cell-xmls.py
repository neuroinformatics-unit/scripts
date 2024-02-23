from brainglobe_utils.IO.cells import get_cells
from pathlib import Path
from typing import Set
import numpy as np
from numpy.typing import NDArray
old_cells  = get_cells(str(Path("/media/ceph-neuroinformatics/neuroinformatics/afelder/barnabas_old_cellfinder_cells.xml")))
new_cells  = get_cells(str(Path("/media/ceph-neuroinformatics/neuroinformatics/afelder/barnabas_cells.xml")))

old_set = set()
[old_set.add((cell.z, cell.y, cell.x)) for cell in old_cells]

new_set = set()
[new_set.add((cell.z, cell.y, cell.x)) for cell in new_cells]

in_new_only = new_set - old_set
in_old_only = old_set - new_set

print(f"{len(in_new_only)} cells only in new ")
print(f"{len(in_old_only)} cells only in old ")

def check_closest_point_in_other_set(point_of_interest: NDArray, other_set: Set):
    closest_point_index = np.argmin([np.linalg.norm(point_of_interest - np.array([point.z, point.y, point.x])) for point in other_set])
    closest_point = other_set[closest_point_index]
    distance_to_closest_point = np.linalg.norm(point_of_interest - np.array([closest_point.z, closest_point.y, closest_point.x]))
    return distance_to_closest_point

distances = []
weird_points = []
for point in in_new_only:
    distance = check_closest_point_in_other_set(np.array(list(point)), old_cells)
    distances.append(distance)
    tolerance = 2 # in microns
    if distance > tolerance:
        #print(f"Point {point} is more than {tolerance} um away from nearest point in other set: {distance} um")
        weird_points.append(point)

print(weird_points)
print(f"there are {len(weird_points)} weird points")


distances = []
weird_points = []
for point in in_old_only:
    distance = check_closest_point_in_other_set(np.array(list(point)), new_cells)
    distances.append(distance)
    tolerance = 2 # in microns
    if distance > tolerance:
        print(f"Point {point} is more than {tolerance} um away from nearest point in other set: {distance} um")
        weird_points.append(point)

print(weird_points)
print(f"there are {len(weird_points)} weird points")
