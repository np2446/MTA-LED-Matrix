import time
import sys

from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import ImageFont, ImageDraw, Image

class RGBMatrix():
    
    def __init__(self):
        # initialize matrix options and matrix object
        self.options = RGBMatrixOptions()
        self.options.rows = 32
        self.options.cols = 64
        self.options.chain_length = 1
        self.options.parallel = 1
        self.options.hardware_mapping = 'adafruit-hat'
        self.matrix = RGBMatrix(options = self.options)

        # initialize fonts and canvas
        fontPath = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" # replace with font path
        self.font = ImageFont.truetype(fontPath)
        self.canvas = Image.new("RGB", (self.options.cols, self.options.rows))
        self.draw = ImageDraw.Draw(self.canvas)

    def displayText(self, text):
        self.draw.text((0,0), text, font = self.font, fill = (255,255,0))
        self.matrix.SetImage(self.canvas.convert('RGB'))

    





