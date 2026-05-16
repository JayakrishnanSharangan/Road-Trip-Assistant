from flask import Flask, render_template, request, jsonify
import requests
import folium
import os

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

def get_route_coordinates(start_coords, end_coords):
    route_url = f"{OSRM_ROUTE_API}/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=full&geometries=geojson"
    try:
        response = requests.get(route_url)
        response.raise_for_status()
        route_data = response.json()
        if "routes" not in route_data or not route_data["routes"]:
            return None
        return [(lat, lon) for lon, lat in route_data["routes"][0]["geometry"]["coordinates"]]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching route data: {e}")
        return None

def get_attractions_along_route(route_coords, radius=10000, max_queries=10):
    attractions = []
    total_points = len(route_coords)
    if total_points == 0:
        return []

    indices = [int(i * total_points / max_queries) for i in range(max_queries)]
    
    for idx in indices:
        lat, lon = route_coords[idx]
        query = f"""
        [out:json];
        (
            node(around:{radius},{lat},{lon})[tourism~"attraction|museum|viewpoint"][name];
            way(around:{radius},{lat},{lon})[tourism~"attraction|museum|viewpoint"][name];
        );
        out center;
        """
        headers = {"User-Agent": "RoadTripApp/1.0"}
        try:
            response = requests.post(OVERPASS_API, data=query, headers=headers)
            response.raise_for_status()
            data = response.json()
            for element in data.get("elements", []):
                name = element.get("tags", {}).get("name")
                elat = element.get("lat") or element.get("center", {}).get("lat")
                elon = element.get("lon") or element.get("center", {}).get("lon")
                if name and elat and elon:
                    attractions.append((name, elat, elon))
        except requests.exceptions.RequestException as e:
            print(f"Error fetching attractions: {e}")

    print(f"Found {len(attractions)} attractions in {len(indices)} Overpass queries")
    return attractions

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

    route_coords = get_route_coordinates(start_coords, end_coords)
    if not route_coords:
        return jsonify({"error": "No route found"}), 404

    attractions = get_attractions_along_route(route_coords)

    # Create map
    map_ = folium.Map(location=start_coords, zoom_start=6)
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(map_)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(map_)
    folium.PolyLine(route_coords, color="blue", weight=5).add_to(map_)

    for name, lat, lon in attractions:
        folium.Marker(location=(lat, lon), tooltip=name, icon=folium.Icon(color="purple")).add_to(map_)

    map_.save("static/map.html")
    return render_template("map.html")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
