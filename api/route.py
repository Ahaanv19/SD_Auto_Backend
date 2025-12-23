from flask import Blueprint, request
from flask_restful import Api, Resource
import requests
import re
from .traffic import calculate_route_adjustment, get_traffic_level

# Blueprint and API init
routes_api = Blueprint('routes', __name__, url_prefix='')
api = Api(routes_api)

# Replace with your actual API key
API_KEY = 'AIzaSyC0qOeOkWMCMxT0bMAdpQzZesBsZ-zaFOM'


def strip_html(text):
    """Remove HTML tags from Google Maps instructions."""
    return re.sub(r'<[^>]*>', '', text)


def format_duration(minutes):
    """Format duration in minutes to human-readable string."""
    if minutes < 60:
        return f"{minutes:.0f} mins"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    if mins == 0:
        return f"{hours} hr"
    return f"{hours} hr {mins} mins"


class RoutesAPI:
    class _GetRoutes(Resource):
        def post(self):
            try:
                data = request.get_json()
                origin = data.get('origin')
                destination = data.get('destination')
                mode = data.get('mode', 'driving')
                include_traffic_details = data.get('include_traffic_details', False)

                if not origin or not destination:
                    return {'error': 'Origin and destination are required'}, 400

                # Request to Google Directions API with traffic info
                url = (
                    f"https://maps.googleapis.com/maps/api/directions/json?"
                    f"origin={origin}&destination={destination}&alternatives=true"
                    f"&mode={mode}&departure_time=now&key={API_KEY}"
                )

                response = requests.get(url)
                directions_data = response.json()

                if directions_data.get('status') != 'OK':
                    return {'error': directions_data.get('status', 'Unknown error')}, 500

                routes = directions_data['routes']
                route_info = []

                for route in routes:
                    leg = route['legs'][0]
                    steps = leg['steps']
                    route_details = []
                    total_duration_sec = 0

                    for step in steps:
                        instruction = strip_html(step['html_instructions'])
                        distance = step['distance']['text']
                        duration = step['duration']['text']
                        duration_val = step['duration']['value']
                        total_duration_sec += duration_val

                        route_details.append({
                            'instruction': instruction,
                            'distance': distance,
                            'duration': duration,
                            'duration_seconds': duration_val
                        })

                    # Calculate traffic-based adjustment using our dataset
                    traffic_adjustment = calculate_route_adjustment(route_details)
                    
                    # Base duration from Google
                    base_duration_min = total_duration_sec / 60
                    
                    # Apply our traffic multiplier
                    adjusted_duration_min = base_duration_min * traffic_adjustment['multiplier']
                    
                    # Also check if Google provided duration_in_traffic
                    google_traffic_duration = None
                    if 'duration_in_traffic' in leg:
                        google_traffic_duration = leg['duration_in_traffic']['value'] / 60

                    # Build route response
                    route_data = {
                        'details': route_details,
                        'total_duration': leg['duration']['text'],
                        'total_duration_seconds': leg['duration']['value'],
                        'total_distance': leg['distance']['text'],
                        'geometry': route['overview_polyline']['points'],
                        
                        # Traffic-adjusted duration based on SD traffic data
                        'traffic_adjusted_duration': format_duration(adjusted_duration_min),
                        'traffic_adjusted_seconds': int(adjusted_duration_min * 60),
                        
                        # Traffic analysis metadata
                        'traffic_analysis': {
                            'multiplier': traffic_adjustment['multiplier'],
                            'confidence': traffic_adjustment['confidence'],
                            'streets_analyzed': traffic_adjustment['streets_matched']
                        }
                    }
                    
                    # Optionally include detailed street-by-street traffic info
                    if include_traffic_details:
                        route_data['traffic_analysis']['street_details'] = traffic_adjustment['street_details']
                    
                    # Include Google's traffic estimate if available
                    if google_traffic_duration:
                        route_data['google_traffic_duration'] = format_duration(google_traffic_duration)
                        route_data['google_traffic_seconds'] = int(google_traffic_duration * 60)

                    route_info.append(route_data)

                return route_info, 200

            except Exception as e:
                return {'error': str(e)}, 500


    class _GetTrafficForStreet(Resource):
        """Get traffic information for a specific street."""
        def get(self):
            street = request.args.get('street', '')
            if not street:
                return {'error': 'Street parameter required'}, 400
            
            level, multiplier, count = get_traffic_level(street)
            return {
                'street': street,
                'traffic_level': level,
                'congestion_multiplier': multiplier,
                'daily_vehicle_count': count
            }, 200


    # Route registration
    api.add_resource(_GetRoutes, '/get_routes')
    api.add_resource(_GetTrafficForStreet, '/street_traffic')







