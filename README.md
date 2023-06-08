# Subway Stop Info LED Matrix Display README

## Project Description

This project is designed to fetch and display real-time subway stop information on an RGB LED Matrix. It primarily indicates the uptown and downtown train schedules for a specified station. The data is sourced from the New York City Metropolitan Transportation Authority (MTA) through @Andrew-Dickinson's `nyct-gtfs` python library and rendered on an RGB LED Matrix using @hzeller's `rpi-rgb-led-matrix` python library.

## Repository Structure

The repository consists of the following Python scripts:

1. `rgb.py` - This script handles the interaction with the RGB LED Matrix, including initializing the matrix and displaying text on it.

2. `mta.py` - This script is responsible for fetching subway train data from the MTA and processing it to generate a summary of the upcoming trains at a particular subway stop.

3. `main.py` - The main driver script that combines `rgb.py` and `mta.py` to fetch subway stop information and display it on the RGB LED Matrix.

## Dependencies

1. Python 3.x
2. [PIL (Python Imaging Library)](https://pillow.readthedocs.io/en/stable/)
3. [nyct-gtfs python library](https://github.com/Andrew-Dickinson/nyct-gtfs)
3. [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
4. An API key for accessing MTA data (can be obtained from the [MTA website](https://api.mta.info/))

## Hardware Requirements

1. Raspberry Pi (or similar single-board computer)
2. RGB LED Matrix (32x64 is hardcoded in here, but you can adjust the settings with your specific hardware)
3. Adafruit HAT (or a similar HAT for connecting the LED Matrix to Raspberry Pi. Note that if you use a different hat you'll have to adjust the hardware options in rgb.py)

## Setting Up
1. Set up your raspberry pi (raspian lite OS is recommended by @hzeller in the rpi-rgb-led-matrix documentation) and install the rgb led matrix library:

    Follow instructions on [rpi-rgb-led-matrix repo](https://github.com/hzeller/rpi-rgb-led-matrix) for installation of the rgb led matrix library.
    
    I would recommend running the example programs and seeing if everything works correctly. If not everything works, follow the troubleshooting in the library documentation.


2. Clone the repository to your raspberry pi:

    ```
    git clone [repo_url]
    cd [repo_directory]
    ```

3. Install the required Python dependencies:

    ```
    pip install Pillow
    pip install nyct_gtfs
    ```


4. Obtain an API key from the MTA and set it as an environment variable on your Raspberry Pi:

    ```
    export MTAKey="YOUR_API_KEY"
    ```

5. Connect the RGB LED Matrix to your Raspberry Pi using the Adafruit HAT (or equivalent).

6. Make sure the font path and any hardware specifications in `rgb.py` are correct. You can replace it with the path of any TrueType font on your system.

## Usage

To run the program, use the following command:


    python3 main.py [STATION_ID]
    
Replace `[STATION_ID]` with the station ID for which you want to display the train arrivals. You can find the station ids in the included `stationCSV.csv` file.

For example, to get information for Times Square-42nd Street, you would use:

    python3 main.py "R16"


The program will continuously display the uptown and downtown train schedules for the specified station on the RGB LED Matrix. Press `CTRL+C` to stop the program.

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.


## Contact

For questions or issues, please open an issue on the GitHub repository.



