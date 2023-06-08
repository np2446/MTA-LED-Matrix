from mta import MTARGBMatrix
from rgb import RGBMatrix
import time

def main():
    print("hello world")
    mta = MTARGBMatrix("R18")
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




if __name__ == "__main__":
    main()