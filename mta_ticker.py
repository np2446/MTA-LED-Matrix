#!/usr/bin/env python3
"""
MTA Subway Arrivals LED Matrix Display
Shows real-time subway arrival times for selected stations
"""

from nyct_gtfs import NYCTFeed
from datetime import datetime
import time
import threading
import logging
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont

# Import the advanced matrix display system
from advanced_matrix_display import AdvancedMatrixDisplay, TextStyle, ScrollDirection, Layer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_KEY = "o2LyxAp80c1sDkBYTLL6r5GSVCiAtRBacATpKEbe"

@dataclass
class TrainArrival:
    """Represents a single train arrival"""
    line: str
    minutes: int
    arrival_time: datetime
    direction: str  # 'uptown' or 'downtown'
    destination: Optional[str] = None

class MTADisplay:
    """MTA Subway display for LED matrix"""
    
    # Subway line colors (official MTA colors)
    LINE_COLORS = {
        '1': (238, 53, 46),    # Red
        '2': (238, 53, 46),    # Red
        '3': (238, 53, 46),    # Red
        '4': (0, 147, 60),     # Green
        '5': (0, 147, 60),     # Green
        '6': (0, 147, 60),     # Green
        '7': (185, 51, 174),   # Purple
        'A': (0, 57, 166),     # Blue
        'C': (0, 57, 166),     # Blue
        'E': (0, 57, 166),     # Blue
        'B': (255, 99, 25),    # Orange
        'D': (255, 99, 25),    # Orange
        'F': (255, 99, 25),    # Orange
        'M': (255, 99, 25),    # Orange
        'G': (108, 190, 69),   # Light Green
        'J': (153, 102, 51),   # Brown
        'Z': (153, 102, 51),   # Brown
        'L': (167, 169, 172),  # Gray
        'N': (252, 204, 10),   # Yellow
        'Q': (252, 204, 10),   # Yellow
        'R': (252, 204, 10),   # Yellow
        'W': (252, 204, 10),   # Yellow
        'S': (128, 129, 131),  # Dark Gray
    }
    
    # Station name mapping (from GTFS ID to display name)
    STATION_NAMES = {}  # Will be populated from the CSV data
    
    def __init__(self, matrix_display: AdvancedMatrixDisplay, station_id: str, station_name: str = None):
        self.display = matrix_display
        self.station_id = station_id
        self.station_name = station_name or station_id
        self.uptown_trains = []
        self.downtown_trains = []
        self.running = False
        self.update_thread = None
        self.update_interval = 30  # Update every 30 seconds
        self.scroll_speed = 1.0
        self.font_cache = {}
        
    def collect_data(self) -> Tuple[List[TrainArrival], List[TrainArrival]]:
        """Collect train arrival data from MTA API"""
        processed_train_ids = set()
        subway_lines = ["A", "C", "E", "B", "D", "F", "M", "J", "Z", "L", "N", "Q", "R", "W", "S", "1", "2", "3", "4", "5", "6", "7"]
        now = datetime.now()
        uptown_trains = []
        downtown_trains = []
        
        logger.info(f"Fetching arrivals for station {self.station_id} - {self.station_name}")
        
        for line in subway_lines:
            try:
                feed = NYCTFeed(line, api_key=API_KEY)
                
                # Filter trips for this station
                trains = feed.filter_trips(headed_for_stop_id=[
                    self.station_id + "N", 
                    self.station_id + "S"
                ])
                
                for train in trains:
                    if train.nyc_train_id in processed_train_ids:
                        continue
                    
                    processed_train_ids.add(train.nyc_train_id)
                    
                    for update in train.stop_time_updates:
                        if update.stop_id.startswith(self.station_id):
                            arrival_time = update.arrival
                            time_diff = arrival_time - now
                            minutes_until_arrival = int(time_diff.total_seconds() // 60)
                            
                            # Only show trains arriving in next 30 minutes
                            if 0 <= minutes_until_arrival <= 30:
                                # Extract the line identifier from train ID
                                line_id = train.nyc_train_id[1] if len(train.nyc_train_id) > 1 else line
                                
                                arrival = TrainArrival(
                                    line=line_id,
                                    minutes=minutes_until_arrival,
                                    arrival_time=arrival_time,
                                    direction='uptown' if update.stop_id.endswith('N') else 'downtown'
                                )
                                
                                if update.stop_id.endswith('N'):
                                    uptown_trains.append(arrival)
                                elif update.stop_id.endswith('S'):
                                    downtown_trains.append(arrival)
                            
            except Exception as e:
                logger.error(f"Error fetching data for line {line}: {e}")
                continue
        
        # Sort by arrival time
        uptown_trains.sort(key=lambda x: x.arrival_time)
        downtown_trains.sort(key=lambda x: x.arrival_time)
        
        logger.info(f"Found {len(uptown_trains)} uptown and {len(downtown_trains)} downtown trains")
        
        return uptown_trains[:8], downtown_trains[:8]  # Return up to 8 trains each direction
    
    def get_font(self, style: str = "regular", size: int = 10) -> ImageFont.FreeTypeFont:
        """Get cached font"""
        cache_key = f"{style}_{size}"
        if cache_key in self.font_cache:
            return self.font_cache[cache_key]
        
        font_paths = {
            'bold': "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            'regular': "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            'mono': "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
        }
        
        try:
            font = ImageFont.truetype(font_paths.get(style, font_paths['regular']), size)
        except:
            font = ImageFont.load_default()
        
        self.font_cache[cache_key] = font
        return font
    
    def create_train_bullet(self, line: str, size: int = 14) -> Image.Image:
        """Create subway line bullet icon"""
        # Create circular bullet
        bullet_size = size + 4
        img = Image.new('RGBA', (bullet_size, bullet_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Get line color
        color = self.LINE_COLORS.get(line.upper(), (128, 128, 128))
        
        # Draw circle
        draw.ellipse([0, 0, bullet_size-1, bullet_size-1], fill=color)
        
        # Add line letter/number
        font = self.get_font('bold', size-4)
        bbox = draw.textbbox((0, 0), line.upper(), font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (bullet_size - text_width) // 2
        y = (bullet_size - text_height) // 2
        
        draw.text((x, y), line.upper(), fill=(255, 255, 255), font=font)
        
        return img
    
    def create_display_image(self) -> Image.Image:
        """Create the display image showing train arrivals"""
        width = self.display.width
        height = self.display.height
        
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Fonts
        station_font = self.get_font('bold', 8)
        direction_font = self.get_font('bold', 7)
        time_font = self.get_font('mono', 9)
        min_font = self.get_font('regular', 6)
        
        # Draw station name at top
        station_text = self.station_name[:20]  # Truncate if too long
        bbox = draw.textbbox((0, 0), station_text, font=station_font)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        draw.text((x, 1), station_text, fill=(255, 255, 255), font=station_font)
        
        # Draw separator line
        draw.line([(0, 10), (width, 10)], fill=(100, 100, 100), width=1)
        
        # Calculate layout
        half_height = (height - 11) // 2
        uptown_y = 11
        downtown_y = 11 + half_height + 1
        
        # Draw uptown section
        draw.text((2, uptown_y), "↑", fill=(0, 255, 0), font=direction_font)
        draw.text((10, uptown_y), "UPTN", fill=(200, 200, 200), font=direction_font)
        
        # Draw uptown trains
        x_offset = 40
        for i, train in enumerate(self.uptown_trains[:4]):  # Show up to 4 trains
            if x_offset > width - 20:
                break
                
            # Draw train bullet
            bullet = self.create_train_bullet(train.line, 10)
            img.paste(bullet, (x_offset, uptown_y), bullet)
            
            # Draw arrival time
            time_text = f"{train.minutes}"
            draw.text((x_offset + 15, uptown_y + 1), time_text, 
                     fill=(255, 255, 255), font=time_font)
            
            # Draw "min" label
            draw.text((x_offset + 15 + len(time_text) * 6, uptown_y + 3), "m", 
                     fill=(150, 150, 150), font=min_font)
            
            x_offset += 35
        
        # Draw separator between directions
        draw.line([(0, downtown_y - 1), (width, downtown_y - 1)], fill=(100, 100, 100), width=1)
        
        # Draw downtown section
        draw.text((2, downtown_y), "↓", fill=(255, 0, 0), font=direction_font)
        draw.text((10, downtown_y), "DWTN", fill=(200, 200, 200), font=direction_font)
        
        # Draw downtown trains
        x_offset = 40
        for i, train in enumerate(self.downtown_trains[:4]):  # Show up to 4 trains
            if x_offset > width - 20:
                break
                
            # Draw train bullet
            bullet = self.create_train_bullet(train.line, 10)
            img.paste(bullet, (x_offset, downtown_y), bullet)
            
            # Draw arrival time
            time_text = f"{train.minutes}"
            draw.text((x_offset + 15, downtown_y + 1), time_text, 
                     fill=(255, 255, 255), font=time_font)
            
            # Draw "min" label
            draw.text((x_offset + 15 + len(time_text) * 6, downtown_y + 3), "m", 
                     fill=(150, 150, 150), font=min_font)
            
            x_offset += 35
        
        # Add update timestamp
        now = datetime.now()
        time_str = now.strftime("%I:%M")
        draw.text((width - 25, height - 7), time_str, 
                 fill=(100, 100, 100), font=min_font)
        
        return img
    
    def create_scrolling_display(self) -> Image.Image:
        """Create a scrolling display with all train information"""
        # Create a wider image for scrolling
        scroll_width = 400
        height = self.display.height
        
        img = Image.new('RGBA', (scroll_width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Fonts
        station_font = self.get_font('bold', 10)
        train_font = self.get_font('regular', 9)
        
        # Starting position
        x_offset = 5
        
        # Station name
        draw.text((x_offset, 2), f"{self.station_name}", 
                 fill=(255, 255, 255), font=station_font)
        x_offset += 150
        
        # Uptown trains
        draw.text((x_offset, 2), "UPTOWN:", fill=(0, 255, 0), font=train_font)
        x_offset += 50
        
        for train in self.uptown_trains[:6]:
            bullet = self.create_train_bullet(train.line, 12)
            img.paste(bullet, (x_offset, 1), bullet)
            draw.text((x_offset + 18, 3), f"{train.minutes}min", 
                     fill=(255, 255, 255), font=train_font)
            x_offset += 50
        
        x_offset += 20
        
        # Downtown trains
        draw.text((x_offset, 17), "DOWNTOWN:", fill=(255, 0, 0), font=train_font)
        x_offset_down = x_offset + 60
        
        for train in self.downtown_trains[:6]:
            bullet = self.create_train_bullet(train.line, 12)
            img.paste(bullet, (x_offset_down, 16), bullet)
            draw.text((x_offset_down + 18, 18), f"{train.minutes}min", 
                     fill=(255, 255, 255), font=train_font)
            x_offset_down += 50
        
        return img
    
    def update_data(self):
        """Update train arrival data periodically"""
        while self.running:
            try:
                self.uptown_trains, self.downtown_trains = self.collect_data()
            except Exception as e:
                logger.error(f"Error updating MTA data: {e}")
            
            time.sleep(self.update_interval)
    
    def start_static_display(self):
        """Start static display mode"""
        self.running = True
        
        # Start update thread
        self.update_thread = threading.Thread(target=self.update_data)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # Initial data fetch
        logger.info("Fetching initial MTA data...")
        self.uptown_trains, self.downtown_trains = self.collect_data()
        
        # Display loop
        def display_loop():
            while self.running:
                # Create and display the image
                display_img = self.create_display_image()
                
                self.display.clear()
                layer = Layer(display_img)
                self.display.add_layer(layer)
                self.display.render()
                
                # Update every second to show time changes
                time.sleep(1)
        
        display_thread = threading.Thread(target=display_loop)
        display_thread.daemon = True
        display_thread.start()
    
    def start_scrolling_display(self):
        """Start scrolling display mode"""
        self.running = True
        
        # Start update thread
        self.update_thread = threading.Thread(target=self.update_data)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # Initial data fetch
        logger.info("Fetching initial MTA data...")
        self.uptown_trains, self.downtown_trains = self.collect_data()
        
        # Scrolling animation
        def scroll_animation():
            while self.running:
                # Create scrolling image
                scroll_img = self.create_scrolling_display()
                scroll_layer = Layer(scroll_img)
                
                self.display.clear()
                self.display.add_layer(scroll_layer)
                
                # Scroll from right to left
                start_x = self.display.width
                end_x = -scroll_img.width
                
                x = start_x
                while x > end_x and self.running:
                    scroll_layer.x = int(x)
                    self.display.render()
                    x -= self.scroll_speed
                    time.sleep(1/30)  # 30 FPS
                
                time.sleep(0.5)
        
        self.display.start_animation(scroll_animation)
    
    def stop(self):
        """Stop the display"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)
        self.display.stop_animation()
        self.display.clear()

def main():
    """Main entry point for standalone testing"""
    import sys
    
    # Default station (Times Square)
    station_id = "127"
    station_name = "Times Sq-42 St"
    
    if len(sys.argv) > 1:
        station_id = sys.argv[1]
    if len(sys.argv) > 2:
        station_name = sys.argv[2]
    
    logger.info(f"Starting MTA Display for {station_name} (ID: {station_id})")
    
    # Initialize display
    display = AdvancedMatrixDisplay(
        rows=32,
        cols=64,
        chain_length=1,
        parallel=1,
        brightness=75,
        hardware_mapping='adafruit-hat',
        gpio_slowdown=2
    )
    
    # Create MTA display
    mta = MTADisplay(display, station_id, station_name)
    
    try:
        # Show intro animation
        display.clear()
        intro_text = display.add_text("MTA", x=20, y=8, style=TextStyle(
            font_size=16,
            color=(0, 57, 166),
            outline_color=(255, 255, 255),
            outline_width=1
        ))
        display.render()
        time.sleep(1)
        
        display.add_text("Live Arrivals", x=10, y=20, style=TextStyle(
            font_size=8,
            color=(255, 255, 255)
        ))
        display.render()
        time.sleep(2)
        
        # Start the display (static mode for small displays)
        if display.width <= 64:
            logger.info("Starting static display mode")
            mta.start_static_display()
        else:
            logger.info("Starting scrolling display mode")
            mta.start_scrolling_display()
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down MTA display...")
        mta.stop()
        display.clear()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    main()