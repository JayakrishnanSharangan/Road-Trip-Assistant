from flask import Flask, render_template, request, jsonify
import requests
import folium
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# Ensure static directory exists
if not os.path.exists("static"):
    os.makedirs("static")

NOMINATIM_API = "https://nominatim.openstreetmap.org/search"
OSRM_ROUTE_API = "http://router.project-osrm.org/route/v1/driving"
OVERPASS_API = "http://overpass-api.de/api/interpreter"

def get_coordinates(place):
    headers = {"User-Agent": "RoadTripApp/1.0"}
    params = {"q": place, "format": "json"}
    try:
        response = requests.get(NOMINATIM_API, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data:
            print(f"No results found for: {place}")
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching coordinates for {place}: {e}")
        return None

def get_route_details(start_coords, end_coords):
    route_url = f"{OSRM_ROUTE_API}/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=full&geometries=geojson"
    try:
        response = requests.get(route_url)
        response.raise_for_status()
        route_data = response.json()
        if "routes" not in route_data or not route_data["routes"]:
            return None
        route = route_data["routes"][0]
        geometry = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
        distance = route.get("distance", 0)  # meters
        duration = route.get("duration", 0)  # seconds
        return {
            "geometry": geometry,
            "distance": distance,
            "duration": duration
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching route data: {e}")
        return None

def fetch_attractions_at_point(lat, lon, radius=10000):
    query = f"""
    [out:json];
    (
        node(around:{radius},{lat},{lon})[tourism~"attraction|museum|viewpoint"][name];
        way(around:{radius},{lat},{lon})[tourism~"attraction|museum|viewpoint"][name];
    );
    out center;
    """
    headers = {"User-Agent": "RoadTripApp/1.0"}
    point_attractions = []
    try:
        response = requests.post(OVERPASS_API, data=query, headers=headers, timeout=8)
        response.raise_for_status()
        data = response.json()
        for element in data.get("elements", []):
            tags = element.get("tags", {})
            name = tags.get("name")
            category = tags.get("tourism", "attraction")
            elat = element.get("lat") or element.get("center", {}).get("lat")
            elon = element.get("lon") or element.get("center", {}).get("lon")
            if name and elat and elon:
                point_attractions.append({
                    "name": name,
                    "lat": float(elat),
                    "lon": float(elon),
                    "type": category
                })
    except requests.exceptions.RequestException as e:
        print(f"Error fetching attractions at ({lat}, {lon}): {e}")
    return point_attractions

def get_attractions_along_route(route_coords, radius=10000, max_queries=10):
    total_points = len(route_coords)
    if total_points == 0:
        return []

    indices = [int(i * total_points / max_queries) for i in range(max_queries)]
    unique_attractions = {}

    print(f"Starting parallel Overpass queries for {len(indices)} points along the route...")
    with ThreadPoolExecutor(max_workers=max_queries) as executor:
        futures = {
            executor.submit(fetch_attractions_at_point, route_coords[idx][0], route_coords[idx][1], radius): idx
            for idx in indices
        }
        for future in as_completed(futures):
            try:
                results = future.result()
                for attr in results:
                    # De-duplicate based on name and rounded coords
                    key = (attr["name"], round(attr["lat"], 4), round(attr["lon"], 4))
                    if key not in unique_attractions:
                        unique_attractions[key] = attr
            except Exception as e:
                print(f"Thread execution failed: {e}")

    attractions_list = list(unique_attractions.values())
    print(f"Finished. Found {len(attractions_list)} unique attractions.")
    return attractions_list

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/route")
def get_route():
    start_place = request.args.get("start")
    end_place = request.args.get("end")
    if not start_place or not end_place:
        return jsonify({"error": "Missing start or end location"}), 400

    start_coords = get_coordinates(start_place)
    end_coords = get_coordinates(end_place)
    if not start_coords or not end_coords:
        return jsonify({"error": "Could not determine coordinates for given locations"}), 400

    route_details = get_route_details(start_coords, end_coords)
    if not route_details:
        return jsonify({"error": "No route found"}), 404
    
    route_coords = route_details["geometry"]
    attractions = get_attractions_along_route(route_coords)

    # Legacy Folium map creation for backward compatibility
    map_ = folium.Map(location=start_coords, zoom_start=6)
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(map_)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(map_)
    folium.PolyLine(route_coords, color="blue", weight=5).add_to(map_)

    for attr in attractions:
        folium.Marker(location=(attr["lat"], attr["lon"]), tooltip=attr["name"], icon=folium.Icon(color="purple")).add_to(map_)

    map_.save("static/map.html")
    return render_template("map.html")

@app.route("/api/route")
def api_route():
    start_place = request.args.get("start")
    end_place = request.args.get("end")
    if not start_place or not end_place:
        return jsonify({"error": "Missing start or end location"}), 400

    start_coords = get_coordinates(start_place)
    end_coords = get_coordinates(end_place)
    if not start_coords or not end_coords:
        return jsonify({"error": "Could not determine coordinates for given locations"}), 400

    route_details = get_route_details(start_coords, end_coords)
    if not route_details:
        return jsonify({"error": "No route found"}), 404

    route_coords = route_details["geometry"]
    attractions = get_attractions_along_route(route_coords)

    return jsonify({
        "start": {
            "name": start_place,
            "coords": start_coords
        },
        "end": {
            "name": end_place,
            "coords": end_coords
        },
        "geometry": route_coords,
        "distance": route_details["distance"],
        "duration": route_details["duration"],
        "attractions": attractions
    })

if __name__ == '__main__':
    # CRITICAL: Binding to '0.0.0.0' opens the container's network interface
    # This allows the Kubernetes readiness probe to see and verify the app's health
    app.run(host='0.0.0.0', port=5000, debug=False)
