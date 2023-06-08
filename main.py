from mta import MTARGBMatrix
from rgb import RGBMatrix
import sys
import time

def main():
    print("hello world")
    mta = MTARGBMatrix(STATION)
    rgb = RGBMatrix()

    try:
     while True:
        mta.collectData()

        for _ in range(12):
           rgb.displayText(mta.uptownString)
           time.sleep(5)
           rgb.displayText(mta.downtownString)
           time.sleep(5)

    except KeyboardInterrupt:
        print("User interrupted program. Exiting...")

if len(sys.argv) == 2 and __name__ == "__main__":
   STATION = sys.argv[1]
   print(f"Starting Program with Stop {STATION}\n")
   main()
else:
   print("ERROR: Program expects station as command line argument. Usage: main.py Station_ID")
