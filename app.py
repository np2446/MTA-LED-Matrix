#!/usr/bin/env python3
"""
LED Matrix Display Controller
Web interface for controlling Sports, News, and MTA displays on RGB LED Matrix
"""

from flask import Flask, render_template, request, jsonify
import os
import time
import threading
import logging
import csv
from typing import Optional, Dict, Any, List

# Import display modules
from advanced_matrix_display import AdvancedMatrixDisplay
from sports_ticker import SportsTicker
from news_ticker import NewsTicker
from mta_ticker import MTADisplay

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'led-matrix-controller-2024'

# Global variables for display management
current_display = None
display_thread = None
matrix_display = None
display_lock = threading.Lock()
current_app = None
current_settings = {}

# Hardcoded API keys
ODDS_API_KEY = ''
NEWS_API_KEY = ''

# Load MTA station data
STATIONS = {}

def load_stations():
    """Load MTA stations from CSV or create default list"""
    global STATIONS
    
    # Default station list
    default_stations = {
        '127': 'Times Sq-42 St',
        '631': 'Grand Central-42 St',
        '635': '14 St-Union Sq',
        '640': 'Brooklyn Bridge-City Hall',
        'R31': 'Atlantic Av-Barclays Ctr',
        'R20': '14 St-Union Sq',
        'R16': 'Times Sq-42 St',
        'R13': '5 Av/59 St',
        'R11': 'Lexington Av/59 St',
        'R01': 'Astoria-Ditmars Blvd'
    }
    
    try:
        if os.path.exists('stations.csv'):
            with open('stations.csv', 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    STATIONS[row['GTFS Stop ID']] = row['Stop Name']
        else:
            STATIONS = default_stations
        logger.info(f"Loaded {len(STATIONS)} stations")
    except Exception as e:
        logger.error(f"Error loading stations: {e}")
        STATIONS = default_stations

# Initialize stations on startup
load_stations()

def initialize_display():
    """Initialize the RGB Matrix display"""
    global matrix_display
    
    if matrix_display is None:
        try:
            matrix_display = AdvancedMatrixDisplay(
                rows=32,
                cols=64,
                chain_length=1,
                parallel=1,
                brightness=75,
                hardware_mapping='adafruit-hat',
                gpio_slowdown=2
            )
            logger.info("Display initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")
            return False
    return True

def stop_current_display():
    """Stop the currently running display"""
    global current_display, display_thread, current_app
    
    with display_lock:
        if current_display:
            try:
                current_display.stop()
                logger.info(f"Stopped {current_app} display")
            except Exception as e:
                logger.error(f"Error stopping display: {e}")
            
            current_display = None
            current_app = None
            
        if display_thread and display_thread.is_alive():
            display_thread.join(timeout=5)

def start_sports_display(settings: Dict[str, Any]):
    """Start multi-sport ticker with selectable leagues"""
    global current_display, display_thread, current_app, current_settings
    
    stop_current_display()
    
    with display_lock:
        try:
            if not initialize_display():
                return False

            # Parse sports selection from payload
            sports_cfg = settings.get('sports', {})
            # Accept both new keys and legacy ones
            mlb = bool(sports_cfg.get('mlb', sports_cfg.get('MLB', True)))
            nfl = bool(sports_cfg.get('nfl', sports_cfg.get('NFL', True)))
            cfb = bool(sports_cfg.get('cfb', sports_cfg.get('CFB', True)))

            enabled_sports: List[str] = []
            if mlb: enabled_sports.append('MLB')
            if nfl: enabled_sports.append('NFL')
            if cfb: enabled_sports.append('CFB')
            if not enabled_sports:
                enabled_sports = ['MLB', 'NFL', 'CFB']  # default if nothing selected

            current_display = SportsTicker(
                matrix_display,
                odds_api_key=ODDS_API_KEY,
                enabled_sports=enabled_sports
            )
            current_app = 'sports'
            # Store the current settings so the UI can reflect checkboxes
            current_settings = {
                'sports': {
                    'mlb': mlb,
                    'nfl': nfl,
                    'cfb': cfb
                }
            }
            
            def run_sports():
                try:
                    current_display.start()
                except Exception as e:
                    logger.error(f"Sports display error: {e}")
            
            display_thread = threading.Thread(target=run_sports, daemon=True)
            display_thread.start()
            
            logger.info(f"Sports ticker started - sports: {enabled_sports}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start sports display: {e}")
            return False

def start_news_display(settings: Dict[str, Any]):
    """Start news headlines ticker"""
    global current_display, display_thread, current_app, current_settings
    
    stop_current_display()
    
    with display_lock:
        try:
            if not initialize_display():
                return False
            
            current_display = NewsTicker(matrix_display, news_api_key=NEWS_API_KEY)
            
            # Apply filter settings
            if settings.get('breaking_only'):
                current_display.set_breaking_only(True)
            if settings.get('category'):
                current_display.set_category_filter(settings['category'])
            
            current_app = 'news'
            current_settings = settings
            
            def run_news():
                try:
                    current_display.start()
                except Exception as e:
                    logger.error(f"News display error: {e}")
            
            display_thread = threading.Thread(target=run_news, daemon=True)
            display_thread.start()
            
            logger.info("News ticker started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start news display: {e}")
            return False

def start_mta_display(settings: Dict[str, Any]):
    """Start MTA subway arrivals display"""
    global current_display, display_thread, current_app, current_settings
    
    stop_current_display()
    
    with display_lock:
        try:
            station_id = settings.get('station_id', '127')
            station_name = STATIONS.get(station_id, station_id)
            
            if not initialize_display():
                return False
            
            current_display = MTADisplay(matrix_display, station_id, station_name)
            current_app = 'mta'
            current_settings = settings
            
            def run_mta():
                try:
                    if matrix_display and matrix_display.width <= 64:
                        current_display.start_static_display()
                    else:
                        current_display.start_scrolling_display()
                except Exception as e:
                    logger.error(f"MTA display error: {e}")
            
            display_thread = threading.Thread(target=run_mta, daemon=True)
            display_thread.start()
            
            logger.info(f"MTA display started for {station_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start MTA display: {e}")
            return False

# Flask Routes
@app.route('/')
def index():
    """Main control page"""
    return render_template('index.html', 
                         current_app=current_app,
                         stations=STATIONS,
                         current_settings=current_settings)

@app.route('/api/status')
def api_status():
    """Get current display status"""
    return jsonify({
        'running': current_app is not None,
        'current_app': current_app,
        'settings': current_settings,
        'display_connected': matrix_display is not None
    })

@app.route('/api/start/<app_name>', methods=['POST'])
def api_start_app(app_name):
    """Start a specific display application"""
    settings = request.json or {}
    
    success = False
    message = ""
    
    if app_name == 'sports':
        success = start_sports_display(settings)
        message = "Sports ticker started" if success else "Failed to start sports ticker"
    elif app_name == 'news':
        success = start_news_display(settings)
        message = "News ticker started" if success else "Failed to start news ticker"
    elif app_name == 'mta':
        success = start_mta_display(settings)
        message = "MTA display started" if success else "Failed to start MTA display"
    else:
        message = f"Unknown app: {app_name}"
    
    return jsonify({
        'success': success,
        'message': message,
        'current_app': current_app
    })

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop the current display"""
    stop_current_display()
    return jsonify({
        'success': True,
        'message': 'Display stopped',
        'current_app': None
    })

@app.route('/api/brightness', methods=['POST'])
def api_brightness():
    """Adjust display brightness"""
    data = request.json or {}
    brightness = data.get('brightness', 75)
    
    if matrix_display:
        try:
            matrix_display.options.brightness = int(brightness)
            return jsonify({'success': True, 'brightness': brightness})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Display not initialized'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)