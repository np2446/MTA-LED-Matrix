from mta import MTARGBMatrix
from rgb import MatrixClass
import sys
import time

def main():
    print("hello world")
    mta = MTARGBMatrix(STATION)
    rgb = MatrixClass()

    try:
     while True:
        rgb.staticText("Refreshing")
        try:
           mta.collectData()
        except:
           rgb.displayText("Error fetching","data from mta")
           continue

        for _ in range(16):
           rgb.displayText(mta.uptownString, mta.downtownString)

    except KeyboardInterrupt:
        print("User interrupted program. Exiting...")

if len(sys.argv) == 2 and __name__ == "__main__":
   STATION = sys.argv[1]
   print(f"Starting Program with Stop {STATION}\n")
   main()
else:
   print("ERROR: Program expects station as command line argument. Usage: main.py Station_ID")
