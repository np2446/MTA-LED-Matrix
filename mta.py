from nyct_gtfs import NYCTFeed
from datetime import datetime
import os

API_KEY = os.environ.get('MTAKey')

class MTARGBMatrix():

    def __init__(self, station):
        self.station_id = station
        self.uptown_trains = []
        self.downtown_trains = []
        self.uptownString = ""
        self.downtownString = ""
        
    def collectData(self):
        # Set to track the train IDs that have been processed
        processed_train_ids = set()
        subway_lines = ["1", "2", "3", "4", "5", "6", "7", "A", "C", "E", "B", "D", "F", "M", "G", "J", "Z", "L", "N", "Q", "R", "W", "S"]
        now = datetime.now()


        for line in subway_lines:
            feed = NYCTFeed(line, api_key=API_KEY)
            
            # Filter trips that are going towards the station
            trains = feed.filter_trips(headed_for_stop_id=[self.station_id + "N", self.station_id + "S"])

            # Iterate through trains and divide them into uptown and downtown
            for train in trains:
                # If this train ID has already been processed, skip it
                if train.nyc_train_id in processed_train_ids:
                    continue

                # Mark this train ID as processed
                processed_train_ids.add(train.nyc_train_id)
                
                # Process stop time updates
                for update in train.stop_time_updates:
                    if update.stop_id.startswith(self.station_id):
                        arrival_time = update.arrival
                        time_diff = arrival_time - now
                        minutes_until_arrival = time_diff.total_seconds() // 60
                        
                        # Store the train info and arrival time in a tuple
                        train_info = (arrival_time, f"{train.nyc_train_id[1]}: {int(minutes_until_arrival)}")
                        
                        # If the stop_id ends with 'N', it's uptown (northbound).
                        # If it ends with 'S', it's downtown (southbound).
                        if update.stop_id.endswith('N'):
                            self.uptown_trains.append(train_info)
                        elif update.stop_id.endswith('S'):
                            self.downtown_trains.append(train_info)

        # Sort the uptown and downtown trains by arrival time
        self.uptown_trains.sort()
        self.downtown_trains.sort()
        
        # Add info to strings
        self.uptownString = "Uptown: "
        self.downtownString = "Downtown: "
        
        for _, train_info in self.uptown_trains[:4]:
            self.uptownString += train_info + " "
       
        for _, train_info in self.downtown_trains[:4]:
            self.downtownString += train_info + " "

        self.downtownString.strip()
        self.uptownString.strip()
            

    def displayData(self):
        # Output the uptown trains
        print("Uptown Trains:")
        for _, train_info in self.uptown_trains[:4]:
            print(train_info)

        # Output the downtown trains
        print("\nDowntown Trains:")
        for _, train_info in self.downtown_trains[:4]:
            print(train_info)


        
